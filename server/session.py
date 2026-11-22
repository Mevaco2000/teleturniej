"""Jedna sesja gry: gracze, telewizory, gospodarz i rozsyłanie stanu."""
from __future__ import annotations

import asyncio
import logging
import random
import re
import secrets
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .games import GAMES

log = logging.getLogger("teleturniej")

PALETTE = ["#ff5a5f", "#ffb400", "#2ec4b6", "#4d96ff", "#b388ff", "#ff7ac6",
           "#7ed957", "#ff9248", "#00d1ff", "#f4e04d", "#c0c8d8", "#e36bae",
           "#a0e426", "#ff6f91", "#6a8dff", "#ffc75f"]
MAX_PLAYERS = 16
MAX_NAME = 16
HOST_GRACE_SECONDS = 30


@dataclass
class Player:
    id: str
    token: str
    name: str
    color: str
    conn: Any = None

    @property
    def connected(self) -> bool:
        return self.conn is not None

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color, "connected": self.connected}


def clean_name(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    name = re.sub(r"\s+", " ", "".join(c for c in raw if c.isprintable())).strip()
    return name[:MAX_NAME].strip()


class Session:
    def __init__(self, clock, content, music, join_url: str = "", tv_url: str = "",
                 rng: Optional[random.Random] = None, code: str = ""):
        self.clock = clock
        self.content = content
        self.music = music
        self.rng = rng or random.Random()
        self.join_url = join_url
        self.tv_url = tv_url
        self.code = code
        self.closed = False
        self.players: dict[str, Player] = {}
        self.known: dict[str, dict] = {}
        self.tvs: set = set()
        self.host_id: Optional[str] = None
        self.game = None
        self.selected: Optional[str] = None
        self.options: dict[str, dict] = {
            gid: {d["key"]: d["default"] for d in cls.option_defs} for gid, cls in GAMES.items()
        }
        self.notice: Optional[str] = None
        self._fx: deque = deque(maxlen=12)
        self._fx_id = 0
        self._flush_pending = False
        self._host_timer = None
        self._next_color = 0
        self._tasks: set = set()

    # --- Rozsyłanie stanu --------------------------------------------------

    def touch(self) -> None:
        if not self._flush_pending and not self.closed:
            self._flush_pending = True
            self.clock.call_later(0, self.flush)

    def flush(self) -> None:
        self._flush_pending = False
        tv_state = self.tv_state()
        for conn in list(self.tvs):
            conn.send({"t": "state", "state": tv_state})
        for player in self.players.values():
            if player.conn is not None:
                player.conn.send({"t": "state", "state": self.player_state(player)})

    def fx(self, name: str) -> None:
        self._fx_id += 1
        self._fx.append({"id": self._fx_id, "name": name})
        self.touch()

    def guard(self, fn: Callable, *args) -> None:
        """Błąd w logice gry ma zakończyć grę z komunikatem, a nie zawiesić całego stołu."""
        try:
            fn(*args)
        except Exception:
            log.exception("Błąd w grze")
            self.abort_game("Wystąpił błąd i gra została przerwana.")
        self.touch()

    def spawn(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- Widoki ------------------------------------------------------------

    def _catalog(self) -> list[dict]:
        return [{
            "id": cls.id,
            "title": cls.title,
            "tagline": cls.tagline,
            "rules": cls.rules,
            "minPlayers": cls.min_players,
            "needsTv": cls.needs_tv,
            "options": cls.option_defs,
        } for cls in GAMES.values()]

    def _base_state(self) -> dict:
        return {
            "players": [p.public() for p in self.players.values()],
            "hostId": self.host_id,
            "joinUrl": self.join_url,
            "tvUrl": self.tv_url,
            "room": self.code,
            "selected": self.selected,
            "options": self.options,
            "catalog": self._catalog(),
            "tvCount": len(self.tvs),
            "notice": self.notice,
        }

    def tv_state(self) -> dict:
        state = self._base_state()
        state["fx"] = list(self._fx)
        state["game"] = self.game.tv_view() if self.game else None
        return state

    def player_state(self, player: Player) -> dict:
        state = self._base_state()
        state["me"] = player.id
        state["isHost"] = player.id == self.host_id
        state["game"] = self.game.player_view(player.id) if self.game else None
        return state

    def pinfo(self, pid: str) -> dict:
        player = self.players.get(pid)
        if player:
            return player.public()
        known = self.known.get(pid)
        if known:
            return {**known, "connected": False}
        return {"id": pid, "name": "?", "color": "#888", "connected": False}

    def is_connected(self, pid: str) -> bool:
        player = self.players.get(pid)
        return bool(player and player.connected)

    def connected_ids(self) -> list[str]:
        return [p.id for p in self.players.values() if p.connected]

    # --- Połączenia --------------------------------------------------------

    def _welcome(self, conn, player: Player) -> None:
        if player.conn is not None and player.conn is not conn:
            # Stare okno musi przestać się łączyć, inaczej dwa okna wyrzucałyby się nawzajem.
            player.conn.player_id = None
            player.conn.send({"t": "replaced"})
            player.conn.close()
        player.conn = conn
        conn.role = "player"
        conn.player_id = player.id
        conn.send({"t": "welcome", "token": player.token, "id": player.id, "name": player.name})
        self._ensure_host()
        if self.game:
            self.guard(self.game.on_player_back, player.id)
        self.touch()

    def _ensure_host(self) -> None:
        if self.host_id in self.players:
            if self.players[self.host_id].connected:
                self._cancel_host_timer()
                return
            if self._host_timer is not None:
                return
        else:
            self.host_id = None
        online = self.connected_ids()
        if self.host_id is None:
            self.host_id = online[0] if online else None
            return
        self._host_timer = self.clock.call_later(HOST_GRACE_SECONDS, self._migrate_host)

    def _cancel_host_timer(self) -> None:
        if self._host_timer is not None:
            self._host_timer.cancel()
            self._host_timer = None

    def _migrate_host(self) -> None:
        self._host_timer = None
        host = self.players.get(self.host_id or "")
        if host and host.connected:
            return
        online = self.connected_ids()
        if online:
            self.host_id = online[0]
        self.touch()

    def disconnected(self, conn) -> None:
        self.tvs.discard(conn)
        if conn.player_id:
            player = self.players.get(conn.player_id)
            if player and player.conn is conn:
                player.conn = None
                self._ensure_host()
                if self.game:
                    self.guard(self.game.on_player_away, player.id)
        self.touch()

    def _find_token(self, token: Any) -> Optional[Player]:
        if not isinstance(token, str):
            return None
        wanted = token.encode("utf-8")
        for player in self.players.values():
            if secrets.compare_digest(player.token.encode("utf-8"), wanted):
                return player
        return None

    def _join(self, conn, raw_name: Any) -> None:
        name = clean_name(raw_name)
        if not name:
            conn.send({"t": "error", "code": "name", "message": "Podaj imię."})
            return
        if len(self.players) >= MAX_PLAYERS:
            conn.send({"t": "error", "code": "full", "message": "Nie ma już wolnych miejsc."})
            return
        taken = {p.name.casefold() for p in self.players.values()}
        base, suffix = name, 2
        while name.casefold() in taken:
            tail = f" {suffix}"
            name = base[:MAX_NAME - len(tail)] + tail
            suffix += 1
        pid = secrets.token_hex(4)
        color = PALETTE[self._next_color % len(PALETTE)]
        self._next_color += 1
        player = Player(pid, secrets.token_urlsafe(18), name, color)
        self.players[pid] = player
        self.known[pid] = {"id": pid, "name": name, "color": color}
        self._welcome(conn, player)

    def _remove(self, pid: str) -> None:
        player = self.players.pop(pid, None)
        if not player:
            return
        if player.conn is not None:
            # Połączenie zostaje otwarte, żeby ta osoba mogła od razu dołączyć ponownie.
            player.conn.send({"t": "removed"})
            player.conn.player_id = None
            player.conn = None
        if self.game:
            self.guard(self.game.on_player_away, pid)
        if self.host_id == pid:
            self._cancel_host_timer()
        self._ensure_host()
        self.touch()

    # --- Wiadomości od klientów --------------------------------------------

    def handle(self, conn, msg: dict) -> None:
        kind = msg.get("t")
        if kind == "hello":
            if msg.get("role") == "tv":
                conn.role = "tv"
                self.tvs.add(conn)
                conn.send({"t": "welcome"})
                self.touch()
                return
            player = self._find_token(msg.get("token"))
            if player:
                self._welcome(conn, player)
            else:
                conn.send({"t": "need_name"})
        elif kind == "join":
            if conn.player_id is None:
                self._join(conn, msg.get("name"))
        elif kind == "tv" and conn.role == "tv":
            if self.game:
                self.guard(self.game.on_tv_event, msg.get("e"), msg)
        elif conn.player_id and conn.player_id in self.players:
            if kind == "action":
                self._player_action(conn.player_id, msg)

    def _player_action(self, pid: str, msg: dict) -> None:
        action = msg.get("a")
        if not isinstance(action, str):
            return
        if action == "leave":
            self._remove(pid)
        elif pid == self.host_id and action in self._HOST_ACTIONS:
            self._HOST_ACTIONS[action](self, msg)
            self.touch()
        elif self.game:
            self.guard(self.game.on_action, pid, action, msg)

    # --- Działania gospodarza ----------------------------------------------

    def _select_game(self, msg: dict) -> None:
        gid = msg.get("v")
        if not self.game and (gid is None or (isinstance(gid, str) and gid in GAMES)):
            self.selected = gid
            self.notice = None

    def _set_option(self, msg: dict) -> None:
        gid, key, value = self.selected, msg.get("key"), msg.get("v")
        if self.game or gid not in GAMES:
            return
        for definition in GAMES[gid].option_defs:
            if definition["key"] == key and any(c["v"] == value for c in definition["choices"]):
                self.options[gid][key] = value

    def _start_game(self, msg: dict) -> None:
        if self.game or self.selected not in GAMES:
            return
        cls = GAMES[self.selected]
        roster = self.connected_ids()
        if len(roster) < cls.required_players(self.options[cls.id]):
            self.notice = f"{cls.title}: potrzeba więcej graczy."
            return
        if cls.needs_tv and not self.tvs:
            self.notice = "Ta gra gra muzykę na telewizorze. Otwórz najpierw ekran TV."
            return
        self.notice = None
        self.game = cls(self, dict(self.options[cls.id]), roster)
        self.guard(self.game.start)

    def _end_game(self, msg: dict) -> None:
        if self.game:
            self.game.stop()
            self.game = None
            self.selected = None

    def _kick(self, msg: dict) -> None:
        pid = msg.get("v")
        if isinstance(pid, str) and pid in self.players and pid != self.host_id:
            self._remove(pid)

    _HOST_ACTIONS = {
        "select_game": _select_game,
        "set_option": _set_option,
        "start_game": _start_game,
        "end_game": _end_game,
        "kick": _kick,
    }

    def abort_game(self, message: str) -> None:
        if self.game and self.game.absorb_abort(message):
            self.touch()
            return
        if self.game:
            try:
                self.game.stop()
            except Exception:
                log.exception("Błąd przy zatrzymywaniu gry")
            self.game = None
        self.notice = message
        self.touch()

    def close(self) -> None:
        """Pokój znika: gra i wszystkie odliczania muszą się zatrzymać, żeby nie zostały w pamięci."""
        if self.game:
            try:
                self.game.stop()
            except Exception:
                log.exception("Błąd przy zatrzymywaniu gry")
            self.game = None
        self._cancel_host_timer()
        for task in list(self._tasks):
            task.cancel()
        self.closed = True
