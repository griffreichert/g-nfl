"""Tests for the moneyline -> implied-spread lever (#29)."""

import numpy as np
import polars as pl

from g_nfl.ml.odds import add_ml_odds, devig_home_prob, prob_to_spread


def _devig(home_ml, away_ml):
    df = pl.DataFrame({"h": [home_ml], "a": [away_ml]}).with_columns(
        p=devig_home_prob(pl.col("h"), pl.col("a"))
    )
    return df["p"][0]


def test_devig_symmetric_is_half():
    assert abs(_devig(-110, -110) - 0.5) < 1e-9


def test_devig_favorite_above_half():
    # home -200 (favorite) vs away +170 -> home prob > 0.5
    assert _devig(-200, 170) > 0.5


def test_prob_to_spread_monotone_and_centered():
    rng = np.random.default_rng(0)
    margins = rng.normal(2.0, 14.0, 5000)  # mean ~ HFA
    p = np.array([0.3, 0.5, 0.7])
    s = prob_to_spread(p, margins)
    assert s[0] < s[1] < s[2]  # higher win prob -> bigger home spread
    assert abs(s[1]) < 1.5  # p=0.5 -> ~ mean margin (small)


# a spiky margin distribution -> the prob->spread map plateaus (few distinct
# values) instead of varying smoothly: the key-number stepping
def test_prob_to_spread_plateaus_on_spiky_margins():
    margins = np.array([3] * 400 + [7] * 300 + [-3] * 300, dtype=float)
    s = prob_to_spread(np.linspace(0.1, 0.9, 50), margins)
    assert len(np.unique(np.round(s, 1))) <= 3  # only ~3 plateaus, not 50


def test_add_ml_odds_attaches_and_handles_nulls():
    matrix = pl.DataFrame(
        {
            "game_id": ["g1", "g2"],
            "home_team": ["KC", "BUF"],
            "away_team": ["DET", "NYJ"],
            "spread_line": [4.0, 3.0],
            "result": [7, -3],
        }
    )
    schedule = pl.DataFrame(
        {
            "game_id": ["g1", "g2"],
            "home_moneyline": [-200, None],
            "away_moneyline": [170, None],
        }
    )
    out = add_ml_odds(matrix, schedule)
    assert "ml_implied_spread" in out.columns
    assert "ml_minus_posted" in out.columns
    g1 = out.filter(pl.col("game_id") == "g1").row(0, named=True)
    g2 = out.filter(pl.col("game_id") == "g2").row(0, named=True)
    # favorite -> positive implied home spread
    assert g1["ml_implied_spread"] > 0
    # raw moneyline cols dropped, missing moneyline -> null feature
    assert "home_moneyline" not in out.columns
    assert g2["ml_implied_spread"] is None
