"""Wspólna podstawa gier.

Każda gra to automat stanów sterowany akcjami z telefonów i zegarem. Każdy etap, na którym
gra czeka na człowieka, musi mieć limit czasu, żeby wyłączony telefon nie zawiesił rozgrywki.

Telefon jest uniwersalnym pilotem: gra opisuje jego ekran listą bloków, a klient tylko je
rysuje. Poprawna odpowiedź trafia do telefonu dopiero po ujawnieniu.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

LETTERS = "ABCDEFGH"


class _Timer:
    __slots__ = ("handle", "deadline", "total", "fn", "left")

    def __init__(self, fn: Callable, total: float):
        self.fn = fn
        self.total = total
        self.handle = None
        self.deadline = 0.0
        self.left = 0.0


def msg(text: str, tone: str = "info", big: bool = False) -> dict:
    return {"type": "msg", "text": text, "tone": tone, "big": big}


def options(action: str, labels: Iterable[str], columns: int = 1, states: Optional[dict] = None,
            letters: bool = True) -> dict:
    states = states or {}
    return {
        "type": "options",
        "action": action,
        "columns": columns,
        "items": [{
            "v": i,
            "label": label,
            "key": LETTERS[i] if letters and i < len(LETTERS) else "",
            "state": states.get(i, ""),
        } for i, label in enumerate(labels)],
    }


def buzz(label: str = "ZGŁASZAM SIĘ!", action: str = "buzz") -> dict:
    return {"type": "buzz", "action": action, "label": label}


def btn(action: str, label: str, v: Any = None, style: str = "", disabled: bool = False,
        hint: str = "", color: str = "") -> dict:
    return {"action": action, "label": label, "v": v, "style": style, "disabled": disabled,
            "hint": hint, "color": color}


def buttons(*items: dict) -> dict:
    return {"type": "buttons", "items": list(items)}


class Game:
    id = ""
    title = ""
    tagline = ""
    rules: list[str] = []
    min_players = 1
    needs_tv = False
    option_defs: list[dict] = []
    allow_spectators = False

    def __init__(self, session, opts: dict, roster: list[str]):
        self.s = session
        self.clock = session.clock
        self.rng = session.rng
        self.opts = opts
        self.roster = list(roster)
        self.screen = "intro"
        self.ranking: Optional[list[dict]] = None
        self.note = ""
        self.stopped = False
        self._timers: dict[str, _Timer] = {}

    @classmethod
    def required_players(cls, opts: dict) -> int:
        return cls.min_players

    # --- Cykl życia --------------------------------------------------------

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        self.stopped = True
        for name in list(self._timers):
            self.cancel_timer(name)

    def on_action(self, pid: str, action: str, msg_: dict) -> None:
        pass

    def on_tv_event(self, event: Any, msg_: dict) -> None:
        pass

    def on_player_away(self, pid: str) -> None:
        pass

    def on_player_back(self, pid: str) -> None:
        pass

    # --- Zegary ------------------------------------------------------------

    def set_timer(self, seconds: float, fn: Callable, name: str = "main",
                  total: Optional[float] = None) -> None:
        self.cancel_timer(name)
        timer = _Timer(fn, total if total is not None else seconds)
        self._timers[name] = timer
        self._arm(name, timer, seconds)

    def _arm(self, name: str, timer: _Timer, seconds: float) -> None:
        def fire() -> None:
            if self._timers.get(name) is timer:
                del self._timers[name]
            if not self.stopped:
                self.s.guard(timer.fn)

        timer.deadline = self.clock.now() + seconds
        timer.handle = self.clock.call_later(seconds, fire)

    def cancel_timer(self, name: str = "main") -> None:
        timer = self._timers.pop(name, None)
        if timer and timer.handle is not None:
            timer.handle.cancel()

    def pause_timer(self, name: str = "main") -> None:
        timer = self._timers.get(name)
        if timer and timer.handle is not None:
            timer.handle.cancel()
            timer.handle = None
            timer.left = max(0.0, timer.deadline - self.clock.now())

    def resume_timer(self, name: str = "main") -> None:
        timer = self._timers.get(name)
        if timer and timer.handle is None:
            self._arm(name, timer, timer.left)

    def time_left(self, name: str = "main") -> float:
        timer = self._timers.get(name)
        if not timer:
            return 0.0
        return timer.left if timer.handle is None else max(0.0, timer.deadline - self.clock.now())

    def timer_view(self, name: str = "main") -> Optional[dict]:
        timer = self._timers.get(name)
        if not timer:
            return None
        return {
            "ms": int(self.time_left(name) * 1000),
            "total": int(timer.total * 1000),
            "running": timer.handle is not None,
        }

    # --- Pomocnicze --------------------------------------------------------

    def name(self, pid: Optional[str]) -> str:
        return self.s.pinfo(pid)["name"] if pid else ""

    def pinfo(self, pid: Optional[str]) -> Optional[dict]:
        return self.s.pinfo(pid) if pid else None

    def fx(self, name: str) -> None:
        self.s.fx(name)

    def pv(self, *blocks: dict, sub: str = "", prompt: str = "", timer: Optional[dict] = None, **extra) -> dict:
        """Opis ekranu telefonu."""
        view = {"theme": self.id, "title": self.title, "sub": sub, "prompt": prompt,
                "timer": timer, "blocks": list(blocks)}
        view.update(extra)
        return view

    def finish(self, ranking: list[dict], note: str = "") -> None:
        """ranking: lista {id?, name, color, score, label} od najlepszego. Remisy dzielą miejsce."""
        for name in list(self._timers):
            self.cancel_timer(name)
        place, previous = 0, None
        for index, item in enumerate(ranking, 1):
            if item.get("score") != previous:
                place, previous = index, item.get("score")
            item["place"] = place
        self.ranking = ranking
        self.note = note
        self.screen = "results"
        self.fx("fanfare")

    # --- Widoki ------------------------------------------------------------

    def tv_view(self) -> dict:
        view = {"id": self.id, "title": self.title, "screen": self.screen}
        if self.screen == "results":
            view.update(ranking=self.ranking, note=self.note)
        else:
            view.update(self.view_tv())
        return view

    def player_view(self, pid: str) -> dict:
        if self.screen == "results":
            return self._results_player(pid)
        if pid not in self.roster and not self.allow_spectators:
            return self.pv(msg("Trwa gra. Dołączysz do następnej rundy, a na razie oglądaj na telewizorze.", big=True))
        return self.view_player(pid)

    def _results_player(self, pid: str) -> dict:
        mine = next((r for r in self.ranking or [] if r.get("id") == pid or pid in r.get("members", [])), None)
        blocks = []
        if mine:
            won = mine["place"] == 1
            blocks.append(msg("Zwycięstwo!" if won else f'{mine["place"]}. miejsce',
                              "good" if won else "info", big=True))
        blocks.append({"type": "ranking", "items": [
            {"place": r["place"], "name": r["name"], "color": r.get("color", "#888"),
             "label": r.get("label", ""),
             "me": r.get("id") == pid or pid in r.get("members", [])}
            for r in self.ranking or []
        ]})
        if self.note:
            blocks.append(msg(self.note))
        if pid == self.s.host_id:
            blocks.append(buttons(btn("end_game", "Wróć do wyboru gry", style="primary")))
        else:
            blocks.append(msg("Gospodarz wybierze kolejną grę."))
        return self.pv(*blocks)

    def view_tv(self) -> dict:
        raise NotImplementedError

    def view_player(self, pid: str) -> dict:
        raise NotImplementedError
