"""Tryb „Z głowy”: odpowiedzi mówione lub wpisane zamiast listy opcji."""
from __future__ import annotations

import json

import pytest

from .conftest import Table
from .test_games import advance_until, cue_and_play


def blocks_of(view: dict, kind: str) -> list[dict]:
    return [b for b in view["blocks"] if b["type"] == kind]


def free_question(game, table: Table) -> None:
    """Pytania bez listy opcji to większość bazy; test czeka na takie."""
    advance_until(table, lambda: game.screen == "ask" and game.free)


# --- 1 z 10 ----------------------------------------------------------------


def test_one_of_ten_voice_shows_answer_box_and_hides_options():
    table = Table()
    table.add_players(2)
    table.start("one_of_ten")
    game = table.session.game
    free_question(game, table)
    view = table.view(game.answerer)
    assert blocks_of(view, "answer") and not blocks_of(view, "options")
    assert game.q.answer not in json.dumps(view, ensure_ascii=False)
    tv = table.tv_view()
    assert tv["q"]["options"] is None and tv["q"]["answer"] is None


def test_one_of_ten_spoken_correct_answer_keeps_lives():
    table = Table()
    table.add_players(2)
    table.start("one_of_ten")
    game = table.session.game
    free_question(game, table)
    pid = game.answerer
    table.act(pid, "say", f"chyba {game.q.answer}")
    assert game.result["correct"] is True and game.lives[pid] == 3
    assert table.tv_view()["q"]["answer"] == game.q.answer


def test_one_of_ten_alternative_transcript_can_be_right():
    table = Table()
    table.add_players(2)
    table.start("one_of_ten")
    game = table.session.game
    free_question(game, table)
    table.act(game.answerer, "say", "zupełnie coś innego", alts=[game.q.answer])
    assert game.result["correct"] is True


def test_one_of_ten_filler_is_not_a_wrong_answer():
    table = Table()
    table.add_players(2)
    table.start("one_of_ten")
    game = table.session.game
    free_question(game, table)
    pid = game.answerer
    table.act(pid, "say", "yyy")
    assert game.screen == "ask" and game.lives[pid] == 3
    assert any("Nie usłyszałem" in b["text"] for b in blocks_of(table.view(pid), "msg"))


def test_one_of_ten_wrong_spoken_answer_costs_a_life_and_host_can_accept_it():
    table = Table()
    pids = table.add_players(3)
    table.start("one_of_ten")
    game = table.session.game
    host = table.session.host_id
    advance_until(table, lambda: game.screen == "ask" and game.free and game.answerer != host)
    pid = game.answerer
    table.act(pid, "say", "Zanzibar Mozambik Kilimandżaro")
    assert game.result["correct"] is False and game.lives[pid] == 2
    assert not blocks_of(table.view(pid), "buttons"), "uznać może tylko gospodarz"
    table.act(pid, "accept")
    assert game.lives[pid] == 2
    accept = [i for b in blocks_of(table.view(host), "buttons") for i in b["items"] if i["action"] == "accept"]
    assert accept
    table.act(host, "accept")
    assert game.result["correct"] is True and game.result["accepted"] is True
    assert game.lives[pid] == 3
    table.act(host, "accept")
    assert game.lives[pid] == 3


def test_one_of_ten_accept_brings_player_back_from_knock_out():
    table = Table()
    table.add_players(1)
    table.start("one_of_ten")
    game = table.session.game
    pid = table.session.host_id
    free_question(game, table)
    game.lives[pid] = 1
    table.act(pid, "say", "Zanzibar")
    assert pid in game.knocked_out
    table.act(pid, "accept")
    assert game.lives[pid] == 1 and pid not in game.knocked_out


def test_one_of_ten_option_answers_are_ignored_in_voice_mode():
    table = Table()
    table.add_players(2)
    table.start("one_of_ten")
    game = table.session.game
    free_question(game, table)
    table.act(game.answerer, "answer", game.q.correct)
    assert game.screen == "ask"


