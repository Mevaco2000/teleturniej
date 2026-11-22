"""Scenariusze zasad każdej gry oraz odporność na nieprzewidywalne zachowanie graczy."""
from __future__ import annotations

import json
import random

import pytest

from server.games import GAMES
from server.games.floor import grid_shape
from server.games.millionaires import LADDER, money

from .conftest import Table

MAX_EVENTS = 40_000


def options_for(game_id: str) -> dict:
    return {"melody": {"source": "builtin", "count": 6}}.get(game_id, {})


def run_until_results(table: Table, tick=lambda: None) -> None:
    for _ in range(MAX_EVENTS):
        game = table.session.game
        if game is None or game.screen == "results":
            return
        tick()
        table.session.flush()
        if not table.clock.run_next():
            pytest.fail("Gra czeka bez żadnego zegara, czyli zawiesiła się")
    pytest.fail(f"Gra nie skończyła się po {MAX_EVENTS} zdarzeniach, ekran: {table.session.game.screen}")


def advance_until(table: Table, done, before_step=lambda: None) -> None:
    """Przewija zdarzenia do spełnienia warunku; zamiast wisieć, test pada."""
    for _ in range(MAX_EVENTS):
        if done():
            return
        before_step()
        if not table.clock.run_next() and not done():
            pytest.fail("Brak kolejnych zdarzeń, a oczekiwany stan nie nastąpił")
    pytest.fail("Oczekiwany stan nie nastąpił")


def tv_ack_audio(table: Table) -> None:
    game = table.session.game
    audio = getattr(game, "audio", None)
    if audio and game.screen == "cue":
        table.session.handle(table.tv, {"t": "tv", "e": "audio_ready", "token": audio["token"]})


def press_random_control(table: Table, pid: str, rng: random.Random) -> None:
    """Klika losowy element, który telefon gracza faktycznie pokazuje."""
    view = table.view(pid)
    if not view:
        return
    actions = []
    for block in view["blocks"]:
        if block["type"] == "options":
            actions += [(block["action"], item["v"]) for item in block["items"] if item["state"] != "gone"]
        elif block["type"] == "buzz":
            actions.append((block["action"], None))
        elif block["type"] == "buttons":
            actions += [(item["action"], item["v"]) for item in block["items"]
                        if not item["disabled"] and item["action"] != "end_game"]
    if actions:
        action, value = rng.choice(actions)
        table.act(pid, action, value)


@pytest.mark.parametrize("game_id", list(GAMES))
@pytest.mark.parametrize("players", [1, 2, 3, 5, 10])
def test_game_finishes_when_nobody_touches_the_phone(game_id, players):
    """Każdy etap ma limit czasu, więc porzucone telefony nie mogą zawiesić gry."""
    table = Table(seed=players)
    table.add_players(players)
    table.start(game_id, **options_for(game_id))
    run_until_results(table, lambda: tv_ack_audio(table))
    assert table.session.game.ranking


@pytest.mark.parametrize("game_id", list(GAMES))
@pytest.mark.parametrize("seed", range(6))
def test_game_survives_random_players(game_id, seed):
    """Losowe klikanie po prawdziwych kontrolkach nie może wywołać błędu ani przerwać gry."""
    table = Table(seed=seed)
    pids = table.add_players(2 + seed)
    rng = random.Random(seed)
    table.start(game_id, **options_for(game_id))

    def tick():
        tv_ack_audio(table)
        if rng.random() < 0.7:
            press_random_control(table, rng.choice(pids), rng)

    run_until_results(table, tick)
    assert table.session.game is not None, table.session.notice
    assert table.session.notice is None


@pytest.mark.parametrize("game_id", list(GAMES))
@pytest.mark.parametrize("seed", range(6))
def test_solo_game_survives_random_clicks(game_id, seed):
    """Każdą grę da się przejść w pojedynkę, np. żeby ją przetestować."""
    table = Table(seed=seed)
    pid = table.add_players(1)[0]
    rng = random.Random(seed)
    table.start(game_id, **options_for(game_id))
    assert table.session.game is not None, table.session.notice

    def tick():
        tv_ack_audio(table)
        if rng.random() < 0.8:
            press_random_control(table, pid, rng)

    run_until_results(table, tick)
    assert table.session.notice is None
    ranking = table.session.game.ranking
    assert any(r.get("id") == pid or pid in r.get("members", []) for r in ranking)


