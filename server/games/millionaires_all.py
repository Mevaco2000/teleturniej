"""Milionerzy w trybie „Wszyscy na drabince”: wszyscy naraz odpowiadają na te same pytania.

Każdy ma własną kwotę i własne koła ratunkowe, a o wycofaniu się decyduje sam. Kto odpadnie
albo się wycofa, zostaje publicznością: zaznacza odpowiedzi, z których powstaje wynik koła
„pytanie do publiczności”, i odbiera telefony od tych, którzy grają dalej. Zegar pytania jest
wspólny i nie staje dla nikogo, więc koła działają od razu.
"""
from __future__ import annotations

from typing import Optional

from .base import LETTERS, btn, buttons, msg, options
from .millionaires import GUARANTEED, HELPER_ACCURACY, LADDER, LOCK_SECONDS, Millionaires, difficulty_for, money

INTRO_SECONDS = 4
REVEAL_SECONDS = 5
FRIEND_SECONDS = 20
MIN_REAL_VOTES = 2
LIFELINES = ("fifty", "audience", "phone")


class Climber:
    """Stan jednego gracza na drabince."""

    def __init__(self):
        self.status = "playing"  # playing | walked | out | top
        self.earned = 0
        self.lifelines = {name: True for name in LIFELINES}
        self.last: Optional[str] = None  # wynik ostatniego pytania: right | wrong | time | walked
        self.new_question()

    def new_question(self) -> None:
        self.choice: Optional[int] = None
        self.locked = False
        self.hidden: list[int] = []
        self.poll: Optional[list[int]] = None
        self.call: Optional[dict] = None
        self.calling: Optional[str] = None
        self.picking = False

    @property
    def playing(self) -> bool:
        return self.status == "playing"