def test_one_of_ten_question_that_needs_options_shows_them():
    table = Table()
    table.add_players(2)
    table.start("one_of_ten")
    game = table.session.game
    advance_until(table, lambda: game.screen == "ask")
    game.q.free = False
    game.free = False
    view = table.view(game.answerer)
    assert blocks_of(view, "options")
    table.act(game.answerer, "answer", game.q.correct)
    assert game.result["correct"] is True


# --- Familiada -------------------------------------------------------------


def test_familiada_spoken_answer_is_found_on_the_board():
    table = Table()
    table.add_players(2)
    table.start("familiada")
    game = table.session.game
    advance_until(table, lambda: game.screen == "duel_buzz")
    first = game.duelists[0]
    table.act(first, "buzz")
    assert blocks_of(table.view(first), "answer")
    label = game.answers[0][0]
    table.act(first, "say", label.lower())
    assert 0 in game.revealed and game.last_pick["hit"] and game.last_pick["board"] == label


def test_familiada_repeated_answer_is_not_a_strike():
    table = Table()
    pid = table.add_players(1)[0]
    table.start("familiada")
    game = table.session.game
    advance_until(table, lambda: game.screen == "duel_buzz")
    table.act(pid, "buzz")
    label = game.answers[1][0]
    table.act(pid, "say", label)
    advance_until(table, lambda: game.screen == "answer")
    table.act(pid, "say", label)
    assert game.screen == "answer" and game.strikes == 0
    assert any("już jest na tablicy" in b["text"] for b in blocks_of(table.view(pid), "msg"))
    table.act(pid, "say", "kosmiczny odkurzacz")
    assert game.strikes == 1 and game.last_pick["label"] == "kosmiczny odkurzacz"


# --- The Floor -------------------------------------------------------------


def floor_duel(table: Table):
    game = table.session.game
    advance_until(table, lambda: game.screen == "pick")
    table.act(game.challenger, "challenge", game._rivals(game.challenger)[0])
    advance_until(table, lambda: game.screen == "duel")
    return game


def test_floor_spoken_answer_switches_the_clock():
    table = Table()
    table.add_players(2)
    table.start("floor")
    game = floor_duel(table)
    a, b = game.challenger, game.defender
    view = table.view(a)
    box = blocks_of(view, "answer")[0]
    assert box["sticky"] and box["auto"]
    assert table.tv_view()["card"]["options"] is None
    table.act(a, "say", game.card["answer"])
    assert game.active == b


def test_floor_wrong_spoken_answer_locks_and_pass_word_passes():
    table = Table()
    table.add_players(2)
    table.start("floor")
    game = floor_duel(table)
    a = game.active
    card = game.card
    wrong = next(o for o in card["others"] if o != card["answer"])
    table.act(a, "say", wrong)
    assert game.locked and game.active == a and game.feedback["label"] == wrong
    assert "to nie to" in json.dumps(table.view(a), ensure_ascii=False)
    table.clock.advance(2.01)
    table.act(a, "say", "pas")
    assert game.locked and game.feedback["correct"] is None


def test_floor_noise_is_ignored():
    table = Table()
    table.add_players(2)
    table.start("floor")
    game = floor_duel(table)
    table.act(game.active, "say", "eee")
    assert not game.locked and game.feedback is None


# --- Jaka to melodia -------------------------------------------------------


def test_melody_spoken_title_scores_and_wrong_one_locks():
    table = Table()
    a, b = table.add_players(2)
    table.start("melody", source="builtin", count=6)
    game = table.session.game
    cue_and_play(table, game)
    table.act(a, "buzz")
    assert blocks_of(table.view(a), "answer")
    table.act(a, "say", "Kaczuszki z Pcimia")
    assert game.screen == "play" and a in game.locked
    assert "Kaczuszki" in json.dumps(table.view(a), ensure_ascii=False)
    table.act(b, "buzz")
    table.act(b, "say", game.track.title)
    assert game.screen == "reveal" and game.points[b] > 0


@pytest.mark.parametrize("said", ["yyy", "  "])
def test_melody_silence_keeps_the_turn(said):
    table = Table()
    a = table.add_players(1)[0]
    table.start("melody", source="builtin", count=6)
    game = table.session.game
    cue_and_play(table, game)
    table.act(a, "buzz")
    table.act(a, "say", said)
    assert game.screen == "answer" and game.answerer == a