@pytest.mark.parametrize("game_id", list(GAMES))
def test_players_dropping_mid_game_do_not_stop_it(game_id):
    table = Table(seed=3)
    pids = table.add_players(5)
    table.start(game_id, **options_for(game_id))
    for _ in range(30):
        tv_ack_audio(table)
        table.clock.run_next()
    table.session.disconnected(table.conns[pids[1]])
    table.act(table.session.host_id, "kick", pids[2])
    run_until_results(table, lambda: tv_ack_audio(table))
    assert table.session.game is not None, table.session.notice


@pytest.mark.parametrize("game_id", list(GAMES))
def test_malformed_actions_are_ignored(game_id):
    table = Table(seed=9)
    pids = table.add_players(3)
    table.start(game_id, **options_for(game_id))
    junk = [None, -1, 99, "x", [], {}, [1], {"a": 1}, 1.5, True]
    for _ in range(40):
        tv_ack_audio(table)
        for action in ("answer", "buzz", "lifeline", "select", "confirm", "point", "self_take", "challenge",
                       "pick", "bid", "vote", "qualify", "friend_answer", "pick_friend", "pass", "nonsense"):
            table.act(pids[0], action, random.Random(action).choice(junk))
        table.clock.run_next()
    assert table.session.notice is None


# --- Tajemnica odpowiedzi --------------------------------------------------


def test_phones_never_receive_the_right_answer_before_reveal():
    table = Table(seed=4)
    pids = table.add_players(4)
    table.start("millionaires")
    for _ in range(300):
        game = table.session.game
        if game.screen == "results":
            break
        if game.q is not None and game.screen in ("qualify", "question", "locked", "audience"):
            for pid in pids:
                dumped = json.dumps(table.view(pid), ensure_ascii=False)
                assert '"correct"' not in dumped
            tv = table.tv_view()
            assert tv["q"]["correct"] is None
        table.clock.run_next()


def test_melody_title_is_hidden_until_reveal():
    table = Table(seed=5)
    pid = table.add_players(1)[0]
    table.start("melody", source="builtin", count=6)
    table.clock.advance(4)
    game = table.session.game
    assert game.screen == "cue"
    assert "track" not in table.tv_view()
    title = game.track.title
    table.session.handle(table.tv, {"t": "tv", "e": "audio_ready", "token": game.audio["token"]})
    assert game.screen == "play"
    assert title not in json.dumps(table.view(pid), ensure_ascii=False)
    assert "track" not in table.tv_view()
    table.act(pid, "buzz")
    table.act(pid, "answer", game.correct)
    assert game.screen == "reveal"
    assert table.tv_view()["track"]["title"] == title


# --- 1 z 10 ----------------------------------------------------------------


def test_one_of_ten_wrong_answer_costs_a_life():
    table = Table()
    table.add_players(2)
    table.start("one_of_ten")
    table.clock.advance(4)
    game = table.session.game
    pid = game.answerer
    table.act(pid, "answer", (game.q.correct + 1) % 4)
    assert game.lives[pid] == 2
    assert game.result["correct"] is False


def test_one_of_ten_only_active_player_can_answer():
    table = Table()
    pids = table.add_players(3)
    table.start("one_of_ten")
    table.clock.advance(4)
    game = table.session.game
    other = next(p for p in pids if p != game.answerer)
    table.act(other, "answer", game.q.correct)
    assert game.screen == "ask"


def test_one_of_ten_round_two_runs_until_three_remain():
    table = Table(seed=2)
    table.add_players(6)
    table.start("one_of_ten")
    game = table.session.game
    def play_wrong():
        if game.screen == "ask":
            table.act(game.answerer, "answer", (game.q.correct + 1) % 4)
        elif game.screen == "pick":
            table.act(game.picker, "point", next(p for p in game._alive() if p != game.picker))

    advance_until(table, lambda: game.round == 3, play_wrong)
    assert game.round == 3
    assert len(game.finalists) == 3
    assert all(game.lives[p] == 3 for p in game.finalists)


