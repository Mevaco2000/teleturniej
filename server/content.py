"""Bazy pytań. Talie są tasowane i nie powtarzają się, dopóki się nie wyczerpią."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Question:
    text: str
    options: list[str]
    correct: int
    category: str
    difficulty: int


class _Deck:
    def __init__(self, items: list, rng: random.Random):
        self.items = list(items)
        self.rng = rng
        self.pile: list = []

    def draw(self):
        if not self.pile:
            self.pile = list(self.items)
            self.rng.shuffle(self.pile)
        return self.pile.pop()


class Content:
    def __init__(self, data_dir: Path, rng: random.Random):
        self.rng = rng
        questions = self._load(data_dir / "questions.json")
        self.question_decks = {
            d: _Deck([q for q in questions if q["d"] == d], rng) for d in (1, 2, 3, 4)
        }
        self.familiada_deck = _Deck(self._load(data_dir / "familiada.json"), rng)
        self.floor = self._load(data_dir / "floor.json")

    @staticmethod
    def _load(path: Path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def question(self, difficulty: int) -> Question:
        raw = self.question_decks[difficulty].draw()
        options = [raw["a"], *raw["w"]]
        self.rng.shuffle(options)
        return Question(raw["q"], options, options.index(raw["a"]), raw.get("c", ""), difficulty)

    def familiada(self) -> dict:
        return self.familiada_deck.draw()

    def floor_categories(self, count: int) -> list[dict]:
        pool = list(self.floor)
        self.rng.shuffle(pool)
        return [pool[i % len(pool)] for i in range(count)]
