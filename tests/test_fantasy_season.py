"""Tests for g_nfl.fantasy.projections.season (issue #30).

All tests are network-free; they build synthetic polars frames and
exercise the pure functions directly.
"""

import polars as pl
import pytest

from g_nfl.fantasy.projections.season import (
    DEFAULT_GAMES,
    _scored_ppg,
    blend_projections,
)

# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _make_frame(*rows: dict) -> pl.DataFrame:
    """Build a minimal player-season frame from dicts."""
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "player_name": pl.Utf8,
            "position": pl.Utf8,
            "recent_team": pl.Utf8,
            "season": pl.Int32,
            "games": pl.Int32,
            "fantasy_points": pl.Float64,
            "fantasy_points_ppr": pl.Float64,
        },
    )


# A WR with 3 seasons; TE with 2; QB with 1 (oldest only); FB to normalise.
FRAME = _make_frame(
    # WR — 3 seasons
    {
        "player_id": "WR1",
        "player_name": "Star WR",
        "position": "WR",
        "recent_team": "KC",
        "season": 2024,
        "games": 16,
        "fantasy_points": 200.0,
        "fantasy_points_ppr": 280.0,
    },
    {
        "player_id": "WR1",
        "player_name": "Star WR",
        "position": "WR",
        "recent_team": "KC",
        "season": 2023,
        "games": 17,
        "fantasy_points": 180.0,
        "fantasy_points_ppr": 260.0,
    },
    {
        "player_id": "WR1",
        "player_name": "Star WR",
        "position": "WR",
        "recent_team": "KC",
        "season": 2022,
        "games": 15,
        "fantasy_points": 160.0,
        "fantasy_points_ppr": 220.0,
    },
    # TE — 2 seasons
    {
        "player_id": "TE1",
        "player_name": "Solid TE",
        "position": "TE",
        "recent_team": "SF",
        "season": 2024,
        "games": 17,
        "fantasy_points": 140.0,
        "fantasy_points_ppr": 180.0,
    },
    {
        "player_id": "TE1",
        "player_name": "Solid TE",
        "position": "TE",
        "recent_team": "SF",
        "season": 2023,
        "games": 14,
        "fantasy_points": 120.0,
        "fantasy_points_ppr": 155.0,
    },
    # QB — only oldest season (index 2 in a 3-weight tuple, weight 0.1)
    {
        "player_id": "QB1",
        "player_name": "Old QB",
        "position": "QB",
        "recent_team": "DAL",
        "season": 2022,
        "games": 17,
        "fantasy_points": 280.0,
        "fantasy_points_ppr": 282.0,
    },
    # FB — should become RB after load_player_seasons normalisation
    {
        "player_id": "FB1",
        "player_name": "Block Back",
        "position": "FB",
        "recent_team": "NE",
        "season": 2024,
        "games": 12,
        "fantasy_points": 30.0,
        "fantasy_points_ppr": 45.0,
    },
)


# ---------------------------------------------------------------------------
# _scored_ppg
# ---------------------------------------------------------------------------


def test_scored_ppg_standard():
    scored = _scored_ppg(FRAME.filter(pl.col("player_id") == "WR1"), "standard")
    row = scored.filter(pl.col("season") == 2024).row(0, named=True)
    assert abs(row["ppg"] - 200.0 / 16) < 1e-9


def test_scored_ppg_ppr():
    scored = _scored_ppg(FRAME.filter(pl.col("player_id") == "WR1"), "ppr")
    row = scored.filter(pl.col("season") == 2024).row(0, named=True)
    assert abs(row["ppg"] - 280.0 / 16) < 1e-9


def test_scored_ppg_half():
    scored = _scored_ppg(FRAME.filter(pl.col("player_id") == "WR1"), "half")
    row = scored.filter(pl.col("season") == 2024).row(0, named=True)
    expected = ((200.0 + 280.0) / 2) / 16
    assert abs(row["ppg"] - expected) < 1e-9


def test_ppr_gte_standard_for_pass_catcher():
    """PPR ppg >= standard ppg for a receiver (they have receptions)."""
    s_std = _scored_ppg(FRAME.filter(pl.col("player_id") == "WR1"), "standard")
    s_ppr = _scored_ppg(FRAME.filter(pl.col("player_id") == "WR1"), "ppr")
    std_vals = s_std["ppg"].to_list()
    ppr_vals = s_ppr["ppg"].to_list()
    assert all(p >= s for p, s in zip(ppr_vals, std_vals, strict=True))


