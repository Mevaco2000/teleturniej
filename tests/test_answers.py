"""Ocena odpowiedzi mówionych: odmiana, liczby słownie, dodatki i próba kontrolna z błędnych opcji."""
import json
from pathlib import Path

import pytest

from server.answers import answerable, fold_text, is_pass, judge, parse, spoken_texts, voice_ready

DATA = Path(__file__).resolve().parent.parent / "data"


def ok(said, answer, wrong=(), question="", alts=()):
    return judge([said] if isinstance(said, str) else said, [[answer, *alts]], context=question,
                 distractors=wrong).ok


@pytest.mark.parametrize("said,answer", [
    ("Warszawa", "Warszawa"),
    ("w Warszawie", "Warszawa"),
    ("warszawa", "Warszawa"),
    ("Krakow", "Kraków"),
    ("chyba to będzie Kraków", "Kraków"),
    ("myślę, że Mikołaj Kopernik", "Mikołaj Kopernik"),
    ("Kopernik", "Mikołaj Kopernik"),
    ("Kopernika", "Mikołaj Kopernik"),
    ("Chrobry", "Bolesław Chrobry"),
    ("Bolesława Chrobrego", "Bolesław Chrobry"),
    ("Morze Śródziemne", "Morze Śródziemne"),
    ("Śródziemne", "Morze Śródziemne"),
    ("Pan Tadeusz", "Pan Tadeusz"),
    ("Tadeusz", "Pan Tadeusz"),
    ("Jan Trzeci Sobieski", "Jan III Sobieski"),
    ("Sobieski", "Jan III Sobieski"),
    ("Nowy York", "Nowy Jork"),
    ("Niedźwiedzie", "Niedźwiedź"),
    ("kawa", "Piję kawę"),
    ("rejkiawik", "Reykjavik"),
    ("Skłodowska", "Maria Skłodowska-Curie"),
    ("Sputnik", "Sputnik 1"),
])
def test_accepts_natural_variants(said, answer):
    assert ok(said, answer)


@pytest.mark.parametrize("said,answer", [
    ("1410", "1410"),
    ("tysiąc czterysta dziesięć", "1410"),
    ("w tysiąc czterysta dziesiątym roku", "1410"),
    ("966", "966"),
    ("dziewięćset sześćdziesiąt sześć", "966"),
    ("osiem", "8"),
    ("ósmy", "8"),
    ("pięćdziesiąt sześć", "56"),
    ("dwa tysiące pierwszego", "2001"),
    ("co cztery lata", "Co 4 lata"),
    ("cztery", "Co 4 lata"),
    ("pierwszego kwietnia", "1 kwietnia"),
    ("pierwszy kwiecień", "1 kwietnia"),
    ("sto stopni", "100°C"),
    ("300 tysięcy kilometrów na sekundę", "300 000 km/s"),
    ("trzysta tysięcy", "300 000 km/s"),
    ("Fiat sto dwadzieścia sześć p", "Fiat 126p"),
    ("126p", "Fiat 126p"),
    ("osiem minut", "8 minut"),
])
def test_numbers_spoken_or_written(said, answer):
    assert ok(said, answer)


@pytest.mark.parametrize("said,answer,wrong", [
    ("1420", "1410", ["1385", "1569", "1525"]),
    ("tysiąc czterysta dwadzieścia", "1410", []),
    ("Austria", "Australia", []),
    ("Iran", "Irak", []),
    ("Słowacja", "Słowenia", []),
    ("Mars", "Marsylia", []),
    ("Wenus", "Wenecja", []),
    ("Bolesław", "Bolesław Chrobry", ["Bolesław Krzywousty", "Mieszko I", "Kazimierz Wielki"]),
    ("Fiat", "Fiat 126p", ["Fiat 125p", "Polonez", "Syrena"]),
    ("Mieszko", "Mieszko I", ["Mieszko II", "Bolesław Chrobry", "Kazimierz Odnowiciel"]),
    ("Warszawa Kraków Gdańsk Poznań", "Kraków", ["Warszawa", "Gdańsk", "Poznań"]),
    ("Paryż Londyn Berlin Rzym", "Paryż", []),
    ("1410 albo 1420", "1410", []),
    ("Ocean", "Ocean Spokojny", ["Ocean Atlantycki", "Ocean Indyjski", "Ocean Arktyczny"]),
    ("Kot", "Kotlet", []),
    ("Ra", "Rak", []),
])
def test_rejects_wrong_or_hedged_answers(said, answer, wrong):
    assert not ok(said, answer, wrong)