def test_one_of_ten_final_self_take_gives_double_points():
    table = Table(seed=2)
    table.add_players(2)
    table.start("one_of_ten")
    game = table.session.game
    advance_until(table, lambda: not (game.round != 3 or game.screen != "buzz"))
    pid = game.finalists[0]
    table.act(pid, "buzz")
    table.act(pid, "answer", game.q.correct)
    assert game.points[pid] == 10
    table.clock.advance(4)
    assert game.screen == "choice" and game.picker == pid
    table.act(pid, "self_take")
    table.act(pid, "answer", game.q.correct)
    assert game.points[pid] == 30


def test_one_of_ten_solo_final_lasts_until_lives_run_out():
    table = Table(seed=4)
    pid = table.add_players(1)[0]
    table.start("one_of_ten")
    game = table.session.game
    advance_until(table, lambda: game.round == 3 and game.screen == "buzz")
    table.act(pid, "buzz")
    table.act(pid, "answer", game.q.correct)
    table.clock.advance(4)
    assert game.screen == "choice"
    assert all(b["type"] != "buttons" or b["items"][0]["action"] == "self_take" for b in table.view(pid)["blocks"])

    def answer_wrong():
        if game.screen == "buzz":
            table.act(pid, "buzz")
        elif game.screen == "ask":
            table.act(pid, "answer", (game.q.correct + 1) % 4)

    advance_until(table, lambda: game.screen == "results", answer_wrong)
    assert game.lives[pid] == 0
    assert game.points[pid] == 10


# --- Milionerzy ------------------------------------------------------------


def seat_player(table: Table, game) -> str:
    def answer_qualifier():
        if game.screen == "qualify":
            for pid in list(game.waiting):
                table.act(pid, "qualify", game.q.correct)

    advance_until(table, lambda: game.screen == "question", answer_qualifier)
    return game.hot


def test_millionaires_fastest_correct_answer_wins_the_seat():
    table = Table()
    a, b, c = table.add_players(3)
    table.start("millionaires")
    game = table.session.game
    assert game.screen == "qualify"
    wrong = (game.q.correct + 1) % 4
    table.act(a, "qualify", wrong)
    table.clock.advance(1)
    table.act(c, "qualify", game.q.correct)
    table.clock.advance(1)
    table.act(b, "qualify", game.q.correct)
    assert game.screen == "qualify_reveal"
    assert game.hot == c


def test_millionaires_wrong_answer_falls_to_guaranteed_amount():
    table = Table()
    table.add_players(1)
    table.start("millionaires")
    game = table.session.game
    hot = seat_player(table, game)
    for level in range(3):
        table.act(hot, "select", game.q.correct)
        table.act(hot, "confirm")
        advance_until(table, lambda: not (game.screen != "question"))
    assert game.level == 3
    table.act(hot, "select", (game.q.correct + 1) % 4)
    table.act(hot, "confirm")
    table.clock.advance(3)
    assert game.outcome == "wrong"
    assert game.earned[hot] == LADDER[1] == 1000


def test_millionaires_walk_away_keeps_last_amount():
    table = Table()
    table.add_players(1)
    table.start("millionaires")
    game = table.session.game
    hot = seat_player(table, game)
    table.act(hot, "select", game.q.correct)
    table.act(hot, "confirm")
    advance_until(table, lambda: not (game.screen != "question"))
    table.act(hot, "walk")
    assert game.earned[hot] == 500


def test_millionaires_fifty_fifty_keeps_correct_answer_and_works_once():
    table = Table()
    table.add_players(1)
    table.start("millionaires")
    game = table.session.game
    hot = seat_player(table, game)
    table.act(hot, "lifeline", "fifty")
    assert len(game.hidden) == 2 and game.q.correct not in game.hidden
    first = list(game.hidden)
    table.act(hot, "lifeline", "fifty")
    assert game.hidden == first
    table.act(hot, "select", first[0])
    assert game.selected is None


