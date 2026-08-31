"""Cuts of our own pick history, computed honestly (#66).

Two corrections separate this from a naive group-by, and both move the
numbers a lot:

1. **Clustering.** The room piles onto the same games, so 167 picks in a
   cell are not 167 trials — they are ~71 games carrying 2.4 votes each.
   Rates are computed per *game*: a game the room split 4-2 contributes
   0.667, not four wins and two losses. Ignoring this inflated the
   z-scores behind the spread bands on the team board by roughly the
   square root of the votes-per-game.

2. **Shrinkage.** One season is ~130 distinct games and a cut of it is
   far fewer, so a raw cell rate is mostly noise. Each cell is pulled
   toward the overall rate by ``n / (n + k)``, with ``k`` estimated from
   the data by method of moments: if the spread between cells is no
   wider than binomial noise predicts, ``k`` is large and everything
   collapses to the base rate, which is the correct answer when a split
   carries no signal.

Pure stdlib on plain dicts — this runs on the deployed API, same
constraint as :mod:`g_nfl.picks.grading`.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from g_nfl.picks.grading import ATS_PICK_TYPES, BREAK_EVEN, WIN_PROFIT, grade_pick

# Prior strength floor, in games. Method of moments can hand back a tiny k
# when cells happen to spread wide, which would let a 12-game cell speak as
# loudly as a 90-game one. 25 games is about a third of a season of one cut.
MIN_PRIOR_GAMES = 25.0


class Cell:
    """One slice of the record, aggregated per game rather than per pick."""

    __slots__ = ("key", "games", "wins", "picks", "pick_wins")

    def __init__(self, key: Any):
        self.key = key
        self.games = 0.0
        self.wins = 0.0
        self.picks = 0
        self.pick_wins = 0

    @property
    def raw_pct(self) -> float | None:
        return self.wins / self.games if self.games else None

    @property
    def pick_pct(self) -> float | None:
        """The naive per-pick rate, kept only so the inflation is visible."""
        return self.pick_wins / self.picks if self.picks else None

    @property
    def units(self) -> float:
        """Profit at -110 over the actual picks, not the clustered games."""
        return self.pick_wins * WIN_PROFIT - (self.picks - self.pick_wins)

    def z(self, base: float = BREAK_EVEN) -> float | None:
        """Standard deviations from `base`, on the clustered denominator."""
        if not self.games:
            return None
        se = math.sqrt(base * (1 - base) / self.games)
        return (self.raw_pct - base) / se if se else None


def graded_rows(
    picks: list[dict[str, Any]],
    results: dict[str, float],
    lines: dict[str, float],
    pool_lines: dict[str, float] | None = None,
    market_lines: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Every ATS pick with its outcome, line and derived attributes.

    `pool_lines` and `market_lines` are optional and unlock the gap columns.
    Whether the pool prices our side better or worse than the market is the
    largest single leak in the record: 28% of picks take the side the pool
    prices worse, and those hit 45.2% (n=1098, z=-3.20). See
    notes/pick-behaviour.md.
    """
    pool_lines = pool_lines or {}
    market_lines = market_lines or {}

    rows = []
    for p in picks:
        if p.get("pick_type", "regular") not in ATS_PICK_TYPES:
            continue
        gid = p["game_id"]
        outcome = grade_pick(p, results.get(gid), lines.get(gid))
        if outcome not in ("win", "loss"):
            continue
        parts = gid.split("_")
        home, away = parts[3], parts[2]
        line = lines.get(gid)
        picked_home = p["team_picked"] == home

        picked_pool = from_picked(pool_lines.get(gid), picked_home)
        picked_market = from_picked(market_lines.get(gid), picked_home)
        gap = (
            None
            if picked_pool is None or picked_market is None
            else picked_pool - picked_market
        )

        rows.append(
            {
                "picker": p["picker"],
                "season": p.get("season"),
                "week": p["week"],
                "game_id": gid,
                "slot": p.get("pick_type", "regular"),
                "team": p["team_picked"],
                "opp": away if picked_home else home,
                "picked_home": picked_home,
                "line": line,
                "picked_spread": from_picked(line, picked_home),
                "picked_pool": picked_pool,
                "picked_market": picked_market,
                # points the pool hands our side over the market. Positive is
                # free value, negative means we picked into the gap.
                "gap": gap,
                "gap_side": None if gap is None else gap_side(gap),
                "won": outcome == "win",
            }
        )
    return rows


def from_picked(home_spread: float | None, picked_home: bool) -> float | None:
    """A home-perspective spread seen from the picked team's side.

    Positive means the side is getting points, negative means laying them.
    """
    if home_spread is None:
        return None
    return -home_spread if picked_home else home_spread


def gap_side(gap: float, tol: float = 0.01) -> str:
    """'better', 'same' or 'worse', from the picked side's point of view."""
    if gap > tol:
        return "better"
    if gap < -tol:
        return "worse"
    return "same"


