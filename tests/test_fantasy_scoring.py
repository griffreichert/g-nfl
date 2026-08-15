"""Tests for g_nfl.fantasy.scoring (issue #88)."""

import polars as pl

from g_nfl.fantasy.scoring import HALF_PPR_12, PPR_12, Scoring, score


def _lines(*rows: tuple) -> pl.DataFrame:
    """(name, position, pass_yd, pass_td, ints, rush_yd, rush_td, rec, rec_yd, rec_td, fum)."""
    cols = [
        "pass_yd",
        "pass_td",
        "ints",
        "rush_yd",
        "rush_td",
        "rec",
        "rec_yd",
        "rec_td",
        "fum",
    ]
    return pl.DataFrame(
        {
            "gsis_id": [r[0] for r in rows],
            "espn_id": [r[0] for r in rows],
            "player_name": [r[0] for r in rows],
            "position": [r[1] for r in rows],
            "team": ["XX"] * len(rows),
            **{c: [r[2 + i] for r in rows] for i, c in enumerate(cols)},
        }
    )


def test_score_matches_hand_computed_total():
    """WR1: 100 rec, 1200 rec_yd, 10 rec_td, 2 fumbles lost, full PPR.

    1.0*100 + 0.1*1200 + 6.0*10 - 2.0*2 = 100 + 120 + 60 - 4 = 276.
    proj_ppg = 276 / 17.
    """
    lines = _lines(("WR1", "WR", 0, 0, 0, 0, 0, 100, 1200, 10, 2))
    result = score(lines, PPR_12)
    row = result.row(0, named=True)
    assert abs(row["proj_points"] - 276.0) < 0.005
    assert abs(row["proj_ppg"] - 276.0 / 17) < 0.005


def test_reception_weight_moves_receivers_above_rushers():
    """High-reception WR vs high-rush-yard, low-reception RB.

    Half PPR: RB (183.5) outscores WR (175). Full PPR: WR (230) overtakes RB (183.5).
    """
    lines = _lines(
        ("RB2", "RB", 0, 0, 0, 1200, 10, 2, 15, 0, 0),
        ("WR3", "WR", 0, 0, 0, 0, 0, 110, 900, 5, 0),
    )
    half = score(lines, HALF_PPR_12).sort("player_name")
    full = score(lines, PPR_12).sort("player_name")

    rb_half, wr_half = half["proj_points"].to_list()
    rb_full, wr_full = full["proj_points"].to_list()

    assert rb_half > wr_half
    assert wr_full > rb_full


def test_te_premium_applies_only_to_te():
    """te_premium is an addition to the base reception rate, TE only."""
    config = HALF_PPR_12.model_copy(
        update={"scoring": Scoring(reception=0.5, te_premium=0.5)}
    )
    lines = _lines(
        ("TE1", "TE", 0, 0, 0, 0, 0, 10, 0, 0, 0),
        ("RB1", "RB", 0, 0, 0, 0, 0, 10, 0, 0, 0),
    )
    result = score(lines, config).sort("player_name")  # RB1, TE1
    rb_points, te_points = result["proj_points"].to_list()
    assert abs(te_points - 10.0) < 1e-9  # (0.5 + 0.5) * 10
    assert abs(rb_points - 5.0) < 1e-9  # 0.5 * 10
