"""Grading is where a sign error would be invisible and total.

Every case below has a favourite, a dog and a margin chosen so the right
answer is obvious by eye.
"""

import polars as pl

from g_nfl.pool.grade import grade


def _fixture(pool_spread: float | None = -3.0):
    """GB at NYG. Negative pool spread = the away team (GB) is favoured."""
    games = pl.DataFrame(
        {
            "season": [2022],
            "week": [5],
            "home_team": ["NYG"],
            "away_team": ["GB"],
            "spread_line": [-2.0],
            "result": [-7.0],  # NYG lost by 7, so GB won by 7
            "game_id": ["2022_05_GB_NYG"],
        }
    )
    lines = pl.DataFrame(
        {
            "season": [2022],
            "week": [5],
            "home_team": ["NYG"],
            "pool_spread": [pool_spread],
        },
        schema_overrides={"pool_spread": pl.Float64},
    )
    return games, lines


def _picks(team: str, pick_type: str = "regular"):
    return pl.DataFrame(
        {
            "season": [2022],
            "week": [5],
            "picker": ["Griffin"],
            "slot": ["1"],
            "pick_type": [pick_type],
            "team_picked": [team],
        }
    )


def test_a_favourite_that_covers_wins():
    games, lines = _fixture()
    row = grade(_picks("GB"), games, lines).row(0, named=True)
    # GB laid 3 and won by 7
    assert row["team_spread"] == -3.0
    assert row["cover"] == 4.0
    assert row["ats_result"] == "W"
    assert row["points"] == 1.0


def test_the_dog_side_of_the_same_game_loses():
    games, lines = _fixture()
    row = grade(_picks("NYG"), games, lines).row(0, named=True)
    assert row["team_spread"] == 3.0  # NYG getting points
    assert row["cover"] == -4.0
    assert row["ats_result"] == "L"
    assert row["points"] == 0.0


def test_a_push_scores_nothing():
    games, lines = _fixture(pool_spread=-7.0)
    row = grade(_picks("GB"), games, lines).row(0, named=True)
    assert row["cover"] == 0.0
    assert row["ats_result"] == "P"
    assert row["points"] == 0.0


def test_a_best_bet_is_worth_two():
    games, lines = _fixture()
    row = grade(_picks("GB", "best_bet"), games, lines).row(0, named=True)
    assert row["points"] == 2.0


def test_an_underdog_pays_the_spread_only_on_an_outright_win():
    games, lines = _fixture()
    lost = grade(_picks("NYG", "underdog"), games, lines).row(0, named=True)
    assert lost["su_win"] is False
    assert lost["points"] == 0.0

    # flip the result so the dog wins outright
    games = games.with_columns(result=pl.lit(4.0))
    won = grade(_picks("NYG", "underdog"), games, lines).row(0, named=True)
    assert won["su_win"] is True
    assert won["points"] == 3.0  # its own spread, not a slot value


def test_a_missing_pool_line_falls_back_to_the_market_and_says_so():
    games, lines = _fixture(pool_spread=None)
    row = grade(_picks("GB"), games, lines).row(0, named=True)
    assert row["line_source"] == "market"
    assert row["team_spread"] == -2.0


def test_a_2020_best_bet_was_only_worth_one_point():
    games, lines = _fixture()
    games = games.with_columns(season=pl.lit(2020))
    lines = lines.with_columns(season=pl.lit(2020))
    picks = _picks("GB", "best_bet").with_columns(season=pl.lit(2020))
    assert grade(picks, games, lines).row(0, named=True)["points"] == 1.0
