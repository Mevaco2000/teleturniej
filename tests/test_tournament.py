"""Turniej: gry po kolei, punkty za miejsca i typowanie podium."""
from __future__ import annotations

import pytest

from server.games.tournament import Tournament, place_points, player_places, tip_points

from .conftest import Table
from .test_games import advance_until


def test_places_skip_bots_and_keep_ties():
    ranking = [
        {"id": "bot1", "place": 1}, {"id": "a", "place": 2}, {"id": "b", "place": 2},
        {"id": "bot2", "place": 4}, {"id": "c", "place": 5},
    ]
    assert player_places(ranking, ["a", "b", "c"]) == {"a": 1, "b": 1, "c": 3}


def test_places_for_teams_go_to_every_member():
    ranking = [{"name": "Czerwoni", "place": 1, "members": ["a", "c"]},
               {"name": "Niebiescy", "place": 2, "members": ["b"]}]
    assert player_places(ranking, ["a", "b", "c"]) == {"a": 1, "c": 1, "b": 2}


def test_points_for_places_and_tips():
    assert [place_points(p) for p in (1, 2, 3, 4, 5, 6, 9)] == [10, 7, 5, 3, 2, 1, 1]
    places = {"a": 1, "b": 2, "c": 3}
    assert tip_points(["a", "b", "c"], places) == 9
    assert tip_points(["b", "a", "c"], places) == 1 + 1 + 3
    assert tip_points(["c", "a", "b"], places) == 0 + 1 + 1
    assert tip_points([], places) == 0


def start_tournament(players=3, **options):
    table = Table(seed=2)
    pids = table.add_players(players)
    table.start("tournament", **{"games": "quick", **options})
    return table, table.session.game, pids


def test_tips_before_game_then_child_game_runs_inside():
    table, game, (a, b, c) = start_tournament()
    assert isinstance(game, Tournament) and game.screen == "predict" and game.child_id == "floor"
    assert table.tv_view()["id"] == "tournament"
    tip_buttons = [i for blk in table.view(a)["blocks"] if blk["type"] == "buttons" for i in blk["items"]]
    assert {i["v"] for i in tip_buttons} == {a, b, c}
    for pid in (a, b, c):
        for target in (a, b, c):
            table.act(pid, "tip", target)
    assert game.screen == "playing" and game.child.id == "floor"
    tv = table.tv_view()
    assert tv["id"] == "floor" and tv["tournament"] == {"number": 1, "total": 3}
    assert table.view(a)["theme"] == "floor"


def test_finished_game_awards_place_and_tip_points():
    table, game, (a, b, c) = start_tournament()
    for pid in (a, b, c):
        for target in (b, a, c):
            table.act(pid, "tip", target)
    child = game.child
    child.finish([{"id": b, "name": "B", "score": 3}, {"id": a, "name": "A", "score": 2},
                  {"id": "bot0", "name": "Bot", "score": 1}, {"id": c, "name": "C", "score": 0}])
    assert game.screen == "scores" and game.child is None
    # b 1. miejsce, a 2., c 3. (bot się nie liczy); każdy typował b, a, c, czyli trafił wszystko.
    assert game.points == {b: 10 + 9, a: 7 + 9, c: 5 + 9}
    assert table.tv_view()["last"]["game"] == "The Floor"
    table.clock.advance(13)
    assert game.screen == "table"
    assert [r["player"]["id"] for r in table.tv_view()["table"]] == [b, a, c]
    table.clock.advance(11)
    assert game.screen == "next" and game.child_id == "familiada", "w Familiadzie nie ma typowania"


def test_host_can_skip_waiting_screens():
    table, game, (a, b, c) = start_tournament(tips="off")
    assert game.screen == "next"
    table.act(b, "next")
    assert game.screen == "next"
    table.act(table.session.host_id, "next")
    assert game.screen == "playing"


def test_crashing_game_is_skipped_and_tournament_goes_on():
    table, game, pids = start_tournament(tips="off")
    table.act(table.session.host_id, "next")
    table.session.abort_game("Coś poszło nie tak.")
    assert table.session.game is game and game.screen == "skipped"
    table.clock.advance(7)
    assert game.child_id == "familiada"


def test_music_game_without_tv_is_skipped():
    table = Table()
    table.add_players(2)
    table.session.disconnected(table.tv)
    table.start("tournament", games="all", tips="off")
    game = table.session.game
    advance_until(table, lambda: game.child_id == "melody" or game.screen == "results",
                  lambda: _end_child(game))
    assert game.screen == "skipped" and "telewizor" in game.skip_note


def _end_child(game):
    if game.screen == "playing" and game.child and game.child.screen != "results":
        game.child.finish([{"id": p, "name": p, "score": 0} for p in game.child.roster])


def test_whole_tournament_ends_with_ranking_by_points():
    table, game, (a, b, c) = start_tournament(tips="off")
    advance_until(table, lambda: game.screen == "results", lambda: _end_child(game))
    assert [r["label"] for r in game.ranking] == ["30 pkt"] * 3
    assert all(r["place"] == 1 for r in game.ranking)


def test_ending_tournament_stops_running_game():
    table, game, pids = start_tournament(tips="off")
    table.act(table.session.host_id, "next")
    child = game.child
    table.act(table.session.host_id, "end_game")
    assert table.session.game is None and child.stopped


@pytest.mark.parametrize("players", [1, 2])
def test_small_groups_skip_tips(players):
    table, game, pids = start_tournament(players=players)
    assert (game.screen == "predict") == (players >= 2)
