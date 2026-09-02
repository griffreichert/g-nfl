"""The committed board artifact, and the seam that reads it (#72).

These run against the real checked-in JSON on purpose: it is the thing
the deployed API plans against, and a board that is stale or missing a
team is a silent wrong answer rather than a crash.
"""

import math

import pytest

from g_nfl.picks.calendar import current_season
from g_nfl.picks.survivor_board import (
    CONFIDENCE_STEP,
    FRAGILITY_STEP,
    LAST_REG_WEEK,
    build_board,
    cells,
    game_stdev,
    load_artifact,
    team_doubt,
)
from g_nfl.utils.config import SPREAD_STDEV

SEASON = current_season()


def test_artifact_covers_every_team_and_every_week():
    art = load_artifact(SEASON)
    assert len(art["ratings"]) == 32
    weeks = {g["week"] for g in art["games"]}
    assert weeks == set(range(1, LAST_REG_WEEK + 1))
    assert len(art["games"]) == 272  # 17 games x 32 teams / 2


def test_every_team_plays_once_a_week_or_is_on_bye():
    art = load_artifact(SEASON)
    for week in range(1, LAST_REG_WEEK + 1):
        playing = [
            t for g in art["games"] if g["week"] == week for t in (g["home"], g["away"])
        ]
        assert len(playing) == len(set(playing)), f"team twice in week {week}"


def test_build_board_drops_spent_teams_and_past_weeks():
    board, teams, weeks = build_board(SEASON, from_week=5, spent=["KC", "BUF"])
    assert weeks == list(range(5, LAST_REG_WEEK + 1))
    assert "KC" not in teams and "BUF" not in teams
    assert not any(t in ("KC", "BUF") for t, _ in board.prob)
    assert not any(w < 5 for _, w in board.prob)


def test_a_market_line_beats_the_model_spread():
    art = load_artifact(SEASON)
    game = next(g for g in art["games"] if g["week"] == 1)
    board, _, _ = build_board(SEASON, 1, market_spreads={game["game_id"]: 14.0})
    meta = board.game[(game["home"], 1)]
    assert meta["source"] == "market"
    assert meta["spread"] == 14.0
    assert board.prob[(game["home"], 1)] > board.prob[(game["away"], 1)]
    # the away side gets the mirror image, not the same number
    assert board.game[(game["away"], 1)]["spread"] == -14.0


def test_probabilities_are_a_pair_that_sums_to_one():
    board, _, _ = build_board(SEASON, 1)
    art = load_artifact(SEASON)
    game = art["games"][0]
    home = board.prob[(game["home"], game["week"])]
    away = board.prob[(game["away"], game["week"])]
    assert home + away == pytest.approx(1.0)


def test_cells_are_one_per_team_per_played_week():
    board, _, _ = build_board(SEASON, 1)
    got = cells(board)
    assert len(got) == 2 * 272
    assert {c["source"] for c in got} <= {"market", "model"}


def test_no_doubts_leaves_the_board_exactly_as_it_was():
    """The default has to be free, or every number on the page moved for
    a reason nobody chose."""
    plain, _, _ = build_board(SEASON, 1)
    doubted, _, _ = build_board(SEASON, 1, doubts={})
    assert plain.prob == doubted.prob
    assert all(c["stdev"] == SPREAD_STDEV for c in cells(plain))


def test_confidence_is_flat_and_fragility_grows_with_the_horizon():
    near = team_doubt({"NYJ": (2, 2)}, "NYJ", horizon=0)
    far = team_doubt({"NYJ": (2, 2)}, "NYJ", horizon=10)
    assert near == pytest.approx(2 * CONFIDENCE_STEP)
    assert far == pytest.approx(2 * CONFIDENCE_STEP + 2 * FRAGILITY_STEP * 10)
    # confidence alone does not care how far out the week is
    assert team_doubt({"NYJ": (2, 0)}, "NYJ", 0) == team_doubt(
        {"NYJ": (2, 0)}, "NYJ", 12
    )


def test_both_teams_widen_the_same_game():
    lone = game_stdev({"NYJ": (4, 0)}, "NYJ", "BUF", 0)
    both = game_stdev({"NYJ": (4, 0), "BUF": (4, 0)}, "NYJ", "BUF", 0)
    assert both > lone > SPREAD_STDEV
    # independent, so they add in quadrature rather than linearly
    tau = 4 * CONFIDENCE_STEP
    assert both == pytest.approx(math.sqrt(SPREAD_STDEV**2 + 2 * tau**2))


def test_doubt_pulls_a_favourite_toward_a_coin_flip():
    plain, _, _ = build_board(SEASON, 1)
    team, week = max(plain.prob, key=plain.prob.get)
    opponent = plain.game[(team, week)]["opponent"]
    doubted, _, _ = build_board(SEASON, 1, doubts={team: (4, 4), opponent: (4, 4)})
    assert 0.5 < doubted.prob[(team, week)] < plain.prob[(team, week)]
    # and the underdog rises to meet it: this is spread, not a penalty
    assert doubted.prob[(opponent, week)] > plain.prob[(opponent, week)]
