"""Tiering and the scoring -> board seam (issue #89). Network-free."""

import polars as pl

from g_nfl.fantasy.draft_board import (
    attach_next_turn_value,
    attach_tiers,
    attach_vs_ecr,
    next_turn_outlook,
    picks_until_next_turn,
    snake_picks,
)
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


def test_snake_picks_reverse_on_even_rounds():
    assert snake_picks(slot=1, teams=12, rounds=4) == [1, 24, 25, 48]
    assert snake_picks(slot=12, teams=12, rounds=4) == [12, 13, 36, 37]


def test_the_wait_alternates_long_and_short_by_round():
    """The turn cost is the whole point: slot 1 waits 22 picks, then 0."""
    assert picks_until_next_turn(slot=1, teams=12, rnd=1) == 22
    assert picks_until_next_turn(slot=1, teams=12, rnd=2) == 0
    assert picks_until_next_turn(slot=12, teams=12, rnd=1) == 0
    assert picks_until_next_turn(slot=6, teams=12, rnd=1) == 12


def _ranked_board() -> pl.DataFrame:
    """Six players, alternating position, ranked 1-6."""
    return pl.DataFrame(
        {
            "overall_rank": [1, 2, 3, 4, 5, 6],
            "player_name": ["A", "B", "C", "D", "E", "F"],
            "position": ["RB", "WR", "RB", "WR", "RB", "WR"],
            "ppgar": [9.0, 8.0, 5.0, 4.5, 1.0, 0.5],
        }
    )


def test_next_turn_outlook_prices_the_wait_per_position():
    outlook = next_turn_outlook(_ranked_board(), picks_between=2)

    rb = outlook.filter(pl.col("position") == "RB").row(0, named=True)
    assert rb["best_now"] == "A"
    assert rb["best_next_turn"] == "C"  # two picks take A and B
    assert rb["cost_of_waiting"] == 4.0

    # Sorted by cost, so the position that punishes waiting most is on top.
    assert outlook["cost_of_waiting"].to_list() == sorted(
        outlook["cost_of_waiting"].to_list(), reverse=True
    )


def test_vs_next_turn_is_value_over_the_real_alternative():
    board, _ = attach_next_turn_value(_ranked_board(), picks_between=2)
    rows = {r["player_name"]: r["vs_next_turn"] for r in board.iter_rows(named=True)}

    # A is 9.0 over replacement but only 4.0 over the RB you could still get.
    assert rows["A"] == 4.0
    # The survivor is worth nothing over himself.
    assert rows["C"] == 0.0
    # Waiting past your next turn is negative value.
    assert rows["E"] == -4.0


def test_vs_ecr_is_positive_when_we_like_a_player_more_than_the_room():
    board = pl.DataFrame(
        {
            "overall_rank": [1, 2, 3],
            "ecr": [10.0, 2.0, None],
            "player_name": ["sleeper", "consensus", "unranked"],
        }
    )
    deltas = attach_vs_ecr(board)["vs_ecr"].to_list()

    assert deltas[0] == 9.0  # we rank him 1st, the room 10th
    assert deltas[1] == 0.0
    assert deltas[2] is None  # no consensus, no delta to report
