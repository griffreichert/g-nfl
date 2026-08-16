"""Will he last to your next pick? (issue #99). Network-free."""

import polars as pl

from g_nfl.fantasy.survival import (
    MIN_PICK_SD,
    best_expected_available,
    consensus_pick,
    survival,
)


def _board() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gsis_id": ["early", "late", "qb", "unknown"],
            "player_name": ["Early WR", "Late RB", "The QB", "Nobody"],
            "position": ["WR", "RB", "QB", "WR"],
            "ppgar": [9.0, 5.0, 4.0, 8.0],
            "ecr": [4.0, 40.0, 26.0, None],
            "sd": [1.0, 8.0, 3.0, None],
        }
    )


def _adp() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gsis_id": ["early", "late", "qb"],
            "adp": [4.0, 40.0, 3.0],
            "adp_min": [1.0, 30.0, 1.0],
            "adp_max": [9.0, 50.0, 11.0],
        }
    )


def test_quarterbacks_use_ecr_because_the_adp_feed_pools_superflex():
    """MFL takes QBs far too early for a 1QB league, so ECR stands in."""
    picked = consensus_pick(_board(), _adp())
    by_id = {r["gsis_id"]: r for r in picked.iter_rows(named=True)}

    assert by_id["qb"]["pick_mu"] == 26.0  # ECR, not the ADP of 3.0
    assert by_id["early"]["pick_mu"] == 4.0  # skill positions keep ADP
    assert by_id["early"]["pick_sd"] == 2.0  # (9 - 1) / 4


def test_a_zero_spread_still_leaves_room_for_doubt():
    board = _board().head(1)
    adp = pl.DataFrame(
        {"gsis_id": ["early"], "adp": [4.0], "adp_min": [4.0], "adp_max": [4.0]}
    )
    assert consensus_pick(board, adp)["pick_sd"][0] == MIN_PICK_SD


def test_survival_rises_with_the_pick_you_are_waiting_for():
    picked = consensus_pick(_board(), _adp())
    at_10 = survival(picked, 10)
    at_60 = survival(picked, 60)

    def p(frame: pl.DataFrame, gsis_id: str) -> float:
        return frame.filter(pl.col("gsis_id") == gsis_id)["p_available"][0]

    assert p(at_10, "early") < 0.01  # ADP 4, sd 2: long gone by pick 10
    assert p(at_10, "late") > 0.99  # ADP 40: certain to be there
    assert p(at_60, "late") < 0.05  # by pick 60 he is not

    # No consensus estimate means no guess.
    assert p(at_10, "unknown") is None


def test_best_expected_available_skips_players_who_will_be_gone():
    """The correction over board order: the best survivor, not the next name."""
    picked = consensus_pick(_board(), _adp())
    best = best_expected_available(picked, 20)
    by_position = {r["position"]: r["player_name"] for r in best.iter_rows(named=True)}

    assert by_position["RB"] == "Late RB"
    # The uncovered player falls back rather than vanishing from the board.
    assert by_position["WR"] == "Nobody"
