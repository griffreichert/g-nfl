"""The committed board artifact, and the seam that reads it (#72).

These run against the real checked-in JSON on purpose: it is the thing
the deployed API plans against, and a board that is stale or missing a
team is a silent wrong answer rather than a crash.
"""

import pytest

from g_nfl.picks.calendar import current_season
from g_nfl.picks.survivor_board import LAST_REG_WEEK, build_board, cells, load_artifact

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
