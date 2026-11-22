"""The Floor: plansza, pojedynki na zegar szachowy i przejmowanie terytorium.

Boty wypełniają planszę, żeby małe grupy też miały pełną rozgrywkę.
"""
from __future__ import annotations

import math
from typing import Optional

from ..answers import is_pass, judge, spoken_texts
from .base import ANSWERS_OPTION, Game, answer_box, btn, buttons, msg, options

BOT_NAMES = ["Zenek", "Halina", "Mietek", "Grażyna", "Staszek", "Jadzia", "Ziutek", "Krysia",
             "Benek", "Wanda", "Heniek", "Bożena", "Lolek", "Irena", "Rysiek", "Tola"]
BOT_COLORS = ["#7f8ea3", "#8d99ae", "#6c7a89", "#95a5a6"]
BOT_ACCURACY = 0.72
BOT_MIN_DELAY = 2.0
BOT_MAX_DELAY = 5.5
BOARD_SECONDS = 4
CHALLENGER_SECONDS = 3.5
PICK_SECONDS = 15
DUEL_INTRO_SECONDS = 4
DUEL_END_SECONDS = 5.5
WRONG_LOCK_SECONDS = 2.0
PASS_LOCK_SECONDS = 3.0


def grid_shape(tiles: int) -> tuple[int, int]:
    """Kolumny i wiersze planszy: jak najmniej dziur i proporcje zbliżone do ekranu TV."""
    def badness(rows: int) -> float:
        cols = math.ceil(tiles / rows)
        return (cols * rows - tiles) * 2 + abs(cols / rows - 16 / 9)

    rows = min(range(1, tiles + 1), key=badness)
    return math.ceil(tiles / rows), rows


class Owner:
    def __init__(self, oid: str, name: str, color: str, bot: bool, category: dict):
        self.id = oid
        self.name = name
        self.color = color
        self.bot = bot
        self.category = category
        self.tiles: set[int] = set()

    @property
    def alive(self) -> bool:
        return bool(self.tiles)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color, "bot": self.bot,
                "category": self.category["name"], "tiles": len(self.tiles)}