def cells(
    rows: Iterable[dict[str, Any]], key: Callable[[dict], Any]
) -> dict[Any, Cell]:
    """Group rows into cells, weighting each game by the room's lean on it.

    A game contributes one observation in total, split across the cells its
    votes fall in. So a game the room takes 4-2 gives 0.667 of an observation
    to the majority side's cell and 0.333 to the other, and a 6-0 gives a whole
    one to a single cell.

    The weighting is what makes a venue cut mean anything. The room takes both
    sides of 54% of the games it picks (82% in 2025), and counting each side as
    a full game made the home and road rows exact complements: every band summed
    to 100%, so the table reported which team covered instead of whether the
    room was right. A 3-3 split now cancels itself, which is the honest reading
    of a game the room had no collective opinion on.

    See notes/pick-behaviour.md, "The board constants were measuring the wrong
    thing".
    """
    rows = list(rows)
    votes_per_game: dict[str, int] = defaultdict(int)
    for r in rows:
        if key(r) is not None:
            votes_per_game[r["game_id"]] += 1

    # cell -> game -> [won flags from this cell's votes on that game]
    per_game: dict[Any, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    out: dict[Any, Cell] = {}
    for r in rows:
        k = key(r)
        if k is None:
            continue
        per_game[k][r["game_id"]].append(r["won"])
        cell = out.setdefault(k, Cell(k))
        cell.picks += 1
        cell.pick_wins += int(r["won"])

    for k, games in per_game.items():
        cell = out[k]
        for game_id, won in games.items():
            share = votes_per_game[game_id]
            cell.games += len(won) / share
            cell.wins += sum(won) / share
    return out


def prior_strength(cs: Iterable[Cell], base: float) -> float:
    """Method-of-moments `k` for shrinking cell rates toward `base`.

    Compares how far the cells actually spread against how far binomial
    noise alone would scatter them. The excess is the signal variance
    tau^2, and `k = base(1-base) / tau^2` is the number of games a cell
    needs before it is believed half way. No excess spread means no
    signal, so `k` is infinite and every cell collapses onto the base
    rate — the right answer when a split carries nothing.
    """
    sized = [c for c in cs if c.games >= 2]
    total = sum(c.games for c in sized)
    if len(sized) < 2 or not total:
        return math.inf
    var = base * (1 - base)
    # spread of the cell rates, weighted by how much each cell is worth
    observed = sum(c.games * (c.raw_pct - base) ** 2 for c in sized) / total
    # spread binomial noise alone would produce, weighted identically:
    # sum(n_i * var/n_i) / sum(n_i) == m * var / total
    noise = len(sized) * var / total
    tau_sq = observed - noise
    if tau_sq <= 0:
        return math.inf
    return max(MIN_PRIOR_GAMES, var / tau_sq)


def shrink(cell: Cell, base: float, k: float) -> float:
    """Cell rate pulled toward `base` by its own sample size."""
    if not cell.games or math.isinf(k):
        return base
    w = cell.games / (cell.games + k)
    return base + w * (cell.raw_pct - base)


def summarize(
    rows: list[dict[str, Any]],
    key: Callable[[dict], Any],
    base: float | None = None,
) -> list[dict[str, Any]]:
    """One cut of the record, raw and shrunk, sorted by sample size."""
    cs = cells(rows, key)
    if not cs:
        return []
    if base is None:
        total_games = sum(c.games for c in cs.values())
        base = (
            sum(c.wins for c in cs.values()) / total_games
            if total_games
            else BREAK_EVEN
        )
    k = prior_strength(cs.values(), base)
    out = [
        {
            "key": c.key,
            "picks": c.picks,
            "games": round(c.games, 1),
            "pick_pct": c.pick_pct,
            "pct": c.raw_pct,
            "shrunk_pct": shrink(c, base, k),
            "units": round(c.units, 2),
            "z": c.z(),
        }
        for c in cs.values()
    ]
    out.sort(key=lambda d: d["games"], reverse=True)
    return out


def team_appetite(
    rows: list[dict[str, Any]],
    schedule: Iterable[tuple[str, str, str]],
    pickers: int,
) -> list[dict[str, Any]]:
    """Which teams we buy more often than chance, and whether it paid.

    A raw pick count says nothing: a team that plays every week has more
    chances to be picked than one on bye, and a team in tight games gets
    looked at more. `appetite` is the share of a team's *available*
    games in which someone in the room took them, so 1.0 means we backed
    them every time we could have and 0.0 means never.

    `schedule` is (game_id, away, home) for every graded game.
    """
    available: dict[str, int] = defaultdict(int)
    for _gid, away, home in schedule:
        available[away] += 1
        available[home] += 1

    taken: dict[str, set] = defaultdict(set)
    votes: dict[str, int] = defaultdict(int)
    for r in rows:
        taken[r["team"]].add(r["game_id"])
        votes[r["team"]] += 1

    by_team = cells(rows, lambda r: r["team"])
    out = []
    for team, chances in sorted(available.items()):
        cell = by_team.get(team)
        picked_games = len(taken[team])
        out.append(
            {
                "team": team,
                "available": chances,
                "picked_games": picked_games,
                "picks": votes[team],
                # 0 = never took them, 1 = took them every time we could
                "appetite": picked_games / chances if chances else None,
                # how hard the room piled on when it did take them
                "votes_per_pick": votes[team] / picked_games if picked_games else None,
                "pct": cell.raw_pct if cell else None,
                "units": round(cell.units, 2) if cell else 0.0,
            }
        )
    out.sort(key=lambda d: d["appetite"] or 0, reverse=True)
    return out
