"""Pokoje: każdy telewizor zakłada własną grę, a telefony dołączają do niej kodem.

Dzięki temu jeden serwer w internecie obsługuje wiele domów naraz, a obcy nie trafią
do cudzej gry. Telewizor dostaje tajny klucz, więc po odświeżeniu wraca do swojego pokoju,
a nikt nie podejrzy gry, udając telewizor.
"""
from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .session import Session

log = logging.getLogger("teleturniej")

# Bez I, O, Q i V, które łatwo pomylić z cyframi lub ze sobą przy przepisywaniu z ekranu.
ALPHABET = "ABCDEFGHJKLMNPRSTUWXYZ"
CODE_LENGTH = 4
MAX_ROOMS = 200
MAX_TVS = 4
# Pokój, w którym nikt nie jest połączony, czeka tyle na powrót graczy.
IDLE_SECONDS = 2 * 3600
SWEEP_SECONDS = 300


def clean_code(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    return re.sub(r"[^A-Z]", "", raw.upper())[:CODE_LENGTH]


@dataclass
class Room:
    code: str
    key: str
    session: Session
    conns: set = field(default_factory=set)
    empty_since: Optional[float] = None


class Rooms:
    def __init__(self, clock, make_session: Callable[[str, str, str], Session]):
        """make_session(kod, adres_dla_telefonów, adres_tv) tworzy sesję nowego pokoju."""
        self.clock = clock
        self.make_session = make_session
        self.rooms: dict[str, Room] = {}
        self._sweeping = False

    def get(self, code: Any) -> Optional[Room]:
        return self.rooms.get(clean_code(code))

    # --- Zakładanie i sprzątanie -------------------------------------------

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self.rooms:
                return code

    def create(self, join_base: str, tv_base: str) -> Optional[Room]:
        self.sweep()
        if len(self.rooms) >= MAX_ROOMS and not self._drop_oldest_empty():
            return None
        code = self._new_code()
        session = self.make_session(code, f"{join_base}/app/?r={code}", f"{tv_base}/tv")
        room = Room(code, secrets.token_urlsafe(18), session, empty_since=self.clock.now())
        self.rooms[code] = room
        log.info("Nowy pokój %s (pokoi: %d)", code, len(self.rooms))
        self._schedule_sweep()
        return room

    def _remove(self, room: Room) -> None:
        self.rooms.pop(room.code, None)
        room.session.close()
        log.info("Pokój %s zamknięty (pokoi: %d)", room.code, len(self.rooms))

    def _drop_oldest_empty(self) -> bool:
        empty = [r for r in self.rooms.values() if r.empty_since is not None]
        if not empty:
            return False
        self._remove(min(empty, key=lambda r: r.empty_since))
        return True

    def sweep(self) -> None:
        now = self.clock.now()
        for room in list(self.rooms.values()):
            if room.empty_since is not None and now - room.empty_since >= IDLE_SECONDS:
                self._remove(room)

    def _schedule_sweep(self) -> None:
        if self._sweeping or not self.rooms:
            return
        self._sweeping = True

        def run() -> None:
            self._sweeping = False
            self.sweep()
            self._schedule_sweep()

        self.clock.call_later(SWEEP_SECONDS, run)

    # --- Połączenia --------------------------------------------------------

    def _attach(self, conn, room: Room) -> None:
        if conn.room is room:
            return
        self._detach(conn)
        conn.room = room
        room.conns.add(conn)
        room.empty_since = None

    def _detach(self, conn) -> None:
        room = conn.room
        if room is None:
            return
        conn.room = None
        room.conns.discard(conn)
        room.session.disconnected(conn)
        conn.role = None
        conn.player_id = None
        if not room.conns:
            room.empty_since = self.clock.now()

    def disconnected(self, conn) -> None:
        self._detach(conn)

    def _tv_hello(self, conn, msg: dict) -> None:
        room = self.get(msg.get("room"))
        key = msg.get("key")
        rejoin = (room is not None and isinstance(key, str)
                  and secrets.compare_digest(room.key.encode(), key.encode("utf-8", "replace"))
                  and len(room.session.tvs) < MAX_TVS)
        if not rejoin:
            room = self.create(*conn.bases)
            if room is None:
                conn.send({"t": "busy"})
                return
            conn.send({"t": "room", "code": room.code, "key": room.key})
        self._attach(conn, room)
        room.session.handle(conn, {"t": "hello", "role": "tv"})

    def _player_room(self, conn, code: Any) -> Optional[Room]:
        room = self.get(code)
        if room is None:
            self._detach(conn)
            conn.send({"t": "no_room", "code": clean_code(code)})
            return None
        self._attach(conn, room)
        return room

    def handle(self, conn, msg: dict) -> None:
        kind = msg.get("t")
        if kind == "ping":
            return
        if kind == "hello":
            if msg.get("role") == "tv":
                self._tv_hello(conn, msg)
                return
            room = self._player_room(conn, msg.get("room"))
            if room:
                room.session.handle(conn, {"t": "hello", "role": "player", "token": msg.get("token")})
            return
        if kind == "join" and "room" in msg:
            room = conn.room if conn.room and conn.room.code == clean_code(msg.get("room")) else None
            if room is None:
                room = self._player_room(conn, msg.get("room"))
            if room:
                room.session.handle(conn, msg)
            return
        if conn.room is not None:
            conn.room.session.handle(conn, msg)
