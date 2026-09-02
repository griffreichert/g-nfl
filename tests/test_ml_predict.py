"""Tests for the weekly predict job (#13).

The guard that matters: an entry built for week 1 must not be the same
number on every game. That was the pre-`preseason` behaviour and it made
``edge = pred - spread`` a ranking of ``|spread|``, so the top pick was
the biggest underdog on the board every time.
"""

import polars as pl
import pytest

from g_nfl.ml import predict as predict_mod
from g_nfl.ml.predict import DEEP_SEASONS_START, predict_week, training_seasons


def test_training_window_is_deep_and_ends_at_the_season():
    seasons = training_seasons(2026)
    assert seasons[0] == DEEP_SEASONS_START
    assert seasons[-1] == 2026
    assert len(seasons) > 5


@pytest.fixture
def matrix() -> pl.DataFrame:
    """Two seasons of a four-team league. Prior-season strength is real
    signal: KC is the best team and WAS the worst, in both the preseason
    block and the lines the model is fitted to.
    """
    rows = []
    strength = {"KC": 7.0, "BUF": 3.0, "SF": -2.0, "WAS": -8.0}
    pairs = [("KC", "BUF"), ("SF", "WAS"), ("KC", "SF"), ("BUF", "WAS")]
    for season in (2024, 2025):
        for week in range(1, 9):
            for i, (home, away) in enumerate(pairs):
                spread = strength[home] - strength[away] + 1.5
                rows.append(
                    {
                        "game_id": f"{season}_{week:02d}_{away}_{home}_{i}",
                        "season": season,
                        "week": week,
                        "home_team": home,
                        "away_team": away,
                        "spread_line": spread,
                        "result": int(spread) + (1 if i % 2 else -1),
                        # in-season feature: null in week 1, as in the real matrix
                        "home_epa_mean_season": None if week == 1 else strength[home],
                        "away_epa_mean_season": None if week == 1 else strength[away],
                        # preseason block: present in every week
                        "pre_diff_mkt_rating": strength[home] - strength[away],
                        "home_pre_mkt_rating": strength[home],
                        "away_pre_mkt_rating": strength[away],
                        # opponent adjustment: the ridge fits week 1 off the
                        # prior season, so this is present in every week too.
                        # Deliberately not a clean multiple of the spread --
                        # a real rating disagrees with the line, and a
                        # perfectly collinear one makes the fit exact.
                        "adj_rating_diff": (strength[home] - strength[away]) / 10
                        + (0.4 if i % 2 else -0.4),
                    }
                )
    return pl.DataFrame(rows)


@pytest.fixture
def patched(monkeypatch, matrix):
    monkeypatch.setattr(predict_mod, "build_matrix", lambda *a, **k: matrix)


def test_week_one_predictions_are_not_one_constant(patched):
    """The headline guard. Four distinct matchups, so at least two
    distinct predictions."""
    out = predict_week(2025, 1, seasons=[2024])
    assert out.height == 4
    assert out["pred"].n_unique() > 1


def test_week_one_ranks_by_matchup_not_by_spread(patched):
    """With a real preseason signal the model should not simply order the
    board by line size, which is what a constant prediction does."""
    out = predict_week(2025, 1, seasons=[2024])
    by_edge = out["game_id"].to_list()
    by_spread = out.sort(pl.col("spread_line").abs(), descending=True)[
        "game_id"
    ].to_list()
    assert by_edge != by_spread


def test_pick_follows_the_sign_of_the_edge(patched):
    out = predict_week(2025, 1, seasons=[2024])
    for row in out.iter_rows(named=True):
        expected = row["home_team"] if row["edge"] > 0 else row["away_team"]
        assert row["pick"] == expected


def test_trains_only_on_strictly_earlier_games(patched, matrix, monkeypatch):
    """A week-5 prediction must not see week 5 or later."""
    seen = {}

    class Spy:
        def __init__(self, params=None):
            self.params = params

        def fit(self, X, y):
            seen["n"] = len(y)

        def predict(self, X):
            return [0.0] * len(X)

    monkeypatch.setattr(predict_mod, "SpreadModel", Spy)
    predict_week(2025, 5, seasons=[2024])

    expected = matrix.filter(
        (pl.col("season") < 2025) | ((pl.col("season") == 2025) & (pl.col("week") < 5))
    ).height
    assert seen["n"] == expected


def test_unscheduled_week_is_an_error(patched):
    with pytest.raises(ValueError, match="no games scheduled"):
        predict_week(2025, 18, seasons=[2024])
