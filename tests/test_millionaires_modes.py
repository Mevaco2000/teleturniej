"""Milionerzy dla wielu osób: zakłady widzów w trybie jednego fotela i tryb „Wszyscy na drabince”."""
from __future__ import annotations

import json

from server.games.millionaires import LADDER, START_CHIPS
from server.games.millionaires_all import MillionairesAll

from .conftest import Table
from .test_games import advance_until, seat_player


def buttons_of(view: dict, action: str) -> list[dict]:
    return [i for b in view["blocks"] if b["type"] == "buttons" for i in b["items"] if i["action"] == action]


# --- Zakłady -------------------------------------------------------------


def seat_game(players: int = 3):
    table = Table()
    pids = table.add_players(players)
    table.start("millionaires", mode="seat")
    game = table.session.game
    hot = seat_player(table, game)
    return table, game, hot, [p for p in pids if p != hot]


def test_spectators_see_bet_buttons_and_hot_seat_does_not():
    table, game, hot, others = seat_game()
    bets = buttons_of(table.view(others[0]), "bet")
    assert {tuple(b["v"]) for b in bets} >= {("right", 100), ("wrong", 500), ("right", START_CHIPS)}
    assert not buttons_of(table.view(hot), "bet")
    table.act(hot, "bet", ["right", 100])
    assert hot not in game.bets


def test_right_bet_wins_and_wrong_bet_loses():
    table, game, hot, (a, b) = seat_game()
    table.act(a, "bet", ["right", 250])
    table.act(b, "bet", ["wrong", 500])
    table.act(a, "bet", ["wrong", 100])
    assert game.bets[a] == ("right", 250)
    table.act(hot, "select", game.q.correct)
    table.act(hot, "confirm")
    table.clock.advance(3)
    assert game.outcome == "right"
    assert game.chips[a] == START_CHIPS + 250 and game.chips[b] == START_CHIPS - 500
    assert table.tv_view()["betResults"][0]["delta"] == 250
    assert "+250" in json.dumps(table.view(a), ensure_ascii=False)


def test_walk_away_returns_bets_and_bets_close_after_lock():
    table, game, hot, (a, b) = seat_game()
    table.act(a, "bet", ["wrong", START_CHIPS])
    table.act(hot, "walk")
    assert game.chips[a] == START_CHIPS
    table, game, hot, (a, b) = seat_game()
    table.act(hot, "select", game.q.correct)
    table.act(hot, "confirm")
    table.act(a, "bet", ["right", 100])
    assert a not in game.bets


def test_cannot_bet_more_than_owned_or_odd_values():
    table, game, hot, (a, b) = seat_game()
    for junk in (["right", 5000], ["right", -100], ["maybe", 100], ["right", True], "right", [1, 2, 3], None):
        table.act(a, "bet", junk)
    assert a not in game.bets
    game.chips[a] = 60
    assert [tuple(x["v"]) for x in buttons_of(table.view(a), "bet")] == [("right", 60), ("wrong", 60)]
    game.chips[a] = 0
    assert not buttons_of(table.view(a), "bet")


def test_final_ranking_shows_chips():
    table, game, hot, (a, b) = seat_game()
    game._finish()
    assert all("żetony" in r["label"] for r in game.ranking)


# --- Wszyscy na drabince -------------------------------------------------


def ladder_game(players: int = 3, seed: int = 1):
    table = Table(seed=seed)
    pids = table.add_players(players)
    table.start("millionaires")
    game = table.session.game
    assert isinstance(game, MillionairesAll), "domyślny tryb to wszyscy na drabince"
    advance_until(table, lambda: game.screen == "question")
    return table, game, pids


def answer(table, pid, index):
    table.act(pid, "select", index)
    table.act(pid, "confirm")


def test_everyone_gets_the_same_question_without_the_answer():
    table, game, pids = ladder_game()
    for pid in pids:
        view = table.view(pid)
        assert view["prompt"] == game.q.text
        assert '"correct"' not in json.dumps(view)
    assert table.tv_view()["q"]["correct"] is None


