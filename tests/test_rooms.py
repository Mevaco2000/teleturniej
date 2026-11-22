"""Pokoje: obcy nie trafiają do cudzej gry, a telewizor i telefony wracają do swojej."""
from __future__ import annotations

import random

from server.content import Content
from server.music import MusicLibrary
from server.rooms import ALPHABET, IDLE_SECONDS, SWEEP_SECONDS, Rooms, clean_code
from tests.conftest import DATA, FakeClock, FakeConn, TestSession


class House:
    """Serwer z pokojami i sztucznym zegarem."""

    def __init__(self):
        self.clock = FakeClock()
        content = Content(DATA, random.Random(1))
        music = MusicLibrary(DATA, DATA / "cache_test_unused", random.Random(1))

        def make(code, join_url, tv_url):
            return TestSession(self.clock, content, music, join_url, tv_url, rng=random.Random(2), code=code)

        self.rooms = Rooms(self.clock, make)

    def send(self, conn, msg):
        self.rooms.handle(conn, msg)
        self.clock.advance(0)

    def tv(self, room=None, key=None) -> FakeConn:
        conn = FakeConn()
        self.send(conn, {"t": "hello", "role": "tv", "room": room, "key": key})
        return conn

    def phone(self, code, name=None, token=None) -> FakeConn:
        conn = FakeConn()
        self.send(conn, {"t": "hello", "role": "player", "room": code, "token": token})
        if name:
            self.send(conn, {"t": "join", "room": code, "name": name})
        return conn

    def leave(self, conn):
        self.rooms.disconnected(conn)
        self.clock.advance(0)


def room_msg(conn):
    found = [m for m in conn.messages if m["t"] == "room"]
    return found[-1] if found else None


def kinds(conn):
    return [m["t"] for m in conn.messages]


def names(conn):
    return [p["name"] for p in conn.state["players"]]


def test_tv_opens_room_and_phone_joins_with_its_code():
    house = House()
    tv = house.tv()
    created = room_msg(tv)
    code = created["code"]
    assert len(code) == 4 and all(c in ALPHABET for c in code)
    assert created["key"]
    assert tv.state["room"] == code
    assert tv.state["joinUrl"] == f"https://gra.example/app/?r={code}"
    assert tv.state["tvUrl"] == "https://gra.example/tv"

    phone = house.phone(code.lower(), "Ania")
    assert "welcome" in kinds(phone)
    assert phone.state["room"] == code
    assert names(tv) == ["Ania"]


def test_unknown_code_is_rejected_without_joining_anything():
    house = House()
    code = room_msg(house.tv())["code"]
    wrong = "ZZZZ" if code != "ZZZZ" else "YYYY"
    phone = house.phone(wrong, "Obcy")
    assert kinds(phone) == ["no_room", "no_room"]
    assert phone.room is None and phone.player_id is None


def test_rooms_do_not_see_each_other():
    house = House()
    tv_a, tv_b = house.tv(), house.tv()
    code_a, code_b = room_msg(tv_a)["code"], room_msg(tv_b)["code"]
    assert code_a != code_b
    house.phone(code_a, "Ania")
    house.phone(code_b, "Bartek")
    assert names(tv_a) == ["Ania"]
    assert names(tv_b) == ["Bartek"]


def test_tv_returns_to_its_room_with_the_key():
    house = House()
    tv = house.tv()
    created = room_msg(tv)
    house.phone(created["code"], "Ania")
    house.leave(tv)

    again = house.tv(created["code"], created["key"])
    assert room_msg(again) is None
    assert again.state["room"] == created["code"]
    assert names(again) == ["Ania"]


def test_tv_without_the_right_key_gets_a_new_room():
    house = House()
    code = room_msg(house.tv())["code"]
    spy = house.tv(code, "zgadywany-klucz")
    assert room_msg(spy)["code"] != code


def test_phone_comes_back_with_token():
    house = House()
    code = room_msg(house.tv())["code"]
    phone = house.phone(code, "Ania")
    welcome = next(m for m in phone.messages if m["t"] == "welcome")
    house.leave(phone)

    back = house.phone(code, token=welcome["token"])
    again = next(m for m in back.messages if m["t"] == "welcome")
    assert again["id"] == welcome["id"]


def test_joining_another_code_moves_the_phone():
    house = House()
    tv_a, tv_b = house.tv(), house.tv()
    code_b = room_msg(tv_b)["code"]
    phone = house.phone(room_msg(tv_a)["code"], "Ania")
    house.send(phone, {"t": "join", "room": code_b, "name": "Ania"})
    assert names(tv_b) == ["Ania"]
    assert [p["connected"] for p in tv_a.state["players"]] == [False]


def test_messages_before_choosing_a_room_are_ignored():
    house = House()
    tv = house.tv()
    stranger = FakeConn()
    house.send(stranger, {"t": "join", "name": "Obcy"})
    house.send(stranger, {"t": "action", "a": "start_game"})
    house.send(stranger, {"t": "ping"})
    assert stranger.messages == []
    assert tv.state["players"] == []


def test_empty_room_is_closed_after_a_while():
    house = House()
    tv = house.tv()
    code = room_msg(tv)["code"]
    phone = house.phone(code, "Ania")
    session = house.rooms.get(code).session
    house.leave(phone)
    house.leave(tv)

    house.clock.advance(IDLE_SECONDS - SWEEP_SECONDS)
    assert house.rooms.get(code) is not None
    house.clock.advance(2 * SWEEP_SECONDS)
    assert house.rooms.get(code) is None
    assert session.closed
    assert kinds(house.phone(code)) == ["no_room"]


def test_room_with_tv_stays_open():
    house = House()
    code = room_msg(house.tv())["code"]
    house.clock.advance(3 * IDLE_SECONDS)
    assert house.rooms.get(code) is not None


def test_full_server_reuses_abandoned_rooms(monkeypatch):
    monkeypatch.setattr("server.rooms.MAX_ROOMS", 2)
    house = House()
    first, second = house.tv(), house.tv()
    third = house.tv()
    assert kinds(third) == ["busy"] and third.room is None

    house.leave(first)
    fourth = house.tv()
    assert room_msg(fourth) is not None
    assert house.rooms.get(room_msg(first)["code"]) is None
    assert house.rooms.get(room_msg(second)["code"]) is not None


def test_running_game_stops_when_room_closes():
    house = House()
    tv = house.tv()
    code = room_msg(tv)["code"]
    host = house.phone(code, "Ania")
    house.phone(code, "Bartek")
    house.send(host, {"t": "action", "a": "select_game", "v": "millionaires"})
    house.send(host, {"t": "action", "a": "start_game", "v": None})
    session = house.rooms.get(code).session
    assert session.game is not None
    for conn in list(house.rooms.get(code).conns):
        house.leave(conn)
    house.clock.advance(IDLE_SECONDS + SWEEP_SECONDS)
    assert session.closed and session.game is None
    # Zatrzymana gra nie może już niczego planować ani rozsyłać.
    house.clock.advance(600)


def test_code_is_cleaned():
    assert clean_code(" ab-cd ") == "ABCD"
    assert clean_code("abcdef") == "ABCD"
    assert clean_code(None) == ""
    assert clean_code(1234) == ""
