"""Survivor planner (#72).

The Hungarian implementation is hand-rolled because the deployed API has
no scipy, so it is checked against scipy — which the dev group does have —
on random matrices. The planning tests then pin the behaviour the pool
actually cares about: not spending a team you will want later.
"""

import math
import random

import pytest

from g_nfl.picks.survivor import (
    Board,
    hungarian,
    plan,
    rank_week,
    win_probability,
)


def _cost(matrix, col_to_row):
    return sum(matrix[col_to_row[j]][j] for j in range(len(col_to_row)))


@pytest.mark.parametrize("seed", range(25))
def test_hungarian_matches_scipy(seed):
    """Same optimal cost as scipy on random rectangular matrices."""
    scipy_opt = pytest.importorskip("scipy.optimize")
    rng = random.Random(seed)
    n = rng.randint(2, 9)  # teams
    m = rng.randint(1, n)  # weeks
    matrix = [[rng.uniform(0, 10) for _ in range(m)] for _ in range(n)]

    mine = _cost(matrix, hungarian(matrix))
    rows, cols = scipy_opt.linear_sum_assignment(matrix)
    theirs = sum(matrix[r][c] for r, c in zip(rows, cols, strict=True))
    assert mine == pytest.approx(theirs, abs=1e-9)


def test_hungarian_assigns_every_column_to_a_distinct_row():
    matrix = [[4.0, 1.0], [2.0, 0.0], [3.0, 3.0]]
    got = hungarian(matrix)
    assert len(got) == 2
    assert len(set(got)) == 2


def test_hungarian_rejects_more_columns_than_rows():
    with pytest.raises(ValueError):
        hungarian([[1.0, 2.0, 3.0]])


def test_win_probability_is_centred_and_monotone():
    assert win_probability(0) == pytest.approx(0.5)
    assert win_probability(7) > win_probability(3) > 0.5
    assert win_probability(-7) == pytest.approx(1 - win_probability(7))


def _board(entries):
    """entries: {(team, week): win_prob}"""
    teams = sorted({t for t, _ in entries})
    weeks = sorted({w for _, w in entries})
    b = Board(teams, weeks)
    for (t, w), p in entries.items():
        b.add(t, w, p, {"opponent": "OPP", "spread": None, "home": True})
    return b, teams, weeks


def test_plan_spends_the_team_it_cannot_use_better_later():
    """The case the planner exists for: AAA is the bigger favourite this
    week AND a monster next week, so the plan must spend BBB now. Greedy
    takes AAA and wastes the 0.95."""
    b, teams, weeks = _board(
        {
            ("AAA", 1): 0.66,
            ("AAA", 2): 0.95,  # huge favourite in week 2
            ("BBB", 1): 0.65,
            ("BBB", 2): 0.50,
        }
    )
    assert max(teams, key=lambda t: b.prob[(t, 1)]) == "AAA"  # what greedy does
    got = plan(b, teams, weeks)
    assert {p["week"]: p["team"] for p in got["picks"]} == {1: "BBB", 2: "AAA"}


def test_rank_week_orders_by_the_plan_not_by_this_week():
    b, teams, weeks = _board(
        {("AAA", 1): 0.66, ("AAA", 2): 0.95, ("BBB", 1): 0.65, ("BBB", 2): 0.50}
    )
    ranked = rank_week(b, teams, weeks)
    assert [r["team"] for r in ranked] == ["BBB", "AAA"]
    # BBB is the plan, so it costs nothing; AAA costs real survival
    assert ranked[0]["forward_cost"] == pytest.approx(0.0, abs=1e-12)
    assert ranked[1]["forward_cost"] > 0
    # and the reason to wait is reported
    assert ranked[1]["best_week"]["week"] == 2


def test_bye_weeks_are_never_assigned():
    b, teams, weeks = _board(
        {("AAA", 1): 0.60, ("BBB", 1): 0.55, ("BBB", 2): 0.55}
    )  # AAA has no week 2
    got = plan(b, teams, weeks)
    by_week = {p["week"]: p["team"] for p in got["picks"]}
    assert by_week == {1: "AAA", 2: "BBB"}
    assert all(r["team"] != "AAA" for r in rank_week(b, teams, [2]))


def test_no_plan_when_teams_run_out():
    b, teams, weeks = _board({("AAA", 1): 0.6, ("AAA", 2): 0.6})
    assert plan(b, teams, weeks) is None


def test_survival_is_the_product_of_the_legs():
    b, teams, weeks = _board(
        {("AAA", 1): 0.5, ("AAA", 2): 0.5, ("BBB", 1): 0.8, ("BBB", 2): 0.4}
    )
    got = plan(b, teams, weeks)
    assert got["survival"] == pytest.approx(math.prod(p["prob"] for p in got["picks"]))
    # best is BBB week 1 (.8) then AAA week 2 (.5) = .40
    assert got["survival"] == pytest.approx(0.40)


def test_pins_are_honoured_and_the_rest_planned_around_them():
    b, teams, weeks = _board(
        {("AAA", 1): 0.66, ("AAA", 2): 0.95, ("BBB", 1): 0.65, ("BBB", 2): 0.50}
    )
    got = plan(b, teams, weeks, {1: "AAA"})
    assert {p["week"]: p["team"] for p in got["picks"]} == {1: "AAA", 2: "BBB"}
    assert [p["pinned"] for p in got["picks"]] == [True, False]
    # insisting costs survival, which is the number the planner exists to show
    assert got["survival"] < plan(b, teams, weeks)["survival"]


def test_a_pin_on_a_bye_is_not_a_plan():
    b, teams, weeks = _board({("AAA", 1): 0.6, ("BBB", 1): 0.55, ("BBB", 2): 0.55})
    assert plan(b, teams, weeks, {2: "AAA"}) is None  # AAA has no week 2


def test_rank_week_holds_other_pins_fixed():
    """AAA is reserved for week 2, so week 1 must not offer it, and the
    week-1 ranking is priced against a season that already spends it."""
    b, teams, weeks = _board(
        {("AAA", 1): 0.90, ("AAA", 2): 0.95, ("BBB", 1): 0.65, ("BBB", 2): 0.50}
    )
    ranked = rank_week(b, teams, weeks, pins={2: "AAA"})
    assert [r["team"] for r in ranked] == ["BBB"]
    assert ranked[0]["plan_survival"] == pytest.approx(0.65 * 0.95)


def test_rank_week_can_rank_a_later_week():
    b, teams, weeks = _board(
        {("AAA", 1): 0.66, ("AAA", 2): 0.95, ("BBB", 1): 0.65, ("BBB", 2): 0.50}
    )
    assert {r["team"] for r in rank_week(b, teams, weeks, week=2)} == {"AAA", "BBB"}
