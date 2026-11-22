from __future__ import annotations

import heapq
import random
from pathlib import Path

import pytest

from server.content import Content
from server.music import MusicLibrary
from server.session import Session

DATA = Path(__file__).resolve().parent.parent / "data"


class FakeClock:
    """Zegar, który przesuwa się tylko na żądanie, więc gry w testach trwają ułamek sekundy."""

    def __init__(self):
        self.time = 0.0
        self._queue: list = []
        self._seq = 0

    def now(self) -> float:
        return self.time

    def call_later(self, delay, fn):
        handle = FakeHandle()
        self._seq += 1
        heapq.heappush(self._queue, (self.time + delay, self._seq, fn, handle))
        return handle

    def advance(self, seconds: float) -> None:
        until = self.time + seconds
        while self._queue and self._queue[0][0] <= until:
            when, _seq, fn, handle = heapq.heappop(self._queue)
            self.time = max(self.time, when)
            if not handle.cancelled:
                fn()
        self.time = until

    def run_next(self) -> bool:
        """Wykonuje najbliższe zdarzenie i przesuwa czas dokładnie do niego."""
        while self._queue:
            when, _seq, fn, handle = heapq.heappop(self._queue)
            if handle.cancelled:
                continue
            self.time = max(self.time, when)
            fn()
            return True
        return False


class FakeHandle:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeConn:
    def __init__(self):
        self.role = None
        self.player_id = None
        self.room = None
        self.bases = ("https://gra.example", "https://gra.example")
        self.state = None
        self.messages: list[dict] = []
        self.closed = False

    def send(self, obj):
        if obj.get("t") == "state":
            self.state = obj["state"]
        else:
            self.messages.append(obj)

    def close(self):
        self.closed = True


class TestSession(Session):
    __test__ = False

    def spawn(self, coro):
        # Melodie wbudowane nie wymagają sieci, więc korutyna kończy się bez zawieszenia.
        try:
            coro.send(None)
        except StopIteration:
            pass


class Table:
    """Stół testowy: sesja, telewizor i podłączeni gracze."""

    def __init__(self, seed: int = 1):
        self.clock = FakeClock()
        self.rng = random.Random(seed)
        content = Content(DATA, self.rng)
        music = MusicLibrary(DATA, DATA / "cache_test_unused", self.rng)
        self.session = TestSession(self.clock, content, music, "http://x/", "http://x/tv", rng=self.rng)
        self.tv = FakeConn()
        self.session.handle(self.tv, {"t": "hello", "role": "tv"})
        self.conns: dict[str, FakeConn] = {}

    def join(self, name: str) -> str:
        conn = FakeConn()
        self.session.handle(conn, {"t": "hello", "role": "player"})
        self.session.handle(conn, {"t": "join", "name": name})
        self.conns[conn.player_id] = conn
        return conn.player_id

    def add_players(self, count: int) -> list[str]:
        return [self.join(f"Gracz {i + 1}") for i in range(count)]

    def act(self, pid: str, action: str, v=None, **extra) -> None:
        self.session.handle(self.conns[pid], {"t": "action", "a": action, "v": v, **extra})

    def start(self, game_id: str, **options) -> None:
        host = self.session.host_id
        self.act(host, "select_game", game_id)
        for key, value in options.items():
            self.session.handle(self.conns[host], {"t": "action", "a": "set_option", "key": key, "v": value})
        self.act(host, "start_game")
        self.settle()

    def settle(self) -> None:
        self.clock.advance(0)

    def view(self, pid: str) -> dict:
        self.session.flush()
        return self.conns[pid].state["game"]

    def tv_view(self) -> dict:
        self.session.flush()
        return self.tv.state["game"]


@pytest.fixture
def table():
    return Table()