def test_millionaires_real_audience_votes_and_timer_resumes():
    table = Table()
    pids = table.add_players(4)
    table.start("millionaires")
    game = table.session.game
    hot = seat_player(table, game)
    table.clock.advance(5)
    before = game.time_left()
    table.act(hot, "lifeline", "audience")
    assert game.screen == "audience"
    table.clock.advance(3)
    assert game.time_left() == pytest.approx(before)
    voters = [p for p in pids if p != hot]
    for voter in voters:
        table.act(voter, "vote", 2)
    assert game.screen == "question"
    assert game.poll[2] == 100
    assert game.timer_view()["running"] is True


def test_millionaires_phone_a_friend_shows_question_only_to_friend():
    table = Table()
    pids = table.add_players(3)
    table.start("millionaires")
    game = table.session.game
    hot = seat_player(table, game)
    table.act(hot, "lifeline", "phone")
    assert game.screen == "phone_pick"
    friend, bystander = [p for p in pids if p != hot]
    table.act(hot, "pick_friend", friend)
    assert game.screen == "phone_call"
    assert any(b["type"] == "options" for b in table.view(friend)["blocks"])
    assert not any(b["type"] == "options" for b in table.view(bystander)["blocks"])
    table.act(friend, "friend_answer", 1)
    assert game.screen == "question"
    assert game.call == {"who": table.session.pinfo(friend)["name"], "choice": 1}


def test_money_format():
    assert money(1000000) == "1 000 000 zł"


# --- Jaka to melodia -------------------------------------------------------


def cue_and_play(table: Table, game) -> None:
    advance_until(table, lambda: not (game.screen != "cue"))
    table.session.handle(table.tv, {"t": "tv", "e": "audio_ready", "token": game.audio["token"]})


def test_melody_faster_answer_scores_more_and_pauses_music():
    table = Table()
    a, b = table.add_players(2)
    table.start("melody", source="builtin", count=6)
    game = table.session.game
    cue_and_play(table, game)
    assert game.screen == "play" and game.audio["playing"] is True
    table.clock.advance(2)
    table.act(a, "buzz")
    assert game.screen == "answer" and game.audio["playing"] is False
    table.act(a, "answer", game.correct)
    fast = game.points[a]
    assert fast >= 85
    cue_and_play(table, game)
    table.clock.advance(15)
    table.act(b, "buzz")
    table.act(b, "answer", game.correct)
    assert 20 <= game.points[b] < fast


def test_melody_wrong_answer_locks_player_and_resumes_clip():
    table = Table()
    a, b = table.add_players(2)
    table.start("melody", source="builtin", count=6)
    game = table.session.game
    cue_and_play(table, game)
    table.clock.advance(5)
    table.act(a, "buzz")
    left_when_buzzed = game.time_left("clip")
    table.clock.advance(3)
    assert game.time_left("clip") == pytest.approx(left_when_buzzed)
    table.act(a, "answer", (game.correct + 1) % 4)
    assert game.screen == "play" and game.audio["playing"] is True
    table.act(a, "buzz")
    assert game.screen == "play"
    table.act(b, "buzz")
    assert game.answerer == b


def test_melody_lowest_bid_plays_for_that_many_seconds():
    table = Table()
    a, b = table.add_players(2)
    table.start("melody", source="builtin", count=6)
    game = table.session.game
    advance_until(table, lambda: game.screen == "bid", lambda: tv_ack_audio(table))
    table.act(a, "bid", 5)
    table.act(a, "bid", 1)
    assert game.bids[a][0] == 5
    table.act(b, "bid", 2)
    assert game.bid_winner == b and game.bid_value == 2
    table.session.handle(table.tv, {"t": "tv", "e": "audio_ready", "token": game.audio["token"]})
    assert game.screen == "bid_play"
    table.clock.advance(2.01)
    assert game.screen == "answer" and game.answerer == b
    table.act(b, "answer", game.correct)
    assert game.points[b] == 150


def test_melody_silent_tv_ends_game_with_clear_message():
    table = Table()
    table.add_players(1)
    table.start("melody", source="builtin", count=6)
    for _ in range(200):
        if table.session.game is None:
            break
        table.clock.run_next()
    assert table.session.game is None
    assert "Telewizor" in table.session.notice