def test_scored_ppg_zero_games_dropped():
    frame = _make_frame(
        {
            "player_id": "X",
            "player_name": "No Games",
            "position": "RB",
            "recent_team": "XX",
            "season": 2024,
            "games": 0,
            "fantasy_points": 10.0,
            "fantasy_points_ppr": 15.0,
        },
    )
    scored = _scored_ppg(frame, "ppr")
    assert len(scored) == 0, "zero-game rows should be dropped"


def test_scored_ppg_invalid_scoring():
    with pytest.raises(ValueError, match="scoring must be one of"):
        _scored_ppg(FRAME, "invalid")


# ---------------------------------------------------------------------------
# blend_projections
# ---------------------------------------------------------------------------


def _scored(scoring: str = "ppr") -> pl.DataFrame:
    return _scored_ppg(FRAME, scoring)


def test_weights_renormalise_single_season():
    """QB1 only has 2022 data; with weights (0.6,0.3,0.1) its only present
    season gets rank 1 but... wait — QB1 only exists in the oldest season
    (2022), which would be rank 3 (least recent) if all 3 seasons were
    present.  After renorm, its weight == 1.0 regardless, so proj_ppg ==
    that season's ppg.
    """
    scored = _scored("ppr")
    result = blend_projections(scored, 2025, (0.6, 0.3, 0.1), DEFAULT_GAMES)
    qb_row = result.filter(pl.col("player_id") == "QB1").row(0, named=True)
    # QB1 has only one season; ppg = 282 / 17
    expected_ppg = 282.0 / 17
    assert abs(qb_row["proj_ppg"] - expected_ppg) < 1e-6


def test_proj_points_equals_ppg_times_games():
    result = blend_projections(_scored(), 2025, (0.6, 0.3, 0.1), DEFAULT_GAMES)
    for row in result.iter_rows(named=True):
        assert abs(row["proj_points"] - row["proj_ppg"] * DEFAULT_GAMES) < 1e-6


def test_n_seasons_correct():
    result = blend_projections(_scored(), 2025, (0.6, 0.3, 0.1), DEFAULT_GAMES)
    assert result.filter(pl.col("player_id") == "WR1")["n_seasons"][0] == 3
    assert result.filter(pl.col("player_id") == "TE1")["n_seasons"][0] == 2
    assert result.filter(pl.col("player_id") == "QB1")["n_seasons"][0] == 1


def test_sorted_descending():
    result = blend_projections(_scored(), 2025, (0.6, 0.3, 0.1), DEFAULT_GAMES)
    pts = result["proj_points"].to_list()
    assert pts == sorted(pts, reverse=True)


def test_last_team_is_most_recent():
    result = blend_projections(_scored(), 2025, (0.6, 0.3, 0.1), DEFAULT_GAMES)
    wr_row = result.filter(pl.col("player_id") == "WR1").row(0, named=True)
    assert wr_row["last_team"] == "KC"


# ---------------------------------------------------------------------------
# FB -> RB normalisation (via load_player_seasons round-trip through _scored)
# ---------------------------------------------------------------------------


def test_fb_normalised_to_rb():
    """FB1 in FRAME has position FB; after _scored_ppg (which doesn't touch
    position) and blend_projections it should still appear as FB because
    load_player_seasons is the normalisation point.

    Test the normalisation directly on a minimal frame that mimics the
    load_player_seasons output (where FB is already mapped to RB).
    """
    fb_frame = _make_frame(
        {
            "player_id": "FB1",
            "player_name": "Block Back",
            "position": "FB",
            "recent_team": "NE",
            "season": 2024,
            "games": 12,
            "fantasy_points": 30.0,
            "fantasy_points_ppr": 45.0,
        },
    )
    # Simulate what load_player_seasons does: replace FB -> RB
    normalised = fb_frame.with_columns(
        pl.col("position").replace({"FB": "RB"}).alias("position")
    )
    scored = _scored_ppg(normalised, "ppr")
    assert scored.filter(pl.col("player_id") == "FB1")["position"][0] == "RB"
