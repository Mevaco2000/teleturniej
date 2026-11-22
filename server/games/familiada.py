"""Familiada: dwie drużyny, tablica ukrytych odpowiedzi, trzy błędy i przejęcie pytania.

Zamiast pisania odpowiedzi telefon pokazuje listę z pozycjami z tablicy i fałszywkami,
bo bez prowadzącego dopasowywanie odmienionych polskich słów dawałoby niesprawiedliwe błędy.
"""
from __future__ import annotations

from typing import Optional

from .base import Game, buzz, msg, options

MULTIPLIERS = [1, 1, 2, 2, 3, 3, 3]
BUZZ_SECONDS = 12
MAX_DUEL_TRIES = 3
ROUND_INTRO_SECONDS = 4
TEAMS_SECONDS = 6
AFTER_PICK_SECONDS = 2.2
ROUND_END_SECONDS = 7
TEAM_NAMES = ("Czerwoni", "Niebiescy")
TEAM_COLORS = ("#ff5a5f", "#4d96ff")
MAX_TIEBREAKERS = 3


class Familiada(Game):
    id = "familiada"
    title = "Familiada"
    tagline = "Drużyny kontra to, co odpowiedzieli ankietowani."
    # Jedna osoba gra sama w drużynie Czerwonych: bez pojedynku z rywalem i bez przejęcia.
    min_players = 1
    rules = [
        "Dwie drużyny zgadują najpopularniejsze odpowiedzi z ankiety (punkty są szacunkowe).",
        "Pojedynek: po jednej osobie z drużyny. Kto trafi wyżej na tablicy, przejmuje pytanie dla drużyny.",
        "Drużyna odpowiada po kolei. Trzy błędy i pytanie może przejąć przeciwnik.",
        "Kolejne rundy mają mnożniki, więc koniec gry bywa zaskakujący.",
    ]
    option_defs = [
        {"key": "rounds", "label": "Liczba rund", "default": 5, "choices": [
            {"v": 3, "l": "3"}, {"v": 5, "l": "5"}, {"v": 7, "l": "7"},
        ]},
        {"key": "time", "label": "Czas na odpowiedź", "default": 20, "choices": [
            {"v": 15, "l": "15 s"}, {"v": 20, "l": "20 s"}, {"v": 30, "l": "30 s"},
        ]},
    ]

    def start(self) -> None:
        shuffled = list(self.roster)
        self.rng.shuffle(shuffled)
        self.teams: list[list[str]] = [shuffled[0::2], shuffled[1::2]]
        self.scores = [0, 0]
        self.rotation = [0, 0]
        self.round = 0
        self.tiebreakers = 0
        self.question: Optional[dict] = None
        self.answers: list[list] = []
        self.revealed: set[int] = set()
        self.reveal_all = False
        self.choices: list[str] = []
        self.tried: set[int] = set()
        self.strikes = 0
        self.bank = 0
        self.multiplier = 1
        self.control: Optional[int] = None
        self.duelists: list[str] = []
        self.duel_tries = 0
        self.answerer: Optional[str] = None
        self.mode = ""
        self.first_rank: Optional[int] = None
        self.first_team = 0
        self.last_pick: Optional[dict] = None
        self.round_winner: Optional[int] = None
        self.screen = "teams"
        self.set_timer(TEAMS_SECONDS, self._start_round)

    # --- Runda -------------------------------------------------------------

    def _team_of(self, pid: str) -> int:
        return 0 if pid in self.teams[0] else 1

    def _next_member(self, team: int) -> str:
        members = self.teams[team]
        pid = members[self.rotation[team] % len(members)]
        self.rotation[team] += 1
        return pid

    def _start_round(self) -> None:
        planned = self.opts["rounds"]
        self.multiplier = MULTIPLIERS[min(self.round, planned - 1)] if self.round < planned else 1
        self.round += 1
        self.question = self.s.content.familiada()
        self.answers = sorted(self.question["answers"], key=lambda a: -a[1])
        labels = [a[0] for a in self.answers] + list(self.question["decoys"])
        self.rng.shuffle(labels)
        self.choices = labels
        self.revealed = set()
        self.reveal_all = False
        self.tried = set()
        self.strikes = 0
        self.bank = 0
        self.control = None
        self.duel_tries = 0
        self.last_pick = None
        self.round_winner = None
        self.screen = "round"
        self.set_timer(ROUND_INTRO_SECONDS, self._start_duel)

    def _start_duel(self) -> None:
        self.duelists = [self._next_member(t) for t in (0, 1) if self.teams[t]]
        self.first_rank = None
        self.answerer = None
        self.mode = "duel_buzz"
        self.screen = "duel_buzz"
        self.set_timer(BUZZ_SECONDS, lambda: self._duel_first(self.rng.choice(self.duelists)))

    def _duel_first(self, pid: str) -> None:
        self.first_team = self._team_of(pid)
        self._prompt(pid, "duel_first")

    def _prompt(self, pid: str, mode: str) -> None:
        self.answerer = pid
        self.mode = mode
        self.screen = "answer"
        self.set_timer(self.opts["time"], lambda: self._picked(None))

    def _rank_of(self, label: str) -> Optional[int]:
        for rank, (text, _points) in enumerate(self.answers):
            if text == label:
                return rank
        return None

    def _picked(self, index: Optional[int]) -> None:
        self.cancel_timer()
        label = self.choices[index] if index is not None else None
        if index is not None:
            self.tried.add(index)
        rank = self._rank_of(label) if label is not None else None
        points = 0
        if rank is not None:
            self.revealed.add(rank)
            points = self.answers[rank][1]
            self.bank += points
            self.fx("reveal")
        else:
            self.fx("strike")
            if self.mode == "play":
                self.strikes += 1
        self.last_pick = {"player": self.s.pinfo(self.answerer), "label": label, "hit": rank is not None,
                          "points": points}
        handler = {
            "duel_first": self._after_duel_first,
            "duel_second": self._after_duel_second,
            "play": self._after_play,
            "steal": self._after_steal,
        }[self.mode]
        self.screen = "picked"
        self.set_timer(AFTER_PICK_SECONDS, lambda: handler(rank))

    def _after_duel_first(self, rank: Optional[int]) -> None:
        other = next((p for p in self.duelists if self._team_of(p) != self.first_team), None)
        if rank == 0 or other is None:
            self._start_play(self.first_team)
            return
        self.first_rank = rank
        self._prompt(other, "duel_second")

    def _after_duel_second(self, rank: Optional[int]) -> None:
        first = self.first_rank
        if rank is None and first is None:
            self.duel_tries += 1
            if self.duel_tries >= MAX_DUEL_TRIES:
                self._start_play(self.rng.choice((0, 1)))
            else:
                self._start_duel()
            return
        first_wins = rank is None or (first is not None and first < rank)
        self._start_play(self.first_team if first_wins else 1 - self.first_team)

    def _all_revealed(self) -> bool:
        return len(self.revealed) == len(self.answers)

    def _start_play(self, team: int) -> None:
        self.control = team
        self.strikes = 0
        if self._all_revealed():
            self._round_won(team)
        else:
            self._prompt(self._next_member(team), "play")

    def _after_play(self, rank: Optional[int]) -> None:
        if self._all_revealed():
            self._round_won(self.control)
        elif self.strikes >= 3 and not self.teams[1 - self.control]:
            # Nie ma kto przejąć pytania, więc runda kończy się jak po nieudanym przejęciu.
            self._round_won(self.control)
        elif self.strikes >= 3:
            self._prompt(self._next_member(1 - self.control), "steal")
        else:
            self._prompt(self._next_member(self.control), "play")

    def _after_steal(self, rank: Optional[int]) -> None:
        self._round_won(1 - self.control if rank is not None else self.control)

    def _round_won(self, team: int) -> None:
        self.round_winner = team
        self.scores[team] += self.bank * self.multiplier
        self.reveal_all = True
        self.answerer = None
        self.fx("good")
        self.screen = "round_end"
        self.set_timer(ROUND_END_SECONDS, self._after_round)

    def _after_round(self) -> None:
        planned = self.opts["rounds"]
        tied = self.scores[0] == self.scores[1]
        if self.round < planned or (tied and self.tiebreakers < MAX_TIEBREAKERS):
            if self.round >= planned:
                self.tiebreakers += 1
            self._start_round()
        else:
            self._finish()

    def _finish(self) -> None:
        ranking = []
        for team in sorted((t for t in (0, 1) if self.teams[t]), key=lambda t: -self.scores[t]):
            names = ", ".join(self.name(p) for p in self.teams[team])
            ranking.append({
                "name": TEAM_NAMES[team], "color": TEAM_COLORS[team], "score": self.scores[team],
                "label": f"{self.scores[team]} pkt", "members": self.teams[team], "detail": names,
            })
        self.finish(ranking)

    # --- Akcje -------------------------------------------------------------

    def on_action(self, pid: str, action: str, m: dict) -> None:
        value = m.get("v")
        if action == "buzz" and self.screen == "duel_buzz" and pid in self.duelists:
            self.fx("buzz")
            self._duel_first(pid)
        elif action == "pick" and self.screen == "answer" and pid == self.answerer:
            if isinstance(value, int) and 0 <= value < len(self.choices) and value not in self.tried:
                self._picked(value)

    # --- Widoki ------------------------------------------------------------

    def _team_view(self, team: int) -> dict:
        return {
            "name": TEAM_NAMES[team],
            "color": TEAM_COLORS[team],
            "score": self.scores[team],
            "players": [self.s.pinfo(p) for p in self.teams[team]],
        }

    def view_tv(self) -> dict:
        board = []
        for rank, (label, points) in enumerate(self.answers):
            shown = rank in self.revealed
            board.append({
                "n": rank + 1,
                "label": label if shown or self.reveal_all else None,
                "points": points if shown or self.reveal_all else None,
                "earned": shown,
            })
        return {
            "teams": [self._team_view(0), self._team_view(1)],
            "round": self.round,
            "rounds": self.opts["rounds"],
            "multiplier": self.multiplier,
            "question": self.question["q"] if self.question and self.screen != "round" else None,
            "board": board,
            "strikes": self.strikes,
            "bank": self.bank,
            "control": self.control,
            "mode": self.mode,
            "duelists": [self.s.pinfo(p) for p in self.duelists],
            "answerer": self.pinfo(self.answerer),
            "lastPick": self.last_pick,
            "roundWinner": self.round_winner,
            "timer": self.timer_view() if self.screen in ("duel_buzz", "answer") else None,
        }

    def view_player(self, pid: str) -> dict:
        team = self._team_of(pid)
        sub = f"{TEAM_NAMES[team]}  ·  {self.scores[team]} pkt"
        extra = {"accent": TEAM_COLORS[team]}
        if self.screen == "duel_buzz" and pid in self.duelists:
            return self.pv(buzz("ZNAM ODPOWIEDŹ!"), sub=sub, prompt=self.question["q"],
                           timer=self.timer_view(), **extra)
        if self.screen == "answer" and pid == self.answerer:
            states = {i: "disabled" for i in self.tried}
            block = options("pick", self.choices, columns=2, states=states, letters=False)
            label = "Przejęcie! Jedna odpowiedź." if self.mode == "steal" else ""
            blocks = ([msg(label, "good")] if label else []) + [block]
            return self.pv(*blocks, sub=sub, prompt=self.question["q"], timer=self.timer_view(), **extra)
        if self.screen == "teams":
            mates = ", ".join(self.name(p) for p in self.teams[team] if p != pid)
            text = f"Drużyna {TEAM_NAMES[team]}" + (f": grasz z {mates}." if mates else ".")
            return self.pv(msg(text, big=True), sub=sub, **extra)
        if self.screen == "round_end":
            won = self.round_winner == team
            return self.pv(msg("Runda dla Was!" if won else "Runda dla rywali.", "good" if won else "bad", big=True),
                           sub=sub, **extra)
        if self.screen == "picked" and self.last_pick and self.last_pick["player"]["id"] == pid:
            hit = self.last_pick["hit"]
            return self.pv(msg("Jest na tablicy!" if hit else "Nie ma na tablicy.", "good" if hit else "bad", big=True),
                           sub=sub, **extra)
        if self.screen == "answer":
            return self.pv(msg(f"Odpowiada {self.name(self.answerer)}.", big=True), sub=sub, **extra)
        if self.screen == "duel_buzz":
            names = " i ".join(self.name(p) for p in self.duelists)
            return self.pv(msg(f"Pojedynek: {names}.", big=True), sub=sub, **extra)
        return self.pv(msg("Patrz na telewizor.", big=True), sub=sub, **extra)
