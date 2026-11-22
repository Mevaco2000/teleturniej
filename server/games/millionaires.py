"""Milionerzy: pytanie eliminacyjne, drabinka i koła ratunkowe obsługiwane przez telefony.

Dwa tryby (opcja „Tryb”):
- „Jeden fotel”: jak w telewizji. Kto nie gra, obstawia żetonami, czy gracz na fotelu odpowie dobrze.
- „Wszyscy na drabince”: wszyscy odpowiadają naraz, zob. millionaires_all.py.
"""
from __future__ import annotations

from typing import Optional

from .base import LETTERS, Game, btn, buttons, msg, options

LADDER = [500, 1_000, 2_000, 5_000, 10_000, 20_000, 40_000, 75_000, 125_000, 250_000, 500_000, 1_000_000]
GUARANTEED = (1, 6)
QUALIFY_SECONDS = 15
QUALIFY_REVEAL_SECONDS = 5
AUDIENCE_SECONDS = 12
PHONE_PICK_SECONDS = 15
PHONE_CALL_SECONDS = 30
EXPERT_SECONDS = 5
LOCK_SECONDS = 2.2
REVEAL_SECONDS = 4
TURN_END_SECONDS = 5
# Szansa, że symulowana publiczność lub ekspert wskaże dobrą odpowiedź.
HELPER_ACCURACY = {1: 0.95, 2: 0.8, 3: 0.6, 4: 0.45}
# Zakłady w trybie jednego fotela: żetony na start i stawki do wyboru (plus „va banque”).
START_CHIPS = 1000
STAKES = (100, 250, 500)
BET_SIDES = ("right", "wrong")


def money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " zł"


def difficulty_for(level: int) -> int:
    if level < 3:
        return 1
    if level < 6:
        return 2
    return 3 if level < 10 else 4