def test_melody_cannot_start_without_tv():
    table = Table()
    table.add_players(1)
    table.session.disconnected(table.tv)
    table.start("melody", source="builtin", count=6)
    assert table.session.game is None
    assert "TV" in table.session.notice


# --- Familiada -------------------------------------------------------------


def to_answer(table: Table, game) -> None:
    advance_until(table, lambda: not (game.screen != "answer"))


def choice_index(game, label: str) -> int:
    return game.choices.index(label)


def test_familiada_top_answer_in_duel_wins_control():
    table = Table()
    table.add_players(4)
    table.start("familiada")
    game = table.session.game
    advance_until(table, lambda: not (game.screen != "duel_buzz"))
    first = game.duelists[0]
    table.act(first, "buzz")
    table.act(first, "pick", choice_index(game, game.answers[0][0]))
    table.clock.advance(3)
    assert game.control == game._team_of(first)
    assert game.mode == "play"


def test_familiada_higher_answer_wins_duel():
    table = Table()
    table.add_players(4)
    table.start("familiada")
    game = table.session.game
    advance_until(table, lambda: not (game.screen != "duel_buzz"))
    first, second = game.duelists
    table.act(first, "buzz")
    table.act(first, "pick", choice_index(game, game.answers[3][0]))
    table.clock.advance(3)
    assert game.answerer == second and game.mode == "duel_second"
    table.act(second, "pick", choice_index(game, game.answers[1][0]))
    table.clock.advance(3)
    assert game.control == game._team_of(second)


def test_familiada_three_strikes_allow_steal_of_the_bank():
    table = Table()
    table.add_players(4)
    table.start("familiada")
    game = table.session.game
    advance_until(table, lambda: not (game.screen != "duel_buzz"))
    first = game.duelists[0]
    table.act(first, "buzz")
    top = game.answers[0]
    table.act(first, "pick", choice_index(game, top[0]))
    table.clock.advance(3)
    controlling = game.control
    decoys = list(game.question["decoys"])
    for decoy in decoys[:3]:
        to_answer(table, game)
        table.act(game.answerer, "pick", choice_index(game, decoy))
    assert game.strikes == 3
    table.clock.advance(3)
    assert game.mode == "steal"
    assert game._team_of(game.answerer) != controlling
    bank_before = game.bank
    stolen = game.answers[1]
    table.act(game.answerer, "pick", choice_index(game, stolen[0]))
    table.clock.advance(3)
    assert game.round_winner == 1 - controlling
    assert game.scores[1 - controlling] == (bank_before + stolen[1]) * game.multiplier


def test_familiada_cannot_pick_the_same_option_twice():
    table = Table()
    table.add_players(2)
    table.start("familiada")
    game = table.session.game
    advance_until(table, lambda: not (game.screen != "duel_buzz"))
    first = game.duelists[0]
    table.act(first, "buzz")
    index = choice_index(game, game.question["decoys"][0])
    table.act(first, "pick", index)
    table.clock.advance(3)
    table.act(game.answerer, "pick", index)
    assert game.screen == "answer"


def test_familiada_board_is_hidden_from_tv_until_revealed():
    table = Table()
    table.add_players(2)
    table.start("familiada")
    game = table.session.game
    advance_until(table, lambda: not (game.screen != "duel_buzz"))
    board = table.tv_view()["board"]
    assert all(row["label"] is None and row["points"] is None for row in board)


def test_familiada_solo_plays_without_rivals():
    table = Table()
    pid = table.add_players(1)[0]
    table.start("familiada")
    game = table.session.game
    assert game.teams == [[pid], []]
    advance_until(table, lambda: game.screen == "duel_buzz")
    assert game.duelists == [pid]
    table.act(pid, "buzz")
    table.act(pid, "pick", choice_index(game, game.answers[2][0]))
    table.clock.advance(3)
    assert game.mode == "play" and game.control == 0
    for decoy in list(game.question["decoys"])[:3]:
        to_answer(table, game)
        table.act(pid, "pick", choice_index(game, decoy))
    table.clock.advance(3)
    assert game.screen == "round_end" and game.round_winner == 0
    assert game.scores[0] == game.answers[2][1] * game.multiplier


