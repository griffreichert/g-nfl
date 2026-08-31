"""The No Homers guardrails: the sides the record says we should not buy (#58).

One definition, three consumers. The live board flags a side through
:func:`flags`, the backtest replays history through :func:`fit`, and the report
for the room renders the same table. No rate is ever written by hand, which is
how the board ended up telling everyone that home teams in the 3-7 band hit
36.6% when six seasons put that cell at 50.8%.

A guardrail is a veto. Out of sample the band rating separates 51.1% from 45.0%
(z=-4.09) yet cannot rank within an entry, because six picks in one entry rarely
span two cells. So these say "not this side", never "this side". See
notes/pick-behaviour.md.

Knobs live in config/guardrails.yaml.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from g_nfl.picks.analytics import cells, shrink
from g_nfl.utils.paths import PROJECT_DIR

CONFIG_PATH = PROJECT_DIR / "config" / "guardrails.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    return yaml.safe_load((path or CONFIG_PATH).read_text())


@dataclass(frozen=True)
class Rule:
    """One thing the record says not to buy.

    `matches` reads a row from :func:`g_nfl.picks.analytics.graded_rows`, which
    is also the shape the board builds for a candidate side.
    """

    id: str
    label: str
    blurb: str
    matches: Callable[[dict[str, Any]], bool]
    #: True when the rule reads data unavailable at pick time. Shown on the
    #: board, kept out of the walk-forward backtest.
    advisory: bool = False


@dataclass
class RuleFit:
    """What a rule scored, and whether it earned a place on the board."""

    rule: Rule
    games: float
    picks: int
    pct: float | None
    shrunk_pct: float
    base: float
    units: float
    by_season: dict[int, float | None] = field(default_factory=dict)
    qualifies: bool = False
    reason: str = ""

    @property
    def bad_seasons(self) -> int:
        return sum(
            1 for p in self.by_season.values() if p is not None and p < self.base
        )


def build_rules(config: dict[str, Any]) -> list[Rule]:
    """The rule list, with boundaries taken from config."""
    close, big = config["bands"]
    low, high = config["lay_trap"]["low"], config["lay_trap"]["high"]
    active = config["rules"]

    def band(row: dict[str, Any]) -> float | None:
        s = row.get("picked_spread")
        return None if s is None else abs(s)

    def road_7_plus(row):
        b = band(row)
        return b is not None and b > big and not row["picked_home"]

    def home_0_3(row):
        b = band(row)
        return b is not None and b <= close and row["picked_home"]

    def lay_trap(row):
        s = row.get("picked_spread")
        return s is not None and -high <= s <= -low

    def pool_worse(row):
        return row.get("gap_side") == "worse"

    catalogue = [
        Rule(
            "road_7_plus",
            "Road side of a 7+ line",
            "Worst cell in the record and negative in every season.",
            road_7_plus,
        ),
        Rule(
            "home_0_3",
            "Home side of a close game",
            "Negative in every season. We buy home teams in tight games.",
            home_0_3,
        ),
        Rule(
            "lay_trap",
            f"Laying {low} to {high}",
            "The one spread bucket that is clearly bad. The other seven are "
            "within 2 points of even.",
            lay_trap,
        ),
        Rule(
            "pool_worse_than_market",
            "Pool prices this side worse than the market",
            "The largest single leak: 28% of our picks take this side.",
            pool_worse,
            advisory=True,
        ),
    ]
    return [
        Rule(
            r.id,
            r.label,
            r.blurb,
            r.matches,
            advisory=active[r.id].get("advisory", r.advisory),
        )
        for r in catalogue
        if active.get(r.id, {}).get("active", False)
    ]


def _rate(rows: list[dict[str, Any]], rule: Rule) -> tuple[float | None, float, int]:
    """(rate, games, picks) for the rows this rule matches, lean-weighted."""
    grouped = cells(rows, lambda r, _r=rule: _r.id if _r.matches(r) else "other")
    cell = grouped.get(rule.id)
    if cell is None:
        return None, 0.0, 0
    return cell.raw_pct, cell.games, cell.picks


def fit(
    rows: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    rules: Iterable[Rule] | None = None,
) -> list[RuleFit]:
    """Score every active rule against a pick record.

    `rows` come from :func:`g_nfl.picks.analytics.graded_rows`. Pass only the
    seasons a caller is allowed to see: the backtest fits on prior seasons and
    scores the held-out one, so leaking here would defeat the whole exercise.
    """
    config = config or load_config()
    rules = list(rules if rules is not None else build_rules(config))
    if not rows:
        return []

    whole = cells(rows, lambda r: "all")["all"]
    base = whole.raw_pct or 0.0
    bar = config["display"]

    fits = []
    for rule in rules:
        matched = [r for r in rows if rule.matches(r)]
        pct, games, picks = _rate(rows, rule)
        by_season = {}
        for season in sorted({r["season"] for r in rows if "season" in r}):
            season_rows = [r for r in rows if r.get("season") == season]
            by_season[season] = _rate(season_rows, rule)[0]

        cell = cells(rows, lambda r, _r=rule: _r.id if _r.matches(r) else "other").get(
            rule.id
        )
        shrunk = shrink(cell, base, config["prior_games"]) if cell else base

        wins = sum(1 for r in matched if r["won"])
        fits.append(
            RuleFit(
                rule=rule,
                games=games,
                picks=picks,
                pct=pct,
                shrunk_pct=shrunk,
                base=base,
                units=round(wins * 0.909091 - (len(matched) - wins), 2),
                by_season=by_season,
            )
        )

    for f in fits:
        f.qualifies, f.reason = _qualifies(f, bar)
    return fits


def _qualifies(f: RuleFit, bar: dict[str, Any]) -> tuple[bool, str]:
    """Whether a rule has earned the right to flag a pick on the board."""
    if f.games < bar["min_games"]:
        return False, f"only {f.games:.0f} games, needs {bar['min_games']}"
    edge = f.base - f.shrunk_pct
    if edge < bar["min_edge_below_base"]:
        return False, f"shrinks to {f.shrunk_pct:.1%} against a base of {f.base:.1%}"
    seasons = len(f.by_season)
    if f.bad_seasons < min(bar["min_bad_seasons"], seasons):
        return False, f"below base in only {f.bad_seasons} of {seasons} seasons"
    return True, f"{f.shrunk_pct:.1%} shrunk, bad in {f.bad_seasons}/{seasons} seasons"


def flags(row: dict[str, Any], fits: Iterable[RuleFit]) -> list[RuleFit]:
    """Every qualifying guardrail this side trips. Empty is the common case."""
    return [f for f in fits if f.qualifies and f.rule.matches(row)]
