"""Tests for g_nfl.fantasy.projections.board (issue #31). Network-free."""

import polars as pl

from g_nfl.fantasy.projections.board import (
    attach_efficiency_rates,
    build_board,
    replacement_baselines,
)


def _proj(*rows: tuple[str, str, float]) -> pl.DataFrame:
    """(player_name, position, proj_ppg) -> minimal projection frame."""
    return pl.DataFrame(
        {
            "player_id": [r[0] for r in rows],
            "player_name": [r[0] for r in rows],
            "position": [r[1] for r in rows],
            "last_team": ["XX"] * len(rows),
            "proj_ppg": [r[2] for r in rows],
            "proj_points": [r[2] * 17 for r in rows],
        }
    )


def test_replacement_is_first_non_starter():
    """2 teams, 1 QB slot each -> 2 QBs start; QB3 is replacement."""
    proj = _proj(
        ("QB1", "QB", 30.0),
        ("QB2", "QB", 25.0),
        ("QB3", "QB", 20.0),
        ("QB4", "QB", 15.0),
    )
    base = replacement_baselines(proj, teams=2, roster_positions=["QB"])
    assert base["QB"] == 20.0  # QB3, first off the bench


def test_flex_consumes_best_eligible():
    """1 team: 1 RB + 1 FLEX(RB/WR/TE). Best non-RB-starter eligible fills flex.

    RB1 takes the dedicated RB. FLEX then picks the best remaining among
    {RB,WR,TE}: RB2 (18) beats WR1 (17), so RB2 starts -> RB replacement = RB3.
    """
    proj = _proj(
        ("RB1", "RB", 20.0),
        ("RB2", "RB", 18.0),
        ("RB3", "RB", 10.0),
        ("WR1", "WR", 17.0),
        ("WR2", "WR", 8.0),
    )
    base = replacement_baselines(proj, teams=1, roster_positions=["RB", "FLEX"])
    assert base["RB"] == 10.0  # RB3 first off bench (RB1 dedicated, RB2 flex)
    assert base["WR"] == 17.0  # WR1 never started -> it's the replacement


def test_superflex_can_take_qb():
    """SUPER_FLEX is QB-eligible: a strong QB2 fills it, raising the QB baseline."""
    proj = _proj(
        ("QB1", "QB", 30.0),
        ("QB2", "QB", 28.0),
        ("QB3", "QB", 12.0),
        ("RB1", "RB", 20.0),
        ("RB2", "RB", 9.0),
    )
    base = replacement_baselines(
        proj, teams=1, roster_positions=["QB", "RB", "SUPER_FLEX"]
    )
    # QB1 dedicated, QB2 (28) beats RB2 (9) for SF -> QB3 is replacement.
    assert base["QB"] == 12.0


def test_ppgar_and_ranks():
    proj = _proj(
        ("QB1", "QB", 30.0),
        ("QB2", "QB", 20.0),
        ("RB1", "RB", 25.0),
        ("RB2", "RB", 10.0),
    )
    board = build_board(proj, teams=1, roster_positions=["QB", "RB"])
    # baselines: QB2=20, RB2=10. ppgar: QB1=10, RB1=15, QB2=0, RB2=0.
    rb1 = board.filter(pl.col("player_id") == "RB1").row(0, named=True)
    assert abs(rb1["ppgar"] - 15.0) < 1e-9
    assert rb1["overall_rank"] == 1  # RB1 ppgar 15 > QB1 ppgar 10
    assert board["overall_rank"].to_list() == sorted(board["overall_rank"].to_list())


def test_attach_efficiency_rates_left_join_nulls_for_missing():
    board = _proj(("WR1", "WR", 15.0), ("QB1", "QB", 25.0))
    rates = pl.DataFrame(
        {"player_id": ["WR1"], "tprr": [0.25], "yprr": [2.0], "fdrr": [0.1]}
    )
    attached = attach_efficiency_rates(board, rates)
    wr_row = attached.filter(pl.col("player_id") == "WR1").row(0, named=True)
    qb_row = attached.filter(pl.col("player_id") == "QB1").row(0, named=True)
    assert abs(wr_row["yprr"] - 2.0) < 1e-9
    assert qb_row["tprr"] is None