class Millionaires(Game):
    id = "millionaires"
    title = "Milionerzy"
    tagline = "Dwanaście pytań dzieli Cię od miliona."
    min_players = 1
    allow_spectators = True
    rules = [
        "Dwanaście pytań coraz trudniejszych. Sumy gwarantowane: 1 000 zł i 40 000 zł. W każdej chwili możesz się wycofać z wygraną.",
        "Koła: 50:50, pytanie do publiczności i telefon do przyjaciela (dzwonisz do innego gracza).",
        "Tryb „Wszyscy na drabince”: wszyscy odpowiadają naraz na te same pytania i każdy sam decyduje, kiedy się wycofać. "
        "Kto odpadnie, zostaje publicznością i przyjacielem do telefonu.",
        "Tryb „Jeden fotel”: najszybsza dobra odpowiedź w eliminacjach sadza na fotelu, a reszta obstawia żetonami, "
        "czy gracz odpowie dobrze.",
    ]
    option_defs = [{
        "key": "mode",
        "label": "Tryb",
        "default": "all",
        "choices": [{"v": "all", "l": "Wszyscy na drabince"}, {"v": "seat", "l": "Jeden fotel + zakłady"}],
    }, {
        "key": "time",
        "label": "Czas na pytanie",
        "default": 60,
        "choices": [{"v": 30, "l": "30 s"}, {"v": 60, "l": "60 s"}, {"v": 120, "l": "2 min"}],
    }]

    def __new__(cls, session, opts: dict, roster: list[str]):
        # Tryb „Wszyscy na drabince” to osobny automat stanów z tymi samymi opcjami i kartą gry.
        if cls is Millionaires and opts.get("mode") == "all":
            from .millionaires_all import MillionairesAll
            return super().__new__(MillionairesAll)
        return super().__new__(cls)

    def start(self) -> None:
        self.chips = {p: START_CHIPS for p in self.roster}
        self.bets: dict[str, tuple[str, int]] = {}
        self.bet_results: Optional[list[dict]] = None
        self.waiting = list(self.roster)
        self.earned: dict[str, int] = {}
        self.hot: Optional[str] = None
        self.level = 0
        self.q = None
        self.hidden: list[int] = []
        self.selected: Optional[int] = None
        self.lifelines = {"fifty": True, "audience": True, "phone": True}
        self.outcome: Optional[str] = None
        self.qualify_answers: dict[str, tuple[int, float]] = {}
        self.qualify_winner: Optional[dict] = None
        self.votes: dict[str, int] = {}
        self.poll: Optional[list[int]] = None
        self.friend: Optional[str] = None
        self.call: Optional[dict] = None
        self._next_contestant()

    def _next_contestant(self) -> None:
        if not self.waiting:
            self._finish()
        elif len(self.waiting) == 1:
            self.hot = self.waiting[0]
            self._begin_turn()
        else:
            self._start_qualify()

    # --- Eliminacje --------------------------------------------------------

    def _start_qualify(self) -> None:
        self.q = self.s.content.question(2)
        self.hot = None
        self.qualify_answers = {}
        self.qualify_winner = None
        self.screen = "qualify"
        self._qualify_started = self.clock.now()
        self.set_timer(QUALIFY_SECONDS, self._resolve_qualify)

    def _resolve_qualify(self) -> None:
        self.cancel_timer()
        right = [(t, p) for p, (i, t) in self.qualify_answers.items() if i == self.q.correct]
        if right:
            elapsed, winner = min(right)
            self.qualify_winner = {"player": self.s.pinfo(winner), "seconds": round(elapsed, 2)}
        else:
            winner = self.rng.choice(self.waiting)
            self.qualify_winner = {"player": self.s.pinfo(winner), "seconds": None}
        self.hot = winner
        self.screen = "qualify_reveal"
        self.fx("good")
        self.set_timer(QUALIFY_REVEAL_SECONDS, self._begin_turn)

    # --- Pytania -----------------------------------------------------------

    def _begin_turn(self) -> None:
        self.level = 0
        self.lifelines = {"fifty": True, "audience": True, "phone": True}
        self._ask()

    def _ask(self) -> None:
        self.q = self.s.content.question(difficulty_for(self.level))
        self.hidden = []
        self.selected = None
        self.outcome = None
        self.poll = None
        self.call = None
        self.friend = None
        self.bets = {}
        self.bet_results = None
        self.screen = "question"
        self.fx("question")
        self.set_timer(self.opts["time"], self._time_up)

    def _time_up(self) -> None:
        self.selected = None
        self._reveal()

    def _lock_in(self) -> None:
        self.cancel_timer()
        self.screen = "locked"
        self.fx("lock")
        self.set_timer(LOCK_SECONDS, self._reveal)

    def _guaranteed(self) -> int:
        amount = 0
        for level in GUARANTEED:
            if self.level > level:
                amount = LADDER[level]
        return amount

    def _reveal(self) -> None:
        self.cancel_timer()
        right = self.selected == self.q.correct
        self.screen = "reveal"
        self._settle_bets(right)
        if right:
            self.outcome = "right"
            self.fx("good")
            self.earned[self.hot] = LADDER[self.level]
            if self.level == len(LADDER) - 1:
                self.set_timer(REVEAL_SECONDS, self._end_turn)
            else:
                self.set_timer(REVEAL_SECONDS, self._next_level)
        else:
            self.outcome = "wrong"
            self.fx("bad")
            self.earned[self.hot] = self._guaranteed()
            self.set_timer(REVEAL_SECONDS, self._end_turn)

    def _next_level(self) -> None:
        self.level += 1
        self._ask()

    def _walk_away(self) -> None:
        self.cancel_timer()
        self.earned[self.hot] = LADDER[self.level - 1] if self.level else 0
        self._settle_bets(None)
        self.outcome = "walked"
        self.screen = "reveal"
        self.fx("lock")
        self.set_timer(REVEAL_SECONDS, self._end_turn)

    def _end_turn(self) -> None:
        self.earned.setdefault(self.hot, 0)
        self.waiting.remove(self.hot)
        self.screen = "turn_end"
        self.set_timer(TURN_END_SECONDS, self._next_contestant)

    def _finish(self) -> None:
        ranking = []
        betting = len(self.roster) > 1
        order = sorted(self.roster, key=lambda p: (-self.earned.get(p, 0), -self.chips[p]))
        for pid in order:
            info = self.s.pinfo(pid)
            amount = self.earned.get(pid, 0)
            label = money(amount) + (f" · żetony: {self.chips[pid]}" if betting else "")
            ranking.append({"id": pid, "name": info["name"], "color": info["color"],
                            "score": [amount, self.chips[pid]] if betting else amount, "label": label})
        note = ""
        if betting:
            best = max(self.roster, key=lambda p: self.chips[p])
            if self.chips[best] > START_CHIPS:
                note = f"Najlepiej obstawiał(a) {self.name(best)}: {self.chips[best]} żetonów."
        self.finish(ranking, note=note)

    # --- Zakłady -----------------------------------------------------------

    def _betting_open(self) -> bool:
        return self.screen in ("question", "audience", "phone_pick", "phone_call")

    def _stakes(self, pid: str) -> list[int]:
        """Stawki do wyboru: stałe kwoty mniejsze niż stan konta i „va banque” za wszystko."""
        chips = self.chips.get(pid, 0)
        if chips <= 0:
            return []
        return [s for s in STAKES if s < chips] + [chips]

    def _place_bet(self, pid: str, value) -> None:
        if not (isinstance(value, list) and len(value) == 2):
            return
        side, stake = value
        if side in BET_SIDES and isinstance(stake, int) and not isinstance(stake, bool) and stake in self._stakes(pid):
            self.bets[pid] = (side, stake)

    def _settle_bets(self, right: Optional[bool]) -> None:
        """Dobra prognoza podwaja stawkę, zła ją zabiera. Po wycofaniu się gracza zakłady przepadają bez straty."""
        results = []
        for pid, (side, stake) in self.bets.items():
            delta = 0 if right is None else (stake if (side == "right") == right else -stake)
            self.chips[pid] += delta
            results.append({"player": self.s.pinfo(pid), "side": side, "stake": stake, "delta": delta})
        results.sort(key=lambda r: -r["delta"])
        self.bet_results = results
        self.bets = {}

    # --- Koła ratunkowe ----------------------------------------------------

    def _helpers(self) -> list[str]:
        return [p for p in self.s.connected_ids() if p != self.hot]

    def _visible_answers(self) -> list[int]:
        return [i for i in range(4) if i not in self.hidden]

    def _use_fifty(self) -> None:
        wrong = [i for i in range(4) if i != self.q.correct]
        self.hidden = self.rng.sample(wrong, 2)
        if self.selected in self.hidden:
            self.selected = None
        self.fx("lifeline")

    def _use_audience(self) -> None:
        self.pause_timer()
        self.votes = {}
        self.screen = "audience"
        self.fx("lifeline")
        self.set_timer(AUDIENCE_SECONDS, self._close_poll, name="helper")

    def _close_poll(self) -> None:
        self.cancel_timer("helper")
        counts = [0, 0, 0, 0]
        for choice in self.votes.values():
            counts[choice] += 1
        if sum(counts) < 2:
            counts = self._simulated_votes()
        total = sum(counts) or 1
        self.poll = [round(c * 100 / total) for c in counts]
        self.screen = "question"
        self.resume_timer()

    def _simulated_votes(self) -> list[int]:
        accuracy = HELPER_ACCURACY[self.q.difficulty]
        visible = self._visible_answers()
        counts = [0, 0, 0, 0]
        for _ in range(100):
            if self.rng.random() < accuracy:
                counts[self.q.correct] += 1
            else:
                counts[self.rng.choice(visible)] += 1
        return counts

    def _use_phone(self) -> None:
        self.pause_timer()
        self.fx("lifeline")
        if self._helpers():
            self.screen = "phone_pick"
            self.set_timer(PHONE_PICK_SECONDS, self._phone_expert, name="helper")
        else:
            self._phone_expert()

    def _phone_expert(self) -> None:
        self.friend = None
        self.screen = "phone_call"
        self.set_timer(EXPERT_SECONDS, self._expert_answers, name="helper")

    def _expert_answers(self) -> None:
        if self.rng.random() < HELPER_ACCURACY[self.q.difficulty]:
            choice = self.q.correct
        else:
            choice = self.rng.choice(self._visible_answers())
        self._close_call("Ekspert w studiu", choice)

    def _phone_friend(self, pid: str) -> None:
        self.friend = pid
        self.screen = "phone_call"
        self.fx("phone")
        self.set_timer(PHONE_CALL_SECONDS, lambda: self._close_call(self.name(self.friend), None), name="helper")

    def _close_call(self, who: str, choice: Optional[int]) -> None:
        self.cancel_timer("helper")
        self.call = {"who": who, "choice": choice}
        self.friend = None
        self.screen = "question"
        self.resume_timer()

    # --- Akcje -------------------------------------------------------------

    def on_action(self, pid: str, action: str, m: dict) -> None:
        value = m.get("v")
        valid_answer = isinstance(value, int) and value in self._visible_answers() if self.q else False
        if action == "qualify" and self.screen == "qualify" and pid in self.waiting:
            if valid_answer and pid not in self.qualify_answers:
                self.qualify_answers[pid] = (value, self.clock.now() - self._qualify_started)
                if all(p in self.qualify_answers or not self.s.is_connected(p) for p in self.waiting):
                    self._resolve_qualify()
        elif action == "vote" and self.screen == "audience" and pid != self.hot:
            if valid_answer and pid not in self.votes:
                self.votes[pid] = value
                if all(p in self.votes for p in self._helpers()):
                    self._close_poll()
        elif action == "friend_answer" and self.screen == "phone_call" and pid == self.friend:
            if valid_answer:
                self._close_call(self.name(pid), value)
            elif value is None:
                self._close_call(self.name(pid), None)
        elif action == "bet" and self._betting_open() and pid != self.hot and pid in self.chips and pid not in self.bets:
            self._place_bet(pid, value)
        elif pid == self.hot:
            self._hot_action(action, value, valid_answer)

    def _hot_action(self, action: str, value, valid_answer: bool) -> None:
        if self.screen == "question":
            if action == "select" and valid_answer:
                self.selected = value
            elif action == "confirm" and self.selected is not None:
                self._lock_in()
            elif action == "walk":
                self._walk_away()
            elif action == "lifeline" and isinstance(value, str) and self.lifelines.get(value):
                self.lifelines[value] = False
                {"fifty": self._use_fifty, "audience": self._use_audience, "phone": self._use_phone}[value]()
        elif self.screen == "phone_pick" and action == "pick_friend" and value in self._helpers():
            self.cancel_timer("helper")
            self._phone_friend(value)

    def on_player_away(self, pid: str) -> None:
        if self.screen == "phone_call" and pid == self.friend:
            self._close_call(self.name(pid), None)

    # --- Widoki ------------------------------------------------------------

    def _main_timer(self) -> Optional[dict]:
        if self.screen in ("question", "audience", "phone_pick", "phone_call", "qualify"):
            return self.timer_view()
        return None

    def view_tv(self) -> dict:
        view = {
            "hot": self.pinfo(self.hot),
            "level": self.level,
            "ladder": [money(a) for a in LADDER],
            "guaranteed": list(GUARANTEED),
            "lifelines": self.lifelines,
            "selected": self.selected,
            "outcome": self.outcome,
            "poll": self.poll,
            "call": self.call,
            "friend": self.pinfo(self.friend),
            "timer": self._main_timer(),
            "helperTimer": self.timer_view("helper"),
            "votesIn": len(self.votes),
            "qualifyIn": len(self.qualify_answers),
            "qualifyTotal": len(self.waiting),
            "qualifyWinner": self.qualify_winner,
            "earned": money(self.earned.get(self.hot, 0)) if self.hot else "",
            "remaining": len(self.waiting),
            "mode": "seat",
            "bets": {"right": sum(1 for s, _ in self.bets.values() if s == "right"),
                     "wrong": sum(1 for s, _ in self.bets.values() if s == "wrong")},
            "betResults": self.bet_results if self.screen in ("reveal", "turn_end") else None,
        }
        if self.q:
            revealed = self.screen in ("reveal", "turn_end", "qualify_reveal")
            view["q"] = {
                "text": self.q.text,
                "options": [{"label": o, "hidden": i in self.hidden} for i, o in enumerate(self.q.options)],
                "correct": self.q.correct if revealed else None,
            }
        return view

    def _answer_labels(self) -> list[str]:
        return ["" if i in self.hidden else label for i, label in enumerate(self.q.options)]

    def _answer_block(self, action: str, selected: Optional[int] = None) -> dict:
        states = {i: "gone" for i in self.hidden}
        if selected is not None:
            states[selected] = "selected"
        return options(action, self._answer_labels(), states=states)

    def _hot_view(self) -> dict:
        prize = f"Pytanie za {money(LADDER[self.level])}"
        if self.screen == "question":
            blocks = [self._answer_block("select", self.selected)]
            if self.poll:
                blocks.append(msg("Publiczność: " + "  ".join(
                    f"{LETTERS[i]} {p}%" for i, p in enumerate(self.poll) if i not in self.hidden)))
            if self.call:
                said = LETTERS[self.call["choice"]] if self.call["choice"] is not None else "nie wie"
                blocks.append(msg(f'{self.call["who"]}: {said}'))
            blocks.append(buttons(
                btn("confirm", "To moja ostateczna odpowiedź", style="primary", disabled=self.selected is None),
            ))
            blocks.append(buttons(
                btn("lifeline", "50:50", v="fifty", disabled=not self.lifelines["fifty"], style="small"),
                btn("lifeline", "Publiczność", v="audience", disabled=not self.lifelines["audience"], style="small"),
                btn("lifeline", "Telefon", v="phone", disabled=not self.lifelines["phone"], style="small"),
            ))
            walk = money(LADDER[self.level - 1]) if self.level else "0 zł"
            blocks.append(buttons(btn("walk", f"Wycofuję się z kwotą {walk}", style="ghost")))
            return self.pv(*blocks, sub=prize, prompt=self.q.text, timer=self._main_timer(),
                           lifeRow=True)
        if self.screen == "locked":
            return self.pv(msg("Sprawdzamy…", big=True), sub=prize)
        if self.screen == "reveal":
            tone, text = {
                "right": ("good", "Dobrze!"),
                "wrong": ("bad", f"Niestety. Zabierasz {money(self.earned.get(self.hot, 0))}."),
                "walked": ("info", f"Wycofujesz się z kwotą {money(self.earned.get(self.hot, 0))}."),
            }[self.outcome]
            return self.pv(msg(text, tone, big=True), sub=prize)
        if self.screen == "audience":
            return self.pv(msg("Publiczność głosuje…", big=True), sub=prize)
        if self.screen == "phone_pick":
            return self.pv(msg("Do kogo dzwonisz?"), buttons(*[
                btn("pick_friend", self.name(p), v=p, color=self.s.pinfo(p)["color"]) for p in self._helpers()
            ]), sub=prize, timer=self.timer_view("helper"))
        if self.screen == "phone_call":
            who = self.name(self.friend) if self.friend else "ekspert"
            return self.pv(msg(f"Rozmowa: {who}. Możecie rozmawiać na głos!", big=True), sub=prize,
                           timer=self.timer_view("helper"))
        if self.screen == "turn_end":
            return self.pv(msg(f"Twoja wygrana: {money(self.earned.get(self.hot, 0))}", "good", big=True))
        return self.pv(msg("Siadasz na fotelu!", "good", big=True))

    def view_player(self, pid: str) -> dict:
        if pid == self.hot:
            return self._hot_view()
        if self.screen == "qualify" and pid in self.waiting:
            if pid in self.qualify_answers:
                return self.pv(msg("Odpowiedź przyjęta. Czekamy na resztę.", big=True))
            return self.pv(options("qualify", self.q.options), sub="Pytanie eliminacyjne",
                           prompt=self.q.text, timer=self.timer_view())
        if self.screen == "audience" and pid not in self.votes:
            return self.pv(self._answer_block("vote"), sub="Jesteś w publiczności: zagłosuj!",
                           prompt=self.q.text, timer=self.timer_view("helper"))
        if self.screen == "phone_call" and pid == self.friend:
            return self.pv(self._answer_block("friend_answer"),
                           buttons(btn("friend_answer", "Nie wiem", style="ghost")),
                           sub=f"Dzwoni {self.name(self.hot)}!", prompt=self.q.text,
                           timer=self.timer_view("helper"))
        if self.screen == "qualify" or not self.hot:
            return self.pv(msg("Trwają eliminacje. Patrz na telewizor.", big=True))
        sub = self._spectator_sub(pid)
        if pid in self.chips and self._betting_open():
            return self.pv(*self._bet_blocks(pid), sub=sub, prompt=self.q.text)
        if pid in self.chips and self.screen in ("reveal", "turn_end") and self.bet_results:
            mine = next((r for r in self.bet_results if r["player"]["id"] == pid), None)
            if mine:
                delta = mine["delta"]
                text = f"+{delta} żetonów!" if delta > 0 else f"{delta} żetonów." if delta < 0 else "Zakład zwrócony."
                return self.pv(msg(text, "good" if delta > 0 else "bad" if delta < 0 else "info", big=True), sub=sub)
        return self.pv(msg(f"Na fotelu: {self.name(self.hot)}.", big=True), sub=sub)

    def _spectator_sub(self, pid: str) -> str:
        parts = []
        if pid in self.chips:
            parts.append(f"Żetony: {self.chips[pid]}")
        if pid in self.earned:
            parts.append(f"Wygrana: {money(self.earned[pid])}")
        return "  ·  ".join(parts)

    def _bet_blocks(self, pid: str) -> list[dict]:
        hot = self.name(self.hot)
        prize = money(LADDER[self.level])
        if pid in self.bets:
            side, stake = self.bets[pid]
            what = "dobrą odpowiedź" if side == "right" else "pomyłkę"
            return [msg(f"Obstawiasz {what} za {stake} żetonów. Trzymaj kciuki!", big=True)]
        stakes = self._stakes(pid)
        if not stakes:
            return [msg(f"Na fotelu: {hot}. Żetony się skończyły, ale kibicować wolno!", big=True)]
        blocks = []
        if self.screen == "audience":
            blocks.append(msg("Głos oddany. Możesz jeszcze obstawić."))
        blocks.append(msg(f"Czy {hot} odpowie dobrze na pytanie za {prize}? Obstaw żetony."))
        for side, label in (("right", "Odpowie dobrze"), ("wrong", "Pomyli się")):
            blocks.append(msg(label, "good" if side == "right" else "bad"))
            blocks.append(buttons(*[
                btn("bet", "Va banque" if s == self.chips[pid] and s not in STAKES else str(s), v=[side, s], style="small")
                for s in stakes
            ]))
        return blocks