def test_any_recognition_alternative_can_match():
    assert ok(["Kopenhaga mów", "Kopenhaga"], "Kopenhaga")
    assert ok(["paris", "Paryż"], "Paryż")


def test_words_from_the_question_do_not_count_as_hedging():
    assert ok("stolica Francji to Paryż na pewno", "Paryż", question="Stolica: Francja")


def test_aliases_are_accepted():
    assert ok("Pacyfik", "Ocean Spokojny", alts=["Pacyfik"])
    assert ok("USA", "Stany Zjednoczone", alts=["USA", "Ameryka"])


def test_filler_only_is_empty_not_wrong():
    verdict = judge(["yyy", "eee no"], [["Warszawa"]])
    assert not verdict.ok and verdict.empty
    verdict = judge(["Gdańsk"], [["Warszawa"]])
    assert not verdict.ok and not verdict.empty and verdict.heard == "Gdańsk"


def test_lenient_mode_picks_the_matching_board_answer():
    board = [["Ręcznik"], ["Krem do opalania"], ["Okulary przeciwsłoneczne"], ["Koc"]]
    assert judge(["krem"], board, lenient=True).index == 1
    assert judge(["okulary"], board, lenient=True).index == 2
    assert judge(["ręcznika"], board, lenient=True).index == 0
    assert not judge(["narty"], board, lenient=True).ok


def test_pass_words():
    assert is_pass(["pas"])
    assert is_pass(["nie wiem"])
    assert is_pass(["Dalej"])
    assert not is_pass(["Paryż"])
    assert not is_pass(["nie"])


def test_message_text_is_cleaned():
    assert spoken_texts({"v": "  Paryż ", "alts": ["Paryż", "paris", 5, None, "x" * 500]}) == ["Paryż", "paris", "x" * 160]
    assert spoken_texts({"v": None}) == []
    assert spoken_texts({"v": ["a"], "alts": "zle"}) == []


def test_fold_text():
    assert fold_text("Łódź, Gdańsk!") == "lodz gdansk"
    assert fold_text("Jan III Sobieski") == "jan 3 sobieski"
    assert fold_text("9,81 m/s²") == "9.81 m s 2"
    assert parse("Tysiąc dziewięćset osiemdziesiąt dziewięć").nums == ["1989"]


def test_option_style_questions_are_not_answerable():
    assert not answerable("Nietoperz", "Który z tych ssaków potrafi naprawdę latać?")
    assert not answerable("6,02 × 10²³")
    assert not answerable("W kościele Świętego Krzyża w Warszawie")
    assert answerable("Warszawa", "Jaka jest stolica Polski?")


def test_almost_every_question_works_without_options():
    """Na całej bazie: poprawna odpowiedź przechodzi, a błędne opcje nie. Wyjątki dostają opcje."""
    questions = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))
    failing = [q for q in questions if not voice_ready(q["a"], q["q"], q["w"], q.get("alt", []))]
    assert len(failing) <= len(questions) * 0.03, "\n".join(f'{q["q"]} => {q["a"]}' for q in failing)


@pytest.mark.parametrize("answer,wrong", [
    ("Witaminę D", ["Witaminę C", "Witaminę A", "Witaminę B12"]),
    ("Witaminy C", ["Witaminy A", "Witaminy D", "Witaminy K"]),
])
def test_letter_at_the_end_is_significant(answer, wrong):
    assert voice_ready(answer, "", wrong)
    assert ok("witamina d" if "D" in answer else "witamina c", answer, wrong)
    assert not ok("witamina a", answer, wrong)


def test_indistinguishable_questions_fall_back_to_options():
    assert not voice_ready("World Wide Web", "Co oznacza skrót WWW?", ["World Wide Window", "Wide World Web", "Web World Wide"])
    assert not voice_ready("8 minut", "", ["8 sekund", "1 godzinę", "1 dzień"])
    assert not voice_ready("@", "", ["#", "&", "%"])


def test_every_floor_answer_beats_the_rest_of_its_category():
    categories = json.loads((DATA / "floor.json").read_text(encoding="utf-8"))
    problems = []
    for category in categories:
        answers = [i["a"] for i in category["items"]]
        for item in category["items"]:
            others = [a for a in answers if a != item["a"]]
            targets = [[item["a"], *item.get("alt", [])]]
            if not judge([item["a"]], targets, distractors=others).ok:
                problems.append(f'{category["name"]}: {item["a"]}')
    assert not problems, "\n".join(problems)