def test_question_closes_when_everyone_decides_and_wrong_answer_falls_to_guaranteed():
    table, game, (a, b, c) = ladder_game()
    wrong = (game.q.correct + 1) % 4
    answer(table, a, game.q.correct)
    answer(table, b, wrong)
    assert game.screen == "question"
    table.act(c, "walk")
    assert game.screen == "locked"
    choices = {p["id"]: p["choice"] for p in table.tv_view()["players"]}
    assert choices[a] == game.q.correct and choices[b] == wrong
    table.clock.advance(3)
    assert game.screen == "reveal"
    assert game.climbers[a].earned == LADDER[0] and game.climbers[a].status == "playing"
    assert game.climbers[b].status == "out" and game.climbers[b].earned == 0
    assert game.climbers[c].status == "walked" and game.climbers[c].earned == 0
    table.clock.advance(6)
    assert game.screen == "question" and game.level == 1


def test_timeout_without_answer_counts_as_wrong():
    table, game, (a, b) = ladder_game(players=2)
    answer(table, a, game.q.correct)
    table.clock.advance(game.opts["time"] + 3)
    assert game.climbers[b].status == "out" and game.climbers[b].last == "time"


def test_walking_away_keeps_money_from_previous_question():
    table, game, (a, b) = ladder_game(players=2)
    for _ in range(3):
        answer(table, a, game.q.correct)
        answer(table, b, game.q.correct)
        advance_until(table, lambda: game.screen == "question")
    table.act(a, "walk")
    assert game.climbers[a].earned == LADDER[2]


def test_out_players_become_audience_for_the_poll():
    table, game, (a, b, c) = ladder_game()
    table.act(b, "walk")
    table.act(c, "walk")
    table.act(b, "vote", 2)
    table.act(c, "vote", 2)
    table.act(a, "lifeline", "audience")
    assert game.climbers[a].poll == [0, 0, 100, 0]
    assert not game.climbers[a].lifelines["audience"]


def test_fifty_fifty_is_personal():
    table, game, (a, b) = ladder_game(players=2)
    table.act(a, "lifeline", "fifty")
    assert len(game.climbers[a].hidden) == 2 and game.q.correct not in game.climbers[a].hidden
    assert game.climbers[b].hidden == []
    table.act(a, "select", game.climbers[a].hidden[0])
    assert game.climbers[a].choice is None


def test_phone_a_friend_who_is_already_out():
    table, game, (a, b) = ladder_game(players=2)
    table.act(b, "walk")
    table.act(a, "lifeline", "phone")
    friends = buttons_of(table.view(a), "pick_friend")
    assert {f["v"] for f in friends} == {b, "expert"}
    table.act(a, "pick_friend", b)
    assert game.calls == {b: a}
    assert "Dzwoni" in table.view(b)["sub"]
    table.act(b, "friend_answer", 3)
    assert game.climbers[a].call["choice"] == 3 and not game.calls
    assert game.screen == "question", "zegar nie staje i pytanie trwa dalej"


def test_expert_answers_at_once():
    table, game, (a,) = ladder_game(players=1)
    table.act(a, "lifeline", "phone")
    table.act(a, "pick_friend", "expert")
    assert game.climbers[a].call["who"] == "Ekspert w studiu"


def test_game_ends_when_nobody_climbs_and_ranks_by_money():
    table, game, (a, b) = ladder_game(players=2)
    answer(table, a, game.q.correct)
    answer(table, b, (game.q.correct + 1) % 4)
    advance_until(table, lambda: game.screen == "question")
    answer(table, a, game.q.correct)
    advance_until(table, lambda: game.screen == "question")
    table.act(a, "walk")
    advance_until(table, lambda: game.screen == "results")
    assert [r["id"] for r in game.ranking] == [a, b]
    assert game.ranking[0]["score"] == LADDER[1]


def test_millionaire_reaches_the_top():
    table, game, (a,) = ladder_game(players=1)
    for _ in range(len(LADDER)):
        advance_until(table, lambda: game.screen == "question")
        answer(table, a, game.q.correct)
    advance_until(table, lambda: game.screen == "results")
    assert game.climbers[a].status == "top" and game.ranking[0]["score"] == 1_000_000


def test_disconnected_climber_walks_away_instead_of_blocking():
    table, game, (a, b) = ladder_game(players=2)
    answer(table, a, game.q.correct)
    table.session.disconnected(table.conns[b])
    assert game.screen == "locked"
    assert game.climbers[b].status == "walked"
