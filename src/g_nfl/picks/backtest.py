"""Replay the submitted entry with the guardrails applied (#58).

Scored in pool points, since that is what the pool pays: best bet 2, regular 1,
MNF 1. A veto needs a replacement, because the slots are fixed and an entry with
five picks is not a legal entry. Two policies, reported side by side:

- **flip** — take the other side of the same game. The direct test of "this side
  is bad".
- **substitute** — swap in the room's most-agreed unflagged side that week, on a
  game the entry has not already used. Closer to what the call would do.

Two fitting schemes, because five seasons is not many:

- **walk-forward** — fit on seasons before t, score t. Two clean seasons.
- **leave-one-season-out** — fit on the other four, score t. Five held-out
  seasons, every rate leak-free.

The rule *structure* was chosen after looking at all six seasons. Only the rates
are held out. The first honest out-of-sample season is 2026, and any report
built on this has to say so.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from g_nfl.picks.guardrails import Rule, RuleFit, build_rules, fit, load_config

#: Pool points per slot.
SLOT_POINTS = {"best_bet": 2.0, "regular": 1.0, "mnf": 1.0}


@dataclass
class Replay:
    """One scheme's result over one season."""

    season: int
    entries: int
    actual: float
    adjusted: float
    available: float
    vetoed: int
    swaps_scored: int

    @property
    def delta(self) -> float:
        return self.adjusted - self.actual


def _points(row: dict[str, Any], won: bool | None = None) -> float:
    won = row["won"] if won is None else won
    return SLOT_POINTS.get(row["slot"], 0.0) if won else 0.0


