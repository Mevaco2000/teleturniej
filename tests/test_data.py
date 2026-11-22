"""Poprawność baz treści: błąd w danych wyszedłby dopiero w trakcie zabawy."""
import json
from collections import Counter
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_questions_are_well_formed():
    questions = load("questions.json")
    for q in questions:
        options = [q["a"], *q["w"]]
        assert len(q["w"]) == 3, q["q"]
        assert len(set(options)) == 4, q["q"]
        assert q["d"] in (1, 2, 3, 4), q["q"]
        assert all(o.strip() == o and o for o in options), q["q"]
    texts = Counter(q["q"] for q in questions)
    assert not [t for t, n in texts.items() if n > 1]


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4])
def test_each_difficulty_has_enough_questions(difficulty):
    assert sum(q["d"] == difficulty for q in load("questions.json")) >= 50


def test_familiada_boards_are_playable():
    boards = load("familiada.json")
    assert len(boards) >= 30
    for board in boards:
        labels = [a[0] for a in board["answers"]]
        everything = labels + board["decoys"]
        assert len(set(everything)) == len(everything), board["q"]
        assert 5 <= len(labels) <= 7, board["q"]
        assert sum(a[1] for a in board["answers"]) <= 100, board["q"]
        assert len(board["decoys"]) >= 3, board["q"]


def test_floor_categories_are_playable():
    categories = load("floor.json")
    assert len(categories) >= 16, "plansza 16 pól wymaga 16 różnych kategorii"
    assert len({c["name"] for c in categories}) == len(categories)
    for category in categories:
        items = category["items"]
        assert len(items) >= 14, category["name"]
        answers = [i["a"] for i in items]
        assert len(set(answers)) == len(answers), (category["name"], Counter(answers).most_common(1))
        assert all(a.strip() == a for a in answers), category["name"]
        for item in items:
            assert item.get("c") or item.get("flag"), category["name"]
            if item.get("c"):
                assert item["c"].casefold() != item["a"].casefold(), f"wskazówka zdradza odpowiedź: {item}"


def test_songs_are_well_formed():
    songs = load("songs.json")
    assert len(songs) >= 100
    keys = Counter((s["artist"], s["title"]) for s in songs)
    assert not [k for k, n in keys.items() if n > 1]
    for song in songs:
        assert song["lang"] in ("pl", "en")
        assert song["decade"] in ("old", "80", "90", "00", "10", "20")
        assert isinstance(song.get("instr", 1), int) and song.get("instr", 1) > 0, song
    for category in ("old", "80", "90", "00", "10", "20"):
        assert sum(s["decade"] == category for s in songs) >= 6, category
    # Polskie wersje instrumentalne pochodzą z albumów, których wyszukiwarka nie dopasuje.
    assert sum("instr" in s for s in songs if s["lang"] == "pl") >= 40
    assert len({s["instr"] for s in songs if "instr" in s}) == sum("instr" in s for s in songs)


def test_melodies_use_valid_notes():
    melodies = load("melodies.json")
    assert len(melodies) >= 10
    for melody in melodies:
        assert melody["tempo"] > 0
        for note, beats in melody["notes"]:
            assert beats > 0
            assert note == "R" or (note[0] in "ABCDEFG" and note[-1].isdigit()), melody["title"]