def test_familiada_teams_are_balanced():
    table = Table()
    table.add_players(7)
    table.start("familiada")
    game = table.session.game
    assert sorted(len(t) for t in game.teams) == [3, 4]


# --- The Floor -------------------------------------------------------------


@pytest.mark.parametrize("tiles,shape", [(2, (2, 1)), (3, (3, 1)), (4, (2, 2)), (6, (3, 2)), (9, (3, 3)),
                                         (12, (4, 3)), (16, (4, 4))])
def test_floor_grid_shape(tiles, shape):
    assert grid_shape(tiles) == shape


def to_duel(table: Table, game) -> None:
    advance_until(table, lambda: not (game.screen != "pick"))
    table.act(game.challenger, "challenge", game._rivals(game.challenger)[0])
    advance_until(table, lambda: not (game.screen != "duel"))


def test_floor_chess_clock_only_runs_for_active_player():
    table = Table()
    table.add_players(4)
    table.start("floor")
    game = table.session.game
    to_duel(table, game)
    a, b = game.challenger, game.defender
    table.clock.advance(5)
    table.act(a, "answer", game.card["correct"])
    assert game.active == b
    assert game.clocks[a] == pytest.approx(game.opts["clock"] - 5, abs=0.01)
    table.clock.advance(7)
    assert game.clocks[a] == pytest.approx(game.opts["clock"] - 5, abs=0.01)
    assert game.time_left("duel") == pytest.approx(game.opts["clock"] - 7, abs=0.01)


def test_floor_wrong_answer_keeps_clock_and_locks_briefly():
    table = Table()
    table.add_players(4)
    table.start("floor")
    game = table.session.game
    to_duel(table, game)
    a = game.active
    card = game.card
    table.act(a, "answer", (card["correct"] + 1) % 4)
    assert game.active == a and game.locked
    table.act(a, "answer", card["correct"])
    assert game.active == a
    table.clock.advance(2.01)
    assert not game.locked and game.card is not card


def test_floor_defender_winning_inherits_challenger_category():
    table = Table()
    table.add_players(4)
    table.start("floor")
    game = table.session.game
    to_duel(table, game)
    challenger, defender = game.challenger, game.defender
    challenger_category = game.owners[challenger].category
    table.clock.advance(game.opts["clock"] + 0.1)
    assert game.winner == defender
    assert game.owners[defender].category is challenger_category
    assert len(game.owners[defender].tiles) == 2
    assert not game.owners[challenger].alive


def test_floor_challenger_winning_keeps_own_category():
    table = Table()
    table.add_players(4)
    table.start("floor")
    game = table.session.game
    to_duel(table, game)
    challenger, defender = game.challenger, game.defender
    own = game.owners[challenger].category
    table.act(challenger, "answer", game.card["correct"])
    table.clock.advance(game.opts["clock"] + 0.1)
    assert game.winner == challenger
    assert game.owners[challenger].category is own


def test_floor_only_neighbours_can_be_challenged():
    table = Table()
    table.add_players(1)
    table.start("floor", tiles=16)
    game = table.session.game
    advance_until(table, lambda: not (game.screen != "pick"))
    me = game.challenger
    rivals = game._rivals(me)
    outsider = next(o for o in game.owners if o != me and o not in rivals)
    table.act(me, "challenge", outsider)
    assert game.screen == "pick"
    table.act(me, "challenge", rivals[0])
    assert game.screen == "duel_intro"


def test_floor_solo_player_gets_bots():
    table = Table()
    table.add_players(1)
    table.start("floor", tiles=0)
    game = table.session.game
    assert len(game.owners) == 2
    assert sum(o.bot for o in game.owners.values()) == 1
    table.act(table.session.host_id, "end_game")
    table.start("floor", tiles=6)
    game = table.session.game
    assert len(game.owners) == 6
    assert sum(o.bot for o in game.owners.values()) == 5


def test_floor_bot_answers_during_its_turn():
    table = Table(seed=8)
    table.add_players(1)
    table.start("floor", tiles=6)
    game = table.session.game
    to_duel(table, game)
    table.act(game.challenger, "answer", game.card["correct"])
    assert game.owners[game.active].bot
    first_card = game.card
    table.clock.advance(6)
    assert game.card is not first_card