def _consensus(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per game, the side the room agreed on most, and one row carrying it."""
    votes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        votes[(r["game_id"], r["team"])].append(r)
    best: dict[str, dict[str, Any]] = {}
    for (game_id, _team), group in votes.items():
        held = best.get(game_id)
        if held is None or len(group) > held["votes"]:
            best[game_id] = {"votes": len(group), "row": group[0]}
    return best


def replay_season(
    rows: list[dict[str, Any]],
    fits: list[RuleFit],
    policy: str,
    entry_pickers: set[str],
    require_qualified: bool = True,
) -> Replay:
    """Score one season's submitted entries, actual against guarded.

    `require_qualified` off replays a rule the display bar turned down, which
    is how a candidate rule is measured before it has earned the board.
    """
    active = [
        f
        for f in fits
        if (f.qualifies or not require_qualified) and not f.rule.advisory
    ]
    consensus = _consensus(rows)

    entries: dict[tuple[Any, ...], list[dict]] = defaultdict(list)
    for r in rows:
        if r["picker"] in entry_pickers and r["slot"] in SLOT_POINTS:
            entries[(r["season"], r["week"], r["picker"])].append(r)

    by_week: dict[Any, list[dict]] = defaultdict(list)
    for r in rows:
        by_week[(r["season"], r["week"])].append(r)

    actual = adjusted = available = 0.0
    vetoed = swaps_scored = 0

    for (season, week, _picker), picks in entries.items():
        used = {p["game_id"] for p in picks}
        for pick in picks:
            available += SLOT_POINTS.get(pick["slot"], 0.0)
            actual += _points(pick)

            if not any(f.rule.matches(pick) for f in active):
                adjusted += _points(pick)
                continue

            vetoed += 1
            if policy == "flip":
                # graded_rows drops pushes, so the other side won iff we lost
                adjusted += _points(pick, won=not pick["won"])
                swaps_scored += 1
                continue

            swap = _substitute(by_week[(season, week)], consensus, used, active)
            if swap is None:
                # no clean side to move to, so the entry keeps the bad pick
                adjusted += _points(pick)
                continue
            used.add(swap["game_id"])
            adjusted += _points({**swap, "slot": pick["slot"]})
            swaps_scored += 1

    return Replay(
        season=next(iter(entries))[0] if entries else 0,
        entries=len(entries),
        actual=actual,
        adjusted=adjusted,
        available=available,
        vetoed=vetoed,
        swaps_scored=swaps_scored,
    )


def _substitute(
    week_rows: list[dict[str, Any]],
    consensus: dict[str, dict[str, Any]],
    used: set[str],
    active: list[RuleFit],
) -> dict[str, Any] | None:
    """The room's most-agreed unflagged side on a game not already in the entry.

    Candidates are sorted before the pick. Iterating a set of game ids let
    Python's per-process string hashing choose between equally-agreed games, so
    the same backtest returned +7 and +15 on consecutive runs.
    """
    candidates = []
    for game_id in sorted({r["game_id"] for r in week_rows} - used):
        entry = consensus.get(game_id)
        if entry is None:
            continue
        row = entry["row"]
        if any(f.rule.matches(row) for f in active):
            continue
        candidates.append((entry["votes"], game_id, row))
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c[0], c[1]))[2]


def run(
    rows: list[dict[str, Any]],
    entry_pickers: set[str],
    scheme: str = "loso",
    policy: str = "flip",
    config: dict[str, Any] | None = None,
    rules: list[Rule] | None = None,
    require_qualified: bool = True,
) -> list[Replay]:
    """Fit and score every season under one scheme and one policy.

    `rows` must include the entry pickers. Rules are fitted on everyone else,
    so the entry is never part of its own training data. `rules` replaces the
    configured set, which is how a candidate rule is scored before it is added
    to the yaml.
    """
    config = config or load_config()
    rules = build_rules(config) if rules is None else rules
    seasons = sorted({r["season"] for r in rows})
    members = [r for r in rows if r["picker"] not in entry_pickers]

    out = []
    for season in seasons:
        if scheme == "walk_forward":
            train = [r for r in members if r["season"] < season]
        else:
            train = [r for r in members if r["season"] != season]
        if not train:
            continue
        fits = fit(train, config, rules)
        scored = [r for r in rows if r["season"] == season]
        replay = replay_season(scored, fits, policy, entry_pickers, require_qualified)
        replay.season = season
        out.append(replay)
    return out


def _share(points: float, available: float) -> str:
    """`" (44.8%)"`, or nothing at all when no points were on offer.

    Available is zero until the entry has submitted something, which is the
    state of every week 1.
    """
    return f" ({points / available:.1%})" if available else ""


def report(rows: list[dict[str, Any]], entry_pickers: set[str]) -> str:
    """Both schemes, both policies, as a markdown table."""
    from g_nfl.picks.guardrails import fit as fit_rules

    lines = ["# Guardrail backtest", ""]

    fits = fit_rules([r for r in rows if r["picker"] not in entry_pickers])
    lines += ["## Rules, fitted on the full sample", ""]
    lines += ["| rule | games | raw | shrunk | base | units | on the board |"]
    lines += ["|---|---|---|---|---|---|---|"]
    for f in fits:
        lines.append(
            f"| {f.rule.label} | {f.games:.0f} | {(f.pct or 0):.1%} | "
            f"{f.shrunk_pct:.1%} | {f.base:.1%} | {f.units:.0f} | "
            f"{'yes' if f.qualifies else 'no, ' + f.reason} |"
        )

    lines += ["", "## Replay of the submitted entry, in pool points", ""]
    lines += ["| scheme | policy | actual | guarded | available | vetoes | delta |"]
    lines += ["|---|---|---|---|---|---|---|"]
    for scheme in ("loso", "walk_forward"):
        for policy in ("flip", "substitute"):
            res = run(rows, entry_pickers, scheme=scheme, policy=policy)
            a = sum(r.actual for r in res)
            g = sum(r.adjusted for r in res)
            av = sum(r.available for r in res)
            v = sum(r.vetoed for r in res)
            lines.append(
                f"| {scheme} | {policy} | {a:.0f}{_share(a, av)} | "
                f"{g:.0f}{_share(g, av)} | {av:.0f} | {v} | {g - a:+.0f} |"
            )

    lines += [
        "",
        "The rule structure was chosen after looking at all six seasons. Only the",
        "rates are held out. The first honest out-of-sample season is 2026.",
    ]
    return "\n".join(lines)


def main() -> None:
    import argparse

    from g_nfl.picks.history import TEAM_PICKERS, load_history

    parser = argparse.ArgumentParser(description="Backtest the No Homers guardrails")
    parser.add_argument("--output", help="write the report here instead of stdout")
    args = parser.parse_args()

    text = report(load_history(drop_team=False), set(TEAM_PICKERS))
    if args.output:
        from pathlib import Path

        Path(args.output).write_text(text)
        print(f"wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
