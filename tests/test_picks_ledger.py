"""The weekly ledger (#58).

Its job is to score the call against alternatives it could have taken, so the
tests are mostly about the benchmarks being honest.
"""

from g_nfl.picks import ledger


def _pick(picker, game_id, team, slot="regular", week=1):
    return {
        "picker": picker,
        "week": week,
        "game_id": game_id,
        "team_picked": team,
        "pick_type": slot,
    }


# 2026_01_AAA_BBB: away AAA, home BBB. Home margin +7 on a line of 0 means the
# home side covered.
G1, G2, G3 = "2026_01_AAA_BBB", "2026_01_CCC_DDD", "2026_01_EEE_FFF"
RESULTS = {G1: 7.0, G2: -7.0, G3: 0.0}
LINES = {G1: 0.0, G2: 0.0, G3: 0.0}


def test_a_best_bet_is_worth_two_and_a_regular_one():
    assert ledger.score(_pick("a", G1, "BBB", "best_bet"), 7.0, 0.0) == 2.0
    assert ledger.score(_pick("a", G1, "BBB"), 7.0, 0.0) == 1.0
    assert ledger.score(_pick("a", G1, "AAA"), 7.0, 0.0) == 0.0


def test_a_push_pays_half():
    assert ledger.score(_pick("a", G3, "FFF", "best_bet"), 0.0, 0.0) == 1.0
    assert ledger.score(_pick("a", G3, "FFF"), 0.0, 0.0) == 0.5


def test_an_ungraded_pick_scores_nothing_rather_than_zero():
    assert ledger.score(_pick("a", G1, "BBB"), None, 0.0) is None


def test_the_majority_takes_the_side_most_members_picked():
    picks = [
        _pick("Griffin", G1, "BBB"),
        _pick("Harry", G1, "BBB"),
        _pick("Ben", G1, "AAA"),
    ]
    (entry,) = ledger.majority_entry(picks)
    assert entry["team_picked"] == "BBB"


def test_the_majority_ignores_team_because_team_is_its_output():
    picks = [
        _pick("Griffin", G1, "BBB"),
        _pick("TEAM", G1, "AAA"),
        _pick("TEAM", G1, "AAA"),
    ]
    (entry,) = ledger.majority_entry(picks)
    assert entry["team_picked"] == "BBB"


def test_the_majority_never_uses_one_game_twice():
    picks = [
        _pick("Griffin", G1, "BBB", "best_bet"),
        _pick("Harry", G1, "BBB", "regular"),
        _pick("Harry", G2, "CCC", "regular"),
    ]
    entry = ledger.majority_entry(picks)
    assert len({e["game_id"] for e in entry}) == len(entry)


def test_the_ledger_scores_team_and_the_benchmarks_side_by_side():
    picks = [
        _pick("TEAM", G1, "AAA"),
        _pick("Griffin", G1, "BBB"),
        _pick("Harry", G1, "BBB"),
    ]
    rows = ledger.weekly(picks, RESULTS, LINES)
    got = {r["entry"]: r["points"] for r in rows}
    assert got["TEAM"] == 0.0
    assert got["Majority"] == 1.0
    assert got["Griffin"] == 1.0


def test_the_best_member_is_chosen_on_the_table_before_the_week():
    """Otherwise the benchmark reads a result it could not have known."""
    picks = [
        # week 1: Griffin right, Harry wrong
        _pick("Griffin", G1, "BBB", week=1),
        _pick("Harry", G1, "AAA", week=1),
        # week 2: it flips, and the benchmark should still be following Griffin
        _pick("Griffin", G2, "DDD", week=2),
        _pick("Harry", G2, "CCC", week=2),
    ]
    rows = ledger.weekly(picks, RESULTS, LINES)
    week2 = {r["entry"]: r for r in rows if r["week"] == 2}
    assert week2["Best member"]["leader"] == "Griffin"
    assert week2["Best member"]["points"] == 0.0  # Griffin lost week 2


def test_a_week_nobody_has_played_is_left_out():
    picks = [_pick("Griffin", "2026_09_ZZZ_YYY", "YYY", week=9)]
    assert ledger.weekly(picks, RESULTS, LINES) == []


def test_underdog_and_survivor_stay_out_of_the_points():
    """Different pools, different objectives. One number over both means nothing."""
    picks = [
        _pick("Griffin", G1, "BBB", "underdog"),
        _pick("Griffin", G2, "CCC", "survivor"),
    ]
    assert ledger.weekly(picks, RESULTS, LINES) == []


def test_standings_rank_on_share_of_the_points_that_were_available():
    rows = [
        {"week": 1, "entry": "TEAM", "points": 1.0, "available": 4.0, "running": 1.0},
        {
            "week": 1,
            "entry": "Majority",
            "points": 3.0,
            "available": 4.0,
            "running": 3.0,
        },
    ]
    table = ledger.standings(rows)
    assert [t["entry"] for t in table] == ["Majority", "TEAM"]
    assert table[0]["share"] == 0.75
