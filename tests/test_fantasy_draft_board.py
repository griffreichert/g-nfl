"""Tiering and the scoring -> board seam (issue #89). Network-free."""

import polars as pl

from g_nfl.fantasy.draft_board import attach_tiers
from g_nfl.fantasy.projections.board import build_board
from g_nfl.fantasy.scoring import HALF_PPR_12, PPR_12, score


def _stat_lines() -> pl.DataFrame:
    """WRs whose receptions thin out steeply, RBs whose barely do.

    That spread is what makes reception value positional: PPGAR is measured
    against a position's own replacement, so cutting PPR only costs a position
    ground when its stars catch far more than its replacement does.
    """
    rows = []
    for i in range(30):
        rows.append(
            {
                "gsis_id": f"WR{i}",
                "player_name": f"WR {i}",
                "position": "WR",
                "team": "SEA",
                "pass_yd": 0.0,
                "pass_td": 0.0,
                "ints": 0.0,
                "rush_yd": 0.0,
                "rush_td": 0.0,
                "rec": 100.0 - i,
                "rec_yd": 1200.0 - 10 * i,
                "rec_td": 8.0,
                "fum": 0.0,
            }
        )
        rows.append(
            {
                "gsis_id": f"RB{i}",
                "player_name": f"RB {i}",
                "position": "RB",
                "team": "DET",
                "pass_yd": 0.0,
                "pass_td": 0.0,
                "ints": 0.0,
                "rush_yd": 1300.0 - 10 * i,
                "rush_td": 9.0,
                "rec": 30.0 - 0.1 * i,
                "rec_yd": 250.0,
                "rec_td": 1.0,
                "fum": 0.0,
            }
        )
    return pl.DataFrame(rows)


def _board(config) -> pl.DataFrame:
    lines = _stat_lines()
    return build_board(score(lines, config), config.teams, config.roster_positions)


def test_reception_value_moves_receivers_relative_to_backs():
    """Halving PPR should cost the high-reception WRs ground on the RBs."""
    full = _board(PPR_12)
    half = _board(HALF_PPR_12)

    def wr_share_of_top(board: pl.DataFrame, n: int = 20) -> int:
        return board.head(n).filter(pl.col("position") == "WR").height

    assert wr_share_of_top(half) < wr_share_of_top(full)


def test_tiers_break_on_gaps_and_number_per_position():
    board = pl.DataFrame(
        {
            "position": ["WR", "WR", "WR", "RB", "RB"],
            "ppgar": [10.0, 9.8, 5.0, 8.0, 7.9],
        }
    )
    tiered = attach_tiers(board, gap=1.0)

    wr = tiered.filter(pl.col("position") == "WR").sort("ppgar", descending=True)
    assert wr["tier"].to_list() == [1, 1, 2]

    # Tiers restart per position, so the RBs are tier 1 despite lower ppgar.
    rb = tiered.filter(pl.col("position") == "RB")
    assert rb["tier"].to_list() == [1, 1]
