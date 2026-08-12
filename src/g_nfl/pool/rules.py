"""Candidate picking rules, and a walk-forward test that can kill them.

A rule names one side of a game from information available before kickoff,
and is graded against the **pool** spread, which is what the pool scores.
Rules live here as data so the same definition drives the backtest and
whatever the site eventually shows.

Two things this module is careful about:

**Selection.** Twenty rules were tried against five seasons, so the best
one is guaranteed to look good. `walk_forward` picks a rule using only
seasons before the one it scores, which is the only number worth quoting.

**Look-ahead.** Rules comparing the pool line to the market carry
`needs_close=True`. The backtest uses nflverse `spread_line`, the closing
number, which is not knowable when picks are due. Most of a week's line
movement has happened by Sunday morning, so a live market line is a close
stand-in — but the backtest flatters these rules by some unknown amount,
and only a stored pick-time snapshot can settle by how much.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import polars as pl

BREAK_EVEN_110 = 0.5238  # the number to beat if these were -110 bets


@dataclass(frozen=True)
class Rule:
    """`take_home` and `subset` are polars expressions over a board frame."""

    name: str
    take_home: pl.Expr
    subset: pl.Expr = field(default_factory=lambda: pl.lit(True))
    needs_close: bool = False
    description: str = ""


def prepare(board: pl.DataFrame) -> pl.DataFrame:
    """Add the columns rules are written against, and drop pushes.

    `home_num` is the home team's own number: positive means the home team
    is the underdog and getting points.
    """
    return (
        board.filter(pl.col("result").is_not_null())
        .with_columns(
            home_num=-pl.col("pool_spread"),
            gap=pl.col("pool_spread") - pl.col("spread_line"),
            home_cover=pl.col("result") - pl.col("pool_spread"),
        )
        .filter(pl.col("home_cover") != 0)
    )


def _rules() -> list[Rule]:
    home_num, gap = pl.col("home_num"), pl.col("gap")
    rules = [
        Rule("always home", pl.lit(True), description="Take the home team every time."),
        Rule(
            "always the dog",
            home_num > 0,
            description="Take whoever is getting points.",
        ),
    ]
    for k in (0, 3, 7):
        rules.append(
            Rule(
                f"home dog +{k} or more",
                pl.lit(True),
                subset=home_num >= k,
                description=f"Take the home team whenever it is getting {k} or more.",
            )
        )
        rules.append(
            Rule(
                f"home favourite laying {k}+",
                pl.lit(True),
                subset=home_num <= -k,
                description=f"Take the home team whenever it lays {k} or more.",
            )
        )
        rules.append(
            Rule(
                f"road dog +{k} or more",
                pl.lit(False),
                subset=home_num <= -k,
                description=f"Take the road team whenever it is getting {k} or more.",
            )
        )
    for k in (0.5, 1.0, 2.0):
        rules.append(
            Rule(
                f"pool-better side, gap >={k}",
                gap < 0,
                subset=gap.abs() >= k,
                needs_close=True,
                description=(
                    f"When the pool line differs from the market by {k} or more, "
                    "take the side the pool prices better."
                ),
            )
        )
    return rules


RULES = _rules()
BY_NAME = {r.name: r for r in RULES}


def _z(wins: int, n: int, p0: float = 0.5) -> float:
    if n == 0:
        return 0.0
    return (wins / n - p0) / math.sqrt(p0 * (1 - p0) / n)


def score(board: pl.DataFrame, rule: Rule) -> tuple[int, int]:
    """(n, wins) for a rule over a prepared board."""
    d = board.filter(rule.subset)
    if d.height == 0:
        return 0, 0
    won = (
        pl.when(rule.take_home)
        .then(pl.col("home_cover") > 0)
        .otherwise(pl.col("home_cover") < 0)
    )
    return d.height, int(d.select(won.sum()).item())


def evaluate(board: pl.DataFrame, rules: list[Rule] | None = None) -> pl.DataFrame:
    """In-sample record for every rule. Selection bias not accounted for."""
    b = prepare(board)
    rows = []
    for rule in rules or RULES:
        n, w = score(b, rule)
        rows.append(
            {
                "rule": rule.name,
                "needs_close": rule.needs_close,
                "n": n,
                "hit": round(w / n, 4) if n else None,
                "z": round(_z(w, n), 2),
            }
        )
    return pl.DataFrame(rows).sort("z", descending=True)


def per_season(board: pl.DataFrame, rule: Rule) -> pl.DataFrame:
    """A rule's record season by season — the stability check."""
    b = prepare(board)
    rows = []
    for season in sorted(b["season"].unique().to_list()):
        n, w = score(b.filter(pl.col("season") == season), rule)
        rows.append(
            {
                "season": season,
                "n": n,
                "hit": round(w / n, 4) if n else None,
                "z": round(_z(w, n), 2),
            }
        )
    return pl.DataFrame(rows)


def walk_forward(
    board: pl.DataFrame,
    rules: list[Rule] | None = None,
    *,
    min_train_n: int = 60,
) -> pl.DataFrame:
    """Pick a rule on prior seasons only, then score it on the held-out one.

    This is the number to quote. Anything chosen with the test season in
    view is a description of the past, not a prediction.
    """
    b = prepare(board)
    pool = rules or RULES
    seasons = sorted(b["season"].unique().to_list())

    rows = []
    for i, season in enumerate(seasons):
        if i == 0:
            continue  # nothing to train on
        train = b.filter(pl.col("season") < season)
        test = b.filter(pl.col("season") == season)

        best, best_hit = None, -1.0
        for rule in pool:
            n, w = score(train, rule)
            if n >= min_train_n and w / n > best_hit:
                best, best_hit = rule, w / n
        if best is None:
            continue

        n, w = score(test, best)
        rows.append(
            {
                "season": season,
                "chosen": best.name,
                "train_hit": round(best_hit, 4),
                "n": n,
                "hit": round(w / n, 4) if n else None,
                "wins": w,
            }
        )

    out = pl.DataFrame(rows)
    if out.height:
        total_n, total_w = int(out["n"].sum()), int(out["wins"].sum())
        print(
            f"out-of-sample: {total_w}/{total_n} = {total_w / total_n:.4f} "
            f"(z={_z(total_w, total_n):.2f}, break-even {BREAK_EVEN_110})"
        )
    return out