class MillionairesAll(Millionaires):
    def start(self) -> None:
        self.climbers = {pid: Climber() for pid in self.roster}
        self.level = 0
        self.q = None
        self.votes: dict[str, int] = {}
        self.calls: dict[str, str] = {}  # przyjaciel -> dzwoniący
        self.screen = "intro"
        self.set_timer(INTRO_SECONDS, self._ask)

    # --- Przebieg ----------------------------------------------------------

    def _playing(self) -> list[str]:
        return [pid for pid, c in self.climbers.items() if c.playing]

    def _audience(self) -> list[str]:
        return [pid for pid, c in self.climbers.items() if not c.playing]

    def _ask(self) -> None:
        self.q = self.s.content.question(difficulty_for(self.level))
        self.votes = {}
        self.calls = {}
        for pid in self._playing():
            self.climbers[pid].new_question()
            self.climbers[pid].last = None
        self.screen = "question"
        self.fx("question")
        self.set_timer(self.opts["time"], self._close)

    def _maybe_close(self) -> None:
        if self.screen == "question" and all(
                self.climbers[p].locked or not self.s.is_connected(p) for p in self._playing()):
            self._close()

    def _close(self) -> None:
        self.cancel_timer()
        for friend in list(self.calls):
            self.cancel_timer(f"call:{friend}")
        self.calls = {}
        for pid in self._playing():
            climber = self.climbers[pid]
            climber.calling = None
            climber.picking = False
            # Rozłączony gracz nie traci pieniędzy przez awarię telefonu: wycofuje się z tym, co ma.
            if not climber.locked and not self.s.is_connected(pid):
                self._walk(pid)
        self.screen = "locked"
        self.fx("lock")
        self.set_timer(LOCK_SECONDS, self._reveal)

    def _reveal(self) -> None:
        any_right = False
        for pid in self._playing():
            climber = self.climbers[pid]
            if climber.locked and climber.choice == self.q.correct:
                any_right = True
                climber.earned = LADDER[self.level]
                climber.last = "right"
                if self.level == len(LADDER) - 1:
                    climber.status = "top"
            else:
                climber.last = "wrong" if climber.locked else "time"
                climber.earned = self._guaranteed()
                climber.status = "out"
        self.fx("good" if any_right else "bad")
        self.screen = "reveal"
        self.set_timer(REVEAL_SECONDS, self._after_reveal)

    def _after_reveal(self) -> None:
        if self._playing() and self.level < len(LADDER) - 1:
            self.level += 1
            self._ask()
        else:
            self._finish()

    def _walk(self, pid: str) -> None:
        climber = self.climbers[pid]
        climber.status = "walked"
        climber.earned = LADDER[self.level - 1] if self.level else 0
        climber.last = "walked"
        climber.locked = False
        climber.picking = False
        self.fx("lock")

    def _finish(self) -> None:
        ranking = []
        for pid in sorted(self.roster, key=lambda p: -self.climbers[p].earned):
            info = self.s.pinfo(pid)
            climber = self.climbers[pid]
            label = money(climber.earned) + (" · MILION!" if climber.status == "top" else "")
            ranking.append({"id": pid, "name": info["name"], "color": info["color"],
                            "score": climber.earned, "label": label})
        self.finish(ranking)

    # --- Koła ratunkowe ----------------------------------------------------

    def _visible(self, climber: Climber) -> list[int]:
        return [i for i in range(4) if i not in climber.hidden]

    def _use_lifeline(self, pid: str, name: str) -> None:
        climber = self.climbers[pid]
        climber.lifelines[name] = False
        self.fx("lifeline")
        if name == "fifty":
            wrong = [i for i in range(4) if i != self.q.correct]
            climber.hidden = self.rng.sample(wrong, 2)
            if climber.choice in climber.hidden:
                climber.choice = None
        elif name == "audience":
            climber.poll = self._poll(climber)
        else:
            climber.picking = True

    def _poll(self, climber: Climber) -> list[int]:
        """Prawdziwe głosy publiczności, a gdy jest ich za mało, publiczność w studiu."""
        visible = self._visible(climber)
        counts = [0, 0, 0, 0]
        real = [v for v in self.votes.values() if v in visible]
        if len(real) >= MIN_REAL_VOTES:
            for vote in real:
                counts[vote] += 1
        else:
            accuracy = HELPER_ACCURACY[self.q.difficulty]
            for _ in range(100):
                counts[self.q.correct if self.rng.random() < accuracy else self.rng.choice(visible)] += 1
        total = sum(counts) or 1
        return [round(c * 100 / total) for c in counts]

    def _friends(self, caller: str) -> list[str]:
        return [p for p in self._audience() if self.s.is_connected(p) and p not in self.calls and p != caller]

    def _call(self, caller: str, target) -> None:
        climber = self.climbers[caller]
        if target == "expert":
            climber.picking = False
            if self.rng.random() < HELPER_ACCURACY[self.q.difficulty]:
                choice = self.q.correct
            else:
                choice = self.rng.choice(self._visible(climber))
            climber.call = {"who": "Ekspert w studiu", "choice": choice}
        elif target in self._friends(caller):
            climber.picking = False
            climber.calling = target
            self.calls[target] = caller
            self.fx("phone")
            self.set_timer(FRIEND_SECONDS, lambda: self._end_call(target, None), name=f"call:{target}")

    def _end_call(self, friend: str, choice: Optional[int]) -> None:
        caller = self.calls.pop(friend, None)
        self.cancel_timer(f"call:{friend}")
        if caller is None:
            return
        climber = self.climbers[caller]
        climber.calling = None
        climber.call = {"who": self.name(friend), "choice": choice}

    # --- Akcje -------------------------------------------------------------

    def on_action(self, pid: str, action: str, m: dict) -> None:
        if self.screen != "question" or pid not in self.climbers:
            return
        value = m.get("v")
        climber = self.climbers[pid]
        answer = value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 4 else None
        if not climber.playing:
            if action == "friend_answer" and pid in self.calls:
                self._end_call(pid, answer)
            elif action == "vote" and answer is not None and pid not in self.votes:
                self.votes[pid] = answer
            return
        if climber.locked:
            return
        if action == "select" and answer is not None and answer not in climber.hidden:
            climber.choice = answer
        elif action == "confirm" and climber.choice is not None:
            climber.locked = True
            climber.picking = False
            self.fx("lock")
            self._maybe_close()
        elif action == "walk":
            self._walk(pid)
            self._maybe_close()
        elif action == "lifeline" and isinstance(value, str) and climber.lifelines.get(value) and not climber.picking:
            self._use_lifeline(pid, value)
        elif action == "pick_friend" and climber.picking:
            self._call(pid, value)

    def on_player_away(self, pid: str) -> None:
        if self.screen != "question":
            return
        if pid in self.calls:
            self._end_call(pid, None)
        self._maybe_close()

    # --- Widoki ------------------------------------------------------------

    def view_tv(self) -> dict:
        revealed = self.screen == "reveal"
        show_choices = self.screen in ("locked", "reveal")
        players = []
        for pid, climber in self.climbers.items():
            players.append({
                **self.s.pinfo(pid),
                "status": climber.status,
                "earned": money(climber.earned),
                "locked": climber.locked,
                "last": climber.last,
                "choice": climber.choice if show_choices and climber.locked else None,
            })
        view = {
            "mode": "all",
            "level": self.level,
            "ladder": [money(a) for a in LADDER],
            "guaranteed": list(GUARANTEED),
            "prize": money(LADDER[self.level]),
            "players": players,
            "timer": self.timer_view() if self.screen == "question" else None,
            "decided": sum(1 for p in self._playing() if self.climbers[p].locked),
            "playing": len(self._playing()),
            "votesIn": len(self.votes),
        }
        if self.q and self.screen != "intro":
            view["q"] = {
                "text": self.q.text,
                "options": [{"label": o, "hidden": False} for o in self.q.options],
                "correct": self.q.correct if revealed else None,
            }
        return view

    def view_player(self, pid: str) -> dict:
        climber = self.climbers.get(pid)
        if climber is None:
            return self.pv(msg("Oglądasz grę. Dołączysz do następnej rundy.", big=True))
        sub = f"Pytanie za {money(LADDER[self.level])}  ·  Masz {money(climber.earned)}"
        if self.screen == "intro":
            return self.pv(msg("Wszyscy na drabince! Odpowiadacie naraz, a każdy sam decyduje, kiedy się wycofać.",
                               big=True))
        if self.screen == "question":
            if climber.playing:
                return self._climber_view(pid, climber, sub)
            return self._audience_view(pid, climber)
        if self.screen == "locked":
            if climber.playing:
                return self.pv(msg("Sprawdzamy…", big=True), sub=sub)
            return self.pv(msg("Patrz na telewizor!", big=True), sub=f"Twoja wygrana: {money(climber.earned)}")
        if self.screen == "reveal" and climber.last:
            tone, text = {
                "right": ("good", f"Dobrze! Masz {money(climber.earned)}."),
                "wrong": ("bad", f"Niestety. Zabierasz {money(climber.earned)}."),
                "time": ("bad", f"Czas minął. Zabierasz {money(climber.earned)}."),
                "walked": ("info", f"Wycofujesz się z kwotą {money(climber.earned)}."),
            }[climber.last]
            if climber.status == "top":
                text = "MILION! Wygrywasz 1 000 000 zł!"
            return self.pv(msg(text, tone, big=True))
        return self.pv(msg("Patrz na telewizor!", big=True), sub=f"Twoja wygrana: {money(climber.earned)}")

    def _climber_view(self, pid: str, climber: Climber, sub: str) -> dict:
        timer = self.timer_view()
        if climber.locked:
            waiting = len([p for p in self._playing() if not self.climbers[p].locked])
            return self.pv(msg(f"Zatwierdzone: {LETTERS[climber.choice]}. Czekamy jeszcze na: {waiting}.", big=True),
                           sub=sub, timer=timer)
        if climber.picking:
            friends = self._friends(pid)
            return self.pv(msg("Do kogo dzwonisz? Zegar biegnie!"), buttons(
                *[btn("pick_friend", self.name(p), v=p, color=self.s.pinfo(p)["color"]) for p in friends],
                btn("pick_friend", "Ekspert w studiu", v="expert"),
            ), sub=sub, prompt=self.q.text, timer=timer)
        states = {i: "gone" for i in climber.hidden}
        if climber.choice is not None:
            states[climber.choice] = "selected"
        labels = ["" if i in climber.hidden else label for i, label in enumerate(self.q.options)]
        blocks = [options("select", labels, states=states)]
        if climber.poll:
            blocks.append(msg("Publiczność: " + "  ".join(
                f"{LETTERS[i]} {p}%" for i, p in enumerate(climber.poll) if i not in climber.hidden)))
        if climber.calling:
            blocks.append(msg(f"Dzwonisz do: {self.name(climber.calling)}. Czekaj na odpowiedź…"))
        elif climber.call:
            said = LETTERS[climber.call["choice"]] if climber.call["choice"] is not None else "nie wie"
            blocks.append(msg(f'{climber.call["who"]}: {said}'))
        blocks.append(buttons(btn("confirm", "To moja ostateczna odpowiedź", style="primary",
                                  disabled=climber.choice is None)))
        blocks.append(buttons(
            btn("lifeline", "50:50", v="fifty", disabled=not climber.lifelines["fifty"], style="small"),
            btn("lifeline", "Publiczność", v="audience", disabled=not climber.lifelines["audience"], style="small"),
            btn("lifeline", "Telefon", v="phone", disabled=not climber.lifelines["phone"], style="small"),
        ))
        walk = money(LADDER[self.level - 1]) if self.level else "0 zł"
        blocks.append(buttons(btn("walk", f"Wycofuję się z kwotą {walk}", style="ghost")))
        return self.pv(*blocks, sub=sub, prompt=self.q.text, timer=timer)

    def _audience_view(self, pid: str, climber: Climber) -> dict:
        sub = f"Twoja wygrana: {money(climber.earned)}"
        timer = self.timer_view()
        if pid in self.calls:
            return self.pv(options("friend_answer", self.q.options),
                           buttons(btn("friend_answer", "Nie wiem", style="ghost")),
                           sub=f"Dzwoni {self.name(self.calls[pid])}!", prompt=self.q.text,
                           timer=self.timer_view(f"call:{pid}"))
        if pid in self.votes:
            return self.pv(msg(f"Twój głos: {LETTERS[self.votes[pid]]}. Gracze mogą zapytać publiczność.", big=True),
                           sub=sub, timer=timer)
        return self.pv(msg("Jesteś w publiczności. Co byś zaznaczył(a)? Twój głos trafi do koła „publiczność”."),
                       options("vote", self.q.options), sub=sub, prompt=self.q.text, timer=timer)