# --- Sesja -----------------------------------------------------------------


def test_reconnect_with_token_restores_player():
    table = Table()
    pid = table.add_players(2)[0]
    conn = table.conns[pid]
    token = next(m["token"] for m in conn.messages if m.get("t") == "welcome")
    table.session.disconnected(conn)
    assert not table.session.players[pid].connected
    new_conn = type(conn)()
    table.session.handle(new_conn, {"t": "hello", "role": "player", "token": token})
    assert new_conn.player_id == pid
    assert table.session.players[pid].connected


def test_second_window_replaces_first_without_reconnect_loop():
    table = Table()
    pid = table.add_players(2)[0]
    first = table.conns[pid]
    token = next(m["token"] for m in first.messages if m.get("t") == "welcome")
    second = type(first)()
    table.session.handle(second, {"t": "hello", "role": "player", "token": token})
    assert first.messages[-1]["t"] == "replaced" and first.closed
    assert second.player_id == pid
    table.session.disconnected(first)
    assert table.session.players[pid].connected, "zamknięcie starego okna odłączyło nowe"


def test_kicked_player_can_join_again_on_the_same_connection():
    table = Table()
    host, guest = table.add_players(2)
    conn = table.conns[guest]
    table.act(host, "kick", guest)
    assert conn.messages[-1]["t"] == "removed" and not conn.closed
    assert guest not in table.session.players
    table.session.handle(conn, {"t": "join", "name": "Powrót"})
    assert conn.player_id in table.session.players


def test_unknown_or_non_ascii_token_asks_for_name():
    table = Table()
    table.add_players(1)
    conn = type(table.tv)()
    table.session.handle(conn, {"t": "hello", "role": "player", "token": "żółw"})
    assert conn.messages[-1]["t"] == "need_name"


def test_duplicate_names_get_suffix():
    table = Table()
    first = table.join("Ania")
    second = table.join("ania")
    assert table.session.players[first].name == "Ania"
    assert table.session.players[second].name == "ania 2"


def test_empty_name_is_rejected_and_html_is_kept_as_text():
    table = Table()
    conn = type(table.tv)()
    table.session.handle(conn, {"t": "join", "name": "   "})
    assert conn.messages[-1]["t"] == "error"
    pid = table.join("<b>x</b>")
    assert table.session.players[pid].name == "<b>x</b>"


def test_only_host_can_start_games():
    table = Table()
    host, guest = table.add_players(2)
    assert table.session.host_id == host
    table.act(guest, "select_game", "floor")
    assert table.session.selected is None
    table.act(host, "select_game", "floor")
    table.act(guest, "start_game")
    assert table.session.game is None


def test_host_migrates_after_grace_period_and_not_before():
    table = Table()
    host, guest = table.add_players(2)
    table.session.disconnected(table.conns[host])
    assert table.session.host_id == host
    table.clock.advance(29)
    assert table.session.host_id == host
    table.clock.advance(2)
    assert table.session.host_id == guest


def test_host_returning_in_time_stays_host():
    table = Table()
    host, guest = table.add_players(2)
    conn = table.conns[host]
    token = next(m["token"] for m in conn.messages if m.get("t") == "welcome")
    table.session.disconnected(conn)
    table.clock.advance(10)
    table.session.handle(type(conn)(), {"t": "hello", "role": "player", "token": token})
    table.clock.advance(60)
    assert table.session.host_id == host


def test_invalid_option_values_are_rejected():
    table = Table()
    host = table.add_players(1)[0]
    table.act(host, "select_game", "one_of_ten")
    table.session.handle(table.conns[host], {"t": "action", "a": "set_option", "key": "time", "v": 9999})
    assert table.session.options["one_of_ten"]["time"] == 15
    table.act(host, "select_game", ["bad"])
    assert table.session.selected == "one_of_ten"


def test_late_joiner_sees_spectator_view():
    table = Table()
    table.add_players(2)
    table.start("one_of_ten")
    late = table.join("Spóźniony")
    view = table.view(late)
    assert "Dołączysz" in view["blocks"][0]["text"]
