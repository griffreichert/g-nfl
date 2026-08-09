"""Survivor planning: which team to spend this week, and what it costs (#72).

The pool takes one team a week, never reusing one, and you are out on the
second outright loss (notes/SCORING.md). Picking the biggest favourite
every week is the obvious strategy and the wrong one: it spends teams
that would be even bigger favourites later, and leaves the closing weeks
with nothing but coin flips.

So the real problem is an assignment: match remaining teams to remaining
weeks so the whole path survives, not just this Sunday. Maximising the
product of weekly win probabilities is the same as minimising the sum of
-log p, which is a linear assignment problem and is solved exactly here.

The number that actually answers "which one do I burn?" is not a team's
win probability this week — it is the **forward cost**: how much worse
the best remaining plan becomes if you spend that team now. A 62% team
you cannot use better later beats a 66% team who is a 13-point favourite
in three weeks' time.

Pure stdlib. This runs on the deployed API, which has neither scipy nor
numpy, so the Hungarian solver is implemented below rather than imported.
"""

from __future__ import annotations

import math
from typing import Any

# Margin is modelled as normal around the spread. SPREAD_STDEV lives in
# utils.config but importing it drags nothing extra in.
from g_nfl.utils.config import SPREAD_STDEV

# Cost used for a pairing that must never be chosen (bye week, team already
# spent). Large enough to dominate any real -log p, finite so the solver
# still returns a feasible assignment if it is forced into one.
FORBIDDEN = 1e6


def win_probability(margin: float, stdev: float = SPREAD_STDEV) -> float:
    """P(a team favoured by `margin` points wins outright).

    Normal CDF via math.erf — the margin distribution is near enough
    normal for this, and a survivor pick never turns on the third
    decimal. Ties are folded into the loss side, which is the pool rule.
    """
    return 0.5 * (1.0 + math.erf(margin / (stdev * math.sqrt(2.0))))


def hungarian(cost: list[list[float]]) -> list[int]:
    """Min-cost assignment of every column to a distinct row.

    O(n^2 m) shortest-augmenting-path with potentials. Rows are teams and
    columns are weeks, and there are always more teams than weeks left,
    so every week gets filled and some teams go unused.

    The algorithm needs rows <= columns to terminate — with spare rows it
    keeps looking for an augmenting path that cannot exist — so it is run
    on the transpose and the result mapped back.

    Returns `col_to_row[j]` = the row assigned to column j.
    """
    n_rows = len(cost)
    n_cols = len(cost[0]) if n_rows else 0
    if n_cols > n_rows:
        raise ValueError(
            f"need at least as many rows as columns, got {n_rows}x{n_cols}"
        )
    if not n_cols:
        return []

    # transposed: n = weeks (few), m = teams (many)
    n, m = n_cols, n_rows
    at = [[cost[r][c] for r in range(n_rows)] for c in range(n_cols)]

    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)  # p[j] = row matched to column j, 0 = unmatched
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = at[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    # p maps transposed-column (team) -> transposed-row (week); invert it
    col_to_row = [0] * n
    for team_idx in range(1, m + 1):
        week_idx = p[team_idx]
        if week_idx:
            col_to_row[week_idx - 1] = team_idx - 1
    return col_to_row


class Board:
    """Win probability for every (team, week) still on the table."""

    def __init__(self, teams: list[str], weeks: list[int]):
        self.teams = teams
        self.weeks = weeks
        self.prob: dict[tuple[str, int], float] = {}
        self.game: dict[tuple[str, int], dict[str, Any]] = {}

    def add(self, team: str, week: int, prob: float, meta: dict[str, Any]) -> None:
        self.prob[(team, week)] = prob
        self.game[(team, week)] = meta

    def matrix(self, teams: list[str], weeks: list[int]) -> list[list[float]]:
        """-log p, with byes and missing games forbidden."""
        rows = []
        for t in teams:
            row = []
            for w in weeks:
                p = self.prob.get((t, w))
                row.append(FORBIDDEN if not p else -math.log(p))
            rows.append(row)
        return rows


def plan(
    board: Board,
    teams: list[str],
    weeks: list[int],
    force: tuple[str, int] | None = None,
) -> dict[str, Any] | None:
    """Best team-to-week assignment over what is left.

    `force` pins one team to one week — that is how the cost of spending
    a team now is measured: solve again with it forced, and compare.
    Returns None when there are fewer usable teams than weeks.
    """
    if len(teams) < len(weeks) or not weeks:
        return None

    use_teams, use_weeks = list(teams), list(weeks)
    pinned = None
    if force:
        team, week = force
        if team not in use_teams or week not in use_weeks:
            return None
        if not board.prob.get((team, week)):
            return None  # bye or no game: not a legal pick
        pinned = (team, week, board.prob[(team, week)])
        use_teams = [t for t in use_teams if t != team]
        use_weeks = [w for w in use_weeks if w != week]

    picks = []
    if use_weeks:
        if len(use_teams) < len(use_weeks):
            return None
        col_to_row = hungarian(board.matrix(use_teams, use_weeks))
        for j, w in enumerate(use_weeks):
            t = use_teams[col_to_row[j]]
            picks.append({"week": w, "team": t, "prob": board.prob.get((t, w), 0.0)})
    if pinned:
        picks.append({"week": pinned[1], "team": pinned[0], "prob": pinned[2]})
    picks.sort(key=lambda d: d["week"])

    # a plan containing an impossible leg is not a plan
    if any(p["prob"] <= 0 for p in picks):
        return None
    survival = 1.0
    for p in picks:
        survival *= p["prob"]
    return {"picks": picks, "survival": survival, "log_survival": math.log(survival)}


def rank_week(board: Board, teams: list[str], weeks: list[int]) -> list[dict[str, Any]]:
    """Every legal pick for the first remaining week, by what it costs.

    `forward_cost` is the drop in whole-season survival probability caused
    by spending this team now instead of letting the plan place it. Zero
    means the optimal plan already wanted this team this week.
    """
    if not weeks:
        return []
    this_week = weeks[0]
    best = plan(board, teams, weeks)
    ceiling = best["log_survival"] if best else None

    out = []
    for team in teams:
        p = board.prob.get((team, this_week))
        if not p:
            continue  # bye, or already played
        forced = plan(board, teams, weeks, force=(team, this_week))
        if forced is None:
            continue
        meta = board.game.get((team, this_week), {})
        out.append(
            {
                "team": team,
                "win_prob": p,
                "spread": meta.get("spread"),
                "opponent": meta.get("opponent"),
                "home": meta.get("home"),
                "plan_survival": forced["survival"],
                "forward_cost": (
                    None if ceiling is None else ceiling - forced["log_survival"]
                ),
                "best_week": _best_week(board, team, weeks),
                "plan": forced["picks"],
            }
        )
    # the whole point: order by the plan, not by this week's win probability
    out.sort(key=lambda d: -d["plan_survival"])
    return out


def _best_week(board: Board, team: str, weeks: list[int]) -> dict[str, Any] | None:
    """The week this team is at their strongest — the reason to wait."""
    best = None
    for w in weeks:
        p = board.prob.get((team, w))
        if p and (best is None or p > best["win_prob"]):
            meta = board.game.get((team, w), {})
            best = {"week": w, "win_prob": p, "spread": meta.get("spread")}
    return best
