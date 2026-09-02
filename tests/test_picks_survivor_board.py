"""The committed board artifact, and the seam that reads it (#72).

These run against the real checked-in JSON on purpose: it is the thing
the deployed API plans against, and a board that is stale or missing a
team is a silent wrong answer rather than a crash.
"""

import math

import pytest

from g_nfl.picks.calendar import current_season
from g_nfl.picks.survivor_board import (
    CONFIDENCE_FLAT,
    CONFIDENCE_SLOPE,
    LAST_REG_WEEK,
    MIN_STDEV_FRACTION,
    NEUTRAL,
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


def test_neutral_leaves_the_board_exactly_as_it_was():
    """3 has to be free, or every number on the page moved for a reason
    nobody chose."""
    plain, _, _ = build_board(SEASON, 1)
    neutral, _, _ = build_board(SEASON, 1, doubts={"NYJ": NEUTRAL, "LA": NEUTRAL})
    assert plain.prob == neutral.prob
    assert all(c["stdev"] == SPREAD_STDEV for c in cells(plain))


def test_confidence_bites_harder_the_further_out_the_week_is():
    near = team_doubt({"NYJ": 1}, "NYJ", horizon=0)
    far = team_doubt({"NYJ": 1}, "NYJ", horizon=10)
    assert 0 < near < far
    assert near == pytest.approx(2 * CONFIDENCE_FLAT)
    assert far == pytest.approx(2 * (CONFIDENCE_FLAT + CONFIDENCE_SLOPE * 10))


def test_five_is_good_and_one_is_bad():
    """The scale has to point the friendly way or nobody will set it right."""
    assert team_doubt({"LA": 5}, "LA", 8) < 0 < team_doubt({"LA": 1}, "LA", 8)
    assert team_doubt({"LA": NEUTRAL}, "LA", 8) == 0
    # and conviction sharpens the game rather than only doubt blurring it
    assert game_stdev({"LA": 5, "ARI": 5}, "LA", "ARI", 8) < SPREAD_STDEV


def test_both_teams_move_the_same_game():
    lone = game_stdev({"NYJ": 1}, "NYJ", "BUF", 4)
    both = game_stdev({"NYJ": 1, "BUF": 1}, "NYJ", "BUF", 4)
    assert both > lone > SPREAD_STDEV
    # independent, so they meet in quadrature rather than adding
    tau = 2 * (CONFIDENCE_FLAT + CONFIDENCE_SLOPE * 4)
    assert both == pytest.approx(math.sqrt(SPREAD_STDEV**2 + 2 * tau**2))


def test_certainty_is_floored():
    """A wall of 5s must not manufacture a game nobody can be that sure of.

    The floor is a guard rather than a value the scale reaches: trusting
    every team completely, 17 weeks out, still lands above it. It exists
    so the sign convention cannot be pushed into nonsense.
    """
    trusted = dict.fromkeys(load_artifact(SEASON)["ratings"], 5)
    stdevs = [
        game_stdev(trusted, g["home"], g["away"], h)
        for g in load_artifact(SEASON)["games"]
        for h in (0, 17)
    ]
    assert min(stdevs) >= MIN_STDEV_FRACTION * SPREAD_STDEV
    assert max(stdevs) <= SPREAD_STDEV  # conviction never widens
    assert game_stdev(trusted, "LA", "ARI", 100) == pytest.approx(
        MIN_STDEV_FRACTION * SPREAD_STDEV
    )


def test_low_confidence_pulls_a_late_favourite_toward_a_coin_flip():
    plain, _, _ = build_board(SEASON, 1)
    late = {k: v for k, v in plain.prob.items() if k[1] >= 12}
    team, week = max(late, key=late.get)
    opponent = plain.game[(team, week)]["opponent"]
    doubted, _, _ = build_board(SEASON, 1, doubts={team: 1, opponent: 1})
    assert 0.5 < doubted.prob[(team, week)] < plain.prob[(team, week)]
    # and the underdog rises to meet it: this is spread, not a penalty
    assert doubted.prob[(opponent, week)] > plain.prob[(opponent, week)]
