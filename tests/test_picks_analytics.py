"""Clustering and shrinkage in g_nfl.picks.analytics (#66).

These two corrections are the whole point of the module, so each gets a
case where a naive group-by would give a visibly different answer.
"""

import math

from g_nfl.picks.analytics import (
    Cell,
    cells,
    graded_rows,
    prior_strength,
    shrink,
    summarize,
)


def _pick(picker, game_id, team, won_side, pick_type="regular"):
    return {
        "picker": picker,
        "game_id": game_id,
        "team_picked": team,
        "week": 1,
        "pick_type": pick_type,
        "spread": None,
    }


# 2025_01_AAA_BBB -> away AAA, home BBB. Home margin +7 with a line of 0 means
# the home side covered.
GID = "2025_01_AAA_BBB"
RESULTS = {GID: 7.0}
LINES = {GID: 0.0}


def test_clustering_collapses_a_pile_on_to_one_game():
    # six people on the same losing side is one bad game, not six
    rows = graded_rows(
        [_pick(f"p{i}", GID, "AAA", False) for i in range(6)], RESULTS, LINES
    )
    assert len(rows) == 6
    (cell,) = cells(rows, lambda r: "all").values()
    assert cell.picks == 6
    assert cell.pick_pct == 0.0
    assert cell.games == 1.0  # <- the correction
    assert cell.raw_pct == 0.0


def test_a_split_game_contributes_its_own_split():
    picks = [
        _pick("a", GID, "BBB", True),
        _pick("b", GID, "BBB", True),
        _pick("c", GID, "AAA", False),
    ]
    rows = graded_rows(picks, RESULTS, LINES)
    (cell,) = cells(rows, lambda r: "all").values()
    assert cell.games == 1.0
    assert math.isclose(cell.raw_pct, 2 / 3)


def test_no_excess_spread_means_no_signal_and_full_shrinkage():
    # two cells sitting exactly on the base rate: nothing to learn
    flat = [Cell("a"), Cell("b")]
    for c in flat:
        c.games, c.wins = 50.0, 25.0
    k = prior_strength(flat, 0.5)
    assert math.isinf(k)
    assert shrink(flat[0], 0.5, k) == 0.5


def test_wide_spread_survives_shrinkage_but_is_pulled_in():
    wide = [Cell("good"), Cell("bad")]
    wide[0].games, wide[0].wins = 80.0, 64.0  # .800
    wide[1].games, wide[1].wins = 80.0, 16.0  # .200
    k = prior_strength(wide, 0.5)
    assert math.isfinite(k)
    pulled = shrink(wide[0], 0.5, k)
    assert 0.5 < pulled < 0.8


def test_small_cell_is_pulled_further_than_a_large_one():
    big, small = Cell("big"), Cell("small")
    big.games, big.wins = 100.0, 70.0
    small.games, small.wins = 5.0, 5.0  # perfect but meaningless
    k = 25.0
    assert shrink(small, 0.5, k) < shrink(big, 0.5, k)


def test_summarize_reports_both_the_naive_and_clustered_rate():
    rows = graded_rows(
        [_pick(f"p{i}", GID, "AAA", False) for i in range(4)], RESULTS, LINES
    )
    (out,) = summarize(rows, lambda r: r["team"])
    assert out["picks"] == 4 and out["games"] == 1.0
    assert out["pick_pct"] == 0.0 and out["pct"] == 0.0
    assert out["units"] == -4.0