class Floor(Game):
    id = "floor"
    title = "The Floor"
    tagline = "Podbij całą planszę, pole po polu."
    min_players = 1
    rules = [
        "Każdy zaczyna z jednym polem i własną kategorią.",
        "Wylosowany gracz wyzywa sąsiada. Pojedynek toczy się w kategorii obrońcy.",
        "Zegar szachowy: dobra odpowiedź przełącza czas na rywala. Kto pierwszy zejdzie do zera, odpada.",
        "Odpowiadasz z głowy: mówisz do telefonu (mikrofon słucha przez cały Twój czas) albo wpisujesz. Słowo „pas” losuje nowe hasło.",
        "Zwycięzca przejmuje pola. Wygrywa ostatni na planszy.",
    ]
    option_defs = [
        ANSWERS_OPTION,
        {"key": "tiles", "label": "Rozmiar planszy", "default": 0, "choices": [
            {"v": 0, "l": "Tylko gracze"}, {"v": 6, "l": "6 pól"}, {"v": 9, "l": "9 pól"},
            {"v": 12, "l": "12 pól"}, {"v": 16, "l": "16 pól"},
        ]},
        {"key": "clock", "label": "Czas w pojedynku", "default": 45, "choices": [
            {"v": 30, "l": "30 s"}, {"v": 45, "l": "45 s"}, {"v": 60, "l": "60 s"},
        ]},
    ]

    def start(self) -> None:
        humans = list(self.roster)
        self.rng.shuffle(humans)
        total = max(self.opts["tiles"], len(humans), 2)
        self.cols, self.rows = grid_shape(total)
        self.tile_count = total
        categories = self.s.content.floor_categories(total)
        self.owners: dict[str, Owner] = {}
        bot_names = self.rng.sample(BOT_NAMES, total - len(humans)) if total > len(humans) else []
        for index, pid in enumerate(humans):
            info = self.s.pinfo(pid)
            self.owners[pid] = Owner(pid, info["name"], info["color"], False, categories[index])
        for index, name in enumerate(bot_names):
            oid = f"bot{index}"
            color = BOT_COLORS[index % len(BOT_COLORS)]
            self.owners[oid] = Owner(oid, f"{name} (bot)", color, True, categories[len(humans) + index])
        ids = list(self.owners)
        self.rng.shuffle(ids)
        self.board: list[str] = ids
        for tile, oid in enumerate(self.board):
            self.owners[oid].tiles.add(tile)
        self.challenged: set[str] = set()
        self.challenger: Optional[str] = None
        self.defender: Optional[str] = None
        self.duel_category: Optional[dict] = None
        self.deck: list[dict] = []
        self.card: Optional[dict] = None
        self.clocks: dict[str, float] = {}
        self.active: Optional[str] = None
        self.locked = False
        self.feedback: Optional[dict] = None
        self.winner: Optional[str] = None
        self.eliminated: list[str] = []
        self.card_id = 0
        self.screen = "board"
        self.set_timer(BOARD_SECONDS, self._next_challenger)

    # --- Plansza -----------------------------------------------------------

    def _neighbours_of_tile(self, tile: int) -> list[int]:
        col, row = tile % self.cols, tile // self.cols
        found = []
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c, r = col + dc, row + dr
            index = r * self.cols + c
            if 0 <= c < self.cols and 0 <= r < self.rows and index < self.tile_count:
                found.append(index)
        return found

    def _rivals(self, oid: str) -> list[str]:
        rivals = []
        for tile in self.owners[oid].tiles:
            for other in self._neighbours_of_tile(tile):
                owner = self.board[other]
                if owner != oid and owner not in rivals:
                    rivals.append(owner)
        return rivals

    def _alive(self) -> list[Owner]:
        return [o for o in self.owners.values() if o.alive]

    def _next_challenger(self) -> None:
        alive = self._alive()
        humans = [o.id for o in alive if not o.bot]
        if len(alive) <= 1 or not humans:
            self._finish()
            return
        fresh = [p for p in humans if p not in self.challenged]
        if not fresh:
            self.challenged.clear()
            fresh = humans
        self.challenger = self.rng.choice(fresh)
        self.challenged.add(self.challenger)
        self.defender = None
        self.feedback = None
        self.card = None
        self.winner = None
        self.screen = "challenger"
        self.fx("reveal")
        self.set_timer(CHALLENGER_SECONDS, self._start_pick)

    def _start_pick(self) -> None:
        self.screen = "pick"
        self.set_timer(PICK_SECONDS, lambda: self._begin_duel(self.rng.choice(self._rivals(self.challenger))))

    def _begin_duel(self, defender: str) -> None:
        self.cancel_timer()
        self.defender = defender
        self.duel_category = self.owners[defender].category
        self.deck = []
        self.clocks = {self.challenger: float(self.opts["clock"]), defender: float(self.opts["clock"])}
        self.active = self.challenger
        self.locked = False
        self.screen = "duel_intro"
        self.fx("lock")
        self.set_timer(DUEL_INTRO_SECONDS, self._start_duel)

    # --- Pojedynek ---------------------------------------------------------

    def _start_duel(self) -> None:
        self.screen = "duel"
        self._new_card()
        self._run_clock()

    def _new_card(self) -> None:
        category = self.duel_category
        if not self.deck:
            self.deck = list(category["items"])
            self.rng.shuffle(self.deck)
        item = self.deck.pop()
        others = sorted({i["a"] for i in category["items"] if i["a"] != item["a"]})
        answers = list(others)
        self.rng.shuffle(answers)
        labels = [item["a"], *answers[:3]]
        self.rng.shuffle(labels)
        self.card_id += 1
        self.card = {"clue": item.get("c", ""), "flag": item.get("flag"), "prompt": category.get("prompt", ""),
                     "options": labels, "correct": labels.index(item["a"]),
                     "answer": item["a"], "alts": list(item.get("alt", [])), "others": others}
        self.locked = False
        self._schedule_bot()

    def _run_clock(self) -> None:
        self.set_timer(self.clocks[self.active], self._time_out, name="duel", total=float(self.opts["clock"]))

    def _store_clock(self) -> None:
        self.clocks[self.active] = self.time_left("duel")

    def _schedule_bot(self) -> None:
        self.cancel_timer("bot")
        if self.owners[self.active].bot:
            delay = self.rng.uniform(BOT_MIN_DELAY, BOT_MAX_DELAY)
            self.set_timer(delay, self._bot_answers, name="bot")

    def _bot_answers(self) -> None:
        if self.screen != "duel" or self.locked or not self.card:
            return
        if self.rng.random() < BOT_ACCURACY:
            self._answer(self.card["correct"])
        else:
            wrong = [i for i in range(len(self.card["options"])) if i != self.card["correct"]]
            self._answer(self.rng.choice(wrong))

    def _answer(self, index: int) -> None:
        self._judged(index == self.card["correct"], self.card["options"][index])

    def _said(self, texts: list[str]) -> None:
        if is_pass(texts):
            self._pass()
            return
        card = self.card
        verdict = judge(texts, [[card["answer"], *card["alts"]]], context=f'{card["prompt"]} {card["clue"]}',
                        distractors=card["others"])
        if not verdict.empty:
            # Po dobrej odpowiedzi widać na ekranie oficjalny zapis, po złej to, co usłyszał telefon.
            self._judged(verdict.ok, card["answer"] if verdict.ok else verdict.heard)

    def _pass(self) -> None:
        self.feedback = {"who": self.active, "correct": None, "label": "Pas"}
        self._lock_and_redraw(PASS_LOCK_SECONDS)

    def _judged(self, correct: bool, label: str) -> None:
        if correct:
            self.fx("good")
            self.feedback = {"who": self.active, "correct": True, "label": label}
            self._store_clock()
            self.cancel_timer("duel")
            self.active = self.defender if self.active == self.challenger else self.challenger
            self._new_card()
            self._run_clock()
        else:
            self.fx("bad")
            self.feedback = {"who": self.active, "correct": False, "label": label}
            self._lock_and_redraw(WRONG_LOCK_SECONDS)

    def _lock_and_redraw(self, seconds: float) -> None:
        self.locked = True
        self.cancel_timer("bot")
        self.set_timer(seconds, self._new_card, name="lock")

    def _time_out(self) -> None:
        self.clocks[self.active] = 0.0
        self.cancel_timer("bot")
        self.cancel_timer("lock")
        loser = self.owners[self.active]
        winner = self.owners[self.defender if self.active == self.challenger else self.challenger]
        # Zwycięzca zachowuje niewykorzystaną kategorię: pojedynek zużył kategorię obrońcy.
        if winner.id == self.defender:
            winner.category = self.owners[self.challenger].category
        winner.tiles |= loser.tiles
        for tile in loser.tiles:
            self.board[tile] = winner.id
        loser.tiles = set()
        self.eliminated.append(loser.id)
        self.winner = winner.id
        self.card = None
        self.fx("good")
        self.screen = "duel_end"
        self.set_timer(DUEL_END_SECONDS, self._next_challenger)

    def _finish(self) -> None:
        ranking = []
        for owner in sorted(self._alive(), key=lambda o: -len(o.tiles)):
            tiles = len(owner.tiles)
            label = f"{tiles} {'pole' if tiles == 1 else 'pola' if 1 < tiles < 5 else 'pól'}"
            ranking.append({"id": owner.id, "name": owner.name, "color": owner.color,
                            "score": tiles, "label": label})
        for depth, oid in enumerate(reversed(self.eliminated)):
            owner = self.owners[oid]
            ranking.append({"id": oid, "name": owner.name, "color": owner.color,
                            "score": -1 - depth, "label": "poza planszą"})
        self.finish(ranking)

    # --- Akcje -------------------------------------------------------------

    def on_action(self, pid: str, action: str, m: dict) -> None:
        value = m.get("v")
        if action == "challenge" and self.screen == "pick" and pid == self.challenger:
            if value in self._rivals(pid):
                self._begin_duel(value)
        elif self.screen == "duel" and pid == self.active and not self.locked and self.card:
            if action == "answer" and not self.voice and isinstance(value, int) and 0 <= value < len(self.card["options"]):
                self._answer(value)
            elif action == "say" and self.voice:
                texts = spoken_texts(m)
                if texts:
                    self._said(texts)
            elif action == "pass":
                self._pass()

    # --- Widoki ------------------------------------------------------------

    def _clock_view(self, oid: Optional[str]) -> Optional[dict]:
        if not oid or oid not in self.clocks:
            return None
        running = self.screen == "duel" and oid == self.active
        left = self.time_left("duel") if running else self.clocks[oid]
        return {"ms": int(left * 1000), "total": self.opts["clock"] * 1000, "running": running}

    def _card_view(self) -> Optional[dict]:
        if not self.card:
            return None
        return {"clue": self.card["clue"], "flag": self.card["flag"], "prompt": self.card["prompt"],
                "options": None if self.voice else self.card["options"]}

    def view_tv(self) -> dict:
        return {
            "cols": self.cols,
            "rows": self.rows,
            "tiles": [{"owner": oid} for oid in self.board],
            "owners": {oid: owner.public() for oid, owner in self.owners.items()},
            "challenger": self.challenger,
            "defender": self.defender,
            "category": self.duel_category["name"] if self.duel_category else "",
            "active": self.active,
            "clocks": {oid: self._clock_view(oid) for oid in (self.challenger, self.defender) if oid},
            "card": self._card_view(),
            "locked": self.locked,
            "feedback": self.feedback,
            "winner": self.winner,
            "timer": self.timer_view() if self.screen == "pick" else None,
            "rivals": self._rivals(self.challenger) if self.screen == "pick" else [],
        }

    def view_player(self, pid: str) -> dict:
        owner = self.owners.get(pid)
        sub = ""
        if owner:
            count = len(owner.tiles)
            sub = f"Pola: {count}  ·  {owner.category['name']}" if count else "Poza planszą"
        if self.screen == "pick":
            if pid == self.challenger:
                return self.pv(msg("Kogo wyzywasz? Zagracie w jego kategorii."), buttons(*[
                    btn("challenge", self.owners[r].name, v=r, color=self.owners[r].color,
                        hint=self.owners[r].category["name"]) for r in self._rivals(pid)
                ]), sub=sub, timer=self.timer_view())
            return self.pv(msg(f"Wybiera {self.owners[self.challenger].name}.", big=True), sub=sub)
        if self.screen == "duel" and pid in (self.challenger, self.defender):
            clock = self._clock_view(pid)
            if pid != self.active:
                return self.pv(msg("Czas rywala. Przygotuj się!", big=True), sub=sub, clock=clock)
            if self.locked:
                blocks = [msg("Chwila…", "bad", big=True)]
                feedback = self.feedback
                if self.voice and feedback and feedback["who"] == pid and feedback["correct"] is False:
                    blocks.append(msg(f"„{feedback['label']}” to nie to."))
                return self.pv(*blocks, sub=sub, clock=clock)
            card = self.card
            prompt = (f'{card["prompt"]} {card["clue"]}').strip()
            if self.voice:
                block = answer_box(f"c{self.card_id}", sticky=True)
                hint = "Pas (3 s kary) — możesz też powiedzieć „pas”"
            else:
                block = options("answer", card["options"], letters=False)
                hint = "Pas (3 s kary)"
            return self.pv(block, buttons(btn("pass", hint, style="ghost")),
                           sub=sub, prompt=prompt, clock=clock, flag=card["flag"])
        if self.screen == "duel_intro" and pid in (self.challenger, self.defender):
            return self.pv(msg(f'Pojedynek! Kategoria: {self.duel_category["name"]}', "good", big=True), sub=sub)
        if self.screen == "duel_end" and pid in (self.challenger, self.defender):
            won = pid == self.winner
            return self.pv(msg("Wygrywasz pojedynek!" if won else "Odpadasz z planszy.",
                               "good" if won else "bad", big=True), sub=sub)
        if self.screen == "challenger" and pid == self.challenger:
            return self.pv(msg("Wylosowano Ciebie!", "good", big=True), sub=sub)
        return self.pv(msg("Patrz na telewizor.", big=True), sub=sub)
