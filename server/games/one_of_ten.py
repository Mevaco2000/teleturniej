"""1 z 10: runda po dwa pytania, runda wskazywania i finał na punkty."""
from __future__ import annotations

from typing import Optional

from .base import Game, btn, buttons, buzz, msg, options

FINALISTS = 3
START_LIVES = 3
ROUND2_LIMIT = 50
FINAL_LIMIT = 30
PICK_SECONDS = 10
BUZZ_SECONDS = 12
REVEAL_SECONDS = 3.5


class OneOfTen(Game):
    id = "one_of_ten"
    title = "1 z 10"
    tagline = "Trzy szanse. Jeden zwycięzca."
    min_players = 1
    rules = [
        "Każdy ma trzy szanse. Zła odpowiedź zabiera jedną.",
        "Runda 1: każdy dostaje po dwa pytania.",
        "Runda 2: kto odpowie dobrze, wskazuje kolejną osobę. Gra toczy się, aż zostanie trójka.",
        "Finał: zgłaszasz się najszybciej, a po dobrej odpowiedzi bierzesz pytanie na siebie (+20) lub wskazujesz rywala.",
    ]
    option_defs = [{
        "key": "time",
        "label": "Czas na odpowiedź",
        "default": 15,
        "choices": [{"v": 10, "l": "10 s"}, {"v": 15, "l": "15 s"}, {"v": 20, "l": "20 s"}],
    }]

    def start(self) -> None:
        self.lives = {p: START_LIVES for p in self.roster}
        self.points = {p: 0 for p in self.roster}
        self.finalists: list[str] = []
        self.knocked_out: list[str] = []
        self.round = 1
        self.q = None
        self.answerer: Optional[str] = None
        self.picker: Optional[str] = None
        self.pointer: Optional[str] = None
        self.result: Optional[dict] = None
        self.value = 10
        self.asked = 0
        self.final_asked = 0
        order = list(self.roster)
        self.rng.shuffle(order)
        self.queue = order + order
        self.screen = "round"
        self.set_timer(4, self._next_round1)

    # --- Wspólne -----------------------------------------------------------

    def _alive(self) -> list[str]:
        pool = self.finalists if self.round == 3 else self.roster
        return [p for p in pool if self.lives[p] > 0]

    def _ask(self, pid: str, value: int = 10, question=None) -> None:
        self.answerer = pid
        self.value = value
        if question is None:
            difficulty = {1: 1, 2: 2, 3: self.rng.choice((2, 3))}[self.round]
            question = self.s.content.question(difficulty)
        self.q = question
        self.result = None
        self.asked += 1
        self.screen = "ask"
        self.set_timer(self.opts["time"], lambda: self._resolve(None))

    def _resolve(self, chosen: Optional[int]) -> None:
        self.cancel_timer()
        correct = chosen == self.q.correct
        self.result = {"correct": correct, "chosen": chosen}
        if correct:
            self.fx("good")
            if self.round == 3:
                self.points[self.answerer] += self.value
        else:
            self.fx("bad")
            self.lives[self.answerer] -= 1
            if self.lives[self.answerer] == 0:
                self.knocked_out.append(self.answerer)
        self.screen = "reveal"
        self.set_timer(REVEAL_SECONDS, lambda: self._after_answer(correct))

    def _after_answer(self, correct: bool) -> None:
        if self.round == 1:
            self._next_round1()
        elif self.round == 2:
            self._after_round2(correct)
        else:
            self._after_final(correct)

    # --- Runda 1 -----------------------------------------------------------

    def _next_round1(self) -> None:
        if self.queue:
            self._ask(self.queue.pop(0))
        elif len(self.roster) <= FINALISTS:
            self._start_final()
        else:
            self.round = 2
            self.picker = None
            self.screen = "round"
            self.set_timer(4, self._start_pick)

    # --- Runda 2 -----------------------------------------------------------

    def _after_round2(self, correct: bool) -> None:
        if len(self._alive()) <= FINALISTS or self.asked >= ROUND2_LIMIT:
            self._start_final()
            return
        if correct:
            self.picker = self.answerer
        self._start_pick()

    def _start_pick(self) -> None:
        alive = self._alive()
        if self.picker not in alive:
            self.picker = self.rng.choice(alive)
        self.answerer = None
        self.q = None
        self.result = None
        self.screen = "pick"
        self.set_timer(PICK_SECONDS, self._pick_random)

    def _pick_random(self) -> None:
        targets = [p for p in self._alive() if p != self.picker]
        self._ask(self.rng.choice(targets))

    # --- Finał -------------------------------------------------------------

    def _start_final(self) -> None:
        alive = self._alive()
        self.rng.shuffle(alive)
        alive.sort(key=lambda p: -self.lives[p])
        self.finalists = alive[:FINALISTS]
        for pid in alive[FINALISTS:]:
            self.lives[pid] = 0
            self.knocked_out.append(pid)
        self.round = 3
        for pid in self.finalists:
            self.lives[pid] = START_LIVES
        self.picker = None
        self.screen = "round"
        self.set_timer(4, self._start_buzz)

    def _final_over(self) -> bool:
        # W pojedynkę finał trwa, dopóki gracz ma szanse; z rywalami do ostatniego na placu.
        needed = 2 if len(self.finalists) > 1 else 1
        return len(self._alive()) < needed or self.final_asked >= FINAL_LIMIT

    def _start_buzz(self) -> None:
        if self._final_over():
            self._finish()
            return
        self.final_asked += 1
        self.q = self.s.content.question(self.rng.choice((2, 3)))
        self.answerer = None
        self.picker = None
        self.pointer = None
        self.result = None
        self.screen = "buzz"
        self.set_timer(BUZZ_SECONDS, self._no_buzz)

    def _no_buzz(self) -> None:
        self.result = {"correct": None, "chosen": None}
        self.screen = "reveal"
        self.set_timer(REVEAL_SECONDS, self._start_buzz)

    def _after_final(self, correct: bool) -> None:
        if self._final_over():
            self._finish()
        elif correct:
            self._start_choice(self.answerer)
        elif self.pointer and self.lives[self.pointer] > 0:
            self._start_choice(self.pointer)
        else:
            self._start_buzz()

    def _start_choice(self, pid: str) -> None:
        self.picker = pid
        self.answerer = None
        self.q = None
        self.result = None
        self.screen = "choice"
        self.set_timer(PICK_SECONDS, self._choice_timeout)

    def _choice_timeout(self) -> None:
        targets = [p for p in self._alive() if p != self.picker]
        if targets:
            self._point_at(self.rng.choice(targets))
        else:
            self._start_buzz()

    def _point_at(self, target: str) -> None:
        self.pointer = self.picker
        self.final_asked += 1
        self._ask(target, 10)

    def _finish(self) -> None:
        bonus = {p: self.lives[p] * 10 for p in self.finalists}
        for pid, extra in bonus.items():
            self.points[pid] += extra
        ranking = []
        for pid in sorted(self.finalists, key=lambda p: -self.points[p]):
            info = self.s.pinfo(pid)
            ranking.append({"id": pid, "name": info["name"], "color": info["color"],
                            "score": self.points[pid], "label": f"{self.points[pid]} pkt"})
        out_of_final = [p for p in reversed(self.knocked_out) if p not in self.finalists]
        for depth, pid in enumerate(out_of_final):
            info = self.s.pinfo(pid)
            ranking.append({"id": pid, "name": info["name"], "color": info["color"],
                            "score": -1 - depth, "label": "poza finałem"})
        self.finish(ranking, note="Do wyniku doliczono po 10 pkt za każdą zachowaną szansę.")

    # --- Akcje -------------------------------------------------------------

    def on_action(self, pid: str, action: str, m: dict) -> None:
        value = m.get("v")
        if action == "answer" and self.screen == "ask" and pid == self.answerer:
            if isinstance(value, int) and 0 <= value < 4:
                self._resolve(value)
        elif action == "point" and pid == self.picker and self.screen in ("pick", "choice"):
            if value in self._alive() and value != pid:
                self.cancel_timer()
                if self.screen == "pick":
                    self._ask(value)
                else:
                    self._point_at(value)
        elif action == "self_take" and self.screen == "choice" and pid == self.picker:
            self.cancel_timer()
            self.pointer = None
            self.final_asked += 1
            self._ask(pid, 20)
        elif action == "buzz" and self.screen == "buzz" and pid in self._alive():
            self.fx("buzz")
            self._ask(pid, 10, self.q)

    # --- Widoki ------------------------------------------------------------

    def view_tv(self) -> dict:
        pool = self.finalists if self.round == 3 else self.roster
        players = []
        for pid in pool:
            info = self.s.pinfo(pid)
            players.append({**info, "lives": self.lives[pid], "points": self.points[pid],
                            "active": pid in (self.answerer, self.picker)})
        view = {
            "round": self.round,
            "players": players,
            "answerer": self.pinfo(self.answerer),
            "picker": self.pinfo(self.picker),
            "value": self.value,
            "result": self.result,
            "timer": self.timer_view() if self.screen in ("ask", "buzz", "pick", "choice") else None,
        }
        if self.q:
            view["q"] = {
                "text": self.q.text,
                "category": self.q.category,
                "options": self.q.options if self.screen != "buzz" else None,
                "correct": self.q.correct if self.screen == "reveal" else None,
            }
        return view

    def _lives_label(self, pid: str) -> str:
        if pid not in self.lives:
            return ""
        return "Szanse: " + "●" * self.lives[pid] + "○" * (START_LIVES - self.lives[pid])

    def view_player(self, pid: str) -> dict:
        sub = self._lives_label(pid)
        if self.round == 3 and pid in self.finalists:
            sub += f"  ·  {self.points[pid]} pkt"
        out = self.lives.get(pid, 0) <= 0
        if self.screen == "ask" and pid == self.answerer:
            return self.pv(options("answer", self.q.options), sub=sub, prompt=self.q.text,
                           timer=self.timer_view())
        if self.screen == "pick" and pid == self.picker:
            return self.pv(msg("Wskaż, kto odpowiada."), self._target_buttons(pid), sub=sub,
                           timer=self.timer_view())
        if self.screen == "choice" and pid == self.picker:
            blocks = [msg("Dobra odpowiedź! Co dalej?"),
                      buttons(btn("self_take", "Biorę na siebie (+20)", style="primary"))]
            if any(t != pid for t in self._alive()):
                blocks.append(self._target_buttons(pid))
            return self.pv(*blocks, sub=sub, timer=self.timer_view())
        if self.screen == "buzz" and pid in self._alive():
            return self.pv(buzz(), sub=sub, prompt=self.q.text, timer=self.timer_view())
        if self.screen == "reveal" and pid == self.answerer and self.result:
            good = self.result["correct"]
            return self.pv(msg("Dobrze!" if good else "Niestety, źle.", "good" if good else "bad", big=True), sub=sub)
        if out:
            return self.pv(msg("Odpadasz z tej gry. Kibicuj na telewizorze!", big=True), sub=sub)
        return self.pv(msg(self._waiting_text(), big=True), sub=sub)

    def _target_buttons(self, pid: str) -> dict:
        return buttons(*[
            btn("point", self.name(t), v=t, color=self.s.pinfo(t)["color"],
                hint=f"szanse: {self.lives[t]}")
            for t in self._alive() if t != pid
        ])

    def _waiting_text(self) -> str:
        if self.screen == "ask":
            return f"Odpowiada {self.name(self.answerer)}."
        if self.screen in ("pick", "choice"):
            return f"Wybiera {self.name(self.picker)}."
        if self.screen == "round":
            return {1: "Runda 1", 2: "Runda 2", 3: "Finał!"}[self.round]
        return "Patrz na telewizor."
