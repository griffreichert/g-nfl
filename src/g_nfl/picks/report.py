"""The case, in one artifact, generated from the code that runs the app (#58).

Everything the room is asked to accept comes out of the same functions the board
and the backtest use. Nothing is retyped, so the argument cannot drift from the
app the way `consensus.ts` drifted from the notes for months.

    make case                          # to stdout
    make case ARGS="--output case.md"  # to a file

Slides later are an export of this, never a fresh set of numbers.
"""

from __future__ import annotations

from typing import Any

from g_nfl.picks import backtest
from g_nfl.picks.calendar import current_season
from g_nfl.picks.guardrails import fit
from g_nfl.picks.history import TEAM_PICKERS, load_history

CAVEAT = """The rule structure was chosen after looking at all six seasons.
Only the rates are held out. The first honest out-of-sample season is 2026, so
read everything above as "this is what the record says", never as "this is what
will happen"."""


def _rules_section(rows: list[dict[str, Any]]) -> list[str]:
    fits = fit([r for r in rows if r["picker"] not in TEAM_PICKERS])
    out = [
        "## What we are bad at",
        "",
        "Each row is a cut of our own picks. A rule reaches the board only when it",
        "sits below the field's own rate *and* sat below it in most seasons, so a",
        "cell that happens to look bad once does not get to lecture anybody.",
        "",
        "| rule | games | raw | shrunk | field | units | on the board |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in fits:
        verdict = "**yes**" if f.qualifies else f"no, {f.reason}"
        if f.qualifies and f.rule.advisory:
            verdict = "**advisory** (reads the closing line, so it cannot veto)"
        out.append(
            f"| {f.rule.label} | {f.games:.0f} | {(f.pct or 0):.1%} | "
            f"{f.shrunk_pct:.1%} | {f.base:.1%} | {f.units:.0f} | {verdict} |"
        )

    out += ["", "Per season, so you can see which ones hold up:", ""]
    seasons = sorted({s for f in fits for s in f.by_season})
    out += [
        "| rule | " + " | ".join(str(s) for s in seasons) + " |",
        "|---" * (len(seasons) + 1) + "|",
    ]
    for f in fits:
        cells = " | ".join(
            f"{f.by_season[s]:.0%}" if f.by_season.get(s) is not None else "-"
            for s in seasons
        )
        out.append(f"| {f.rule.label} | {cells} |")
    return out


def _backtest_section(rows: list[dict[str, Any]]) -> list[str]:
    text = backtest.report(rows, set(TEAM_PICKERS))
    # the rules table is already above, and the caveat has its own section at
    # the end, so keep the replay table alone
    body = text[text.index("## Replay") : text.index("The rule structure")]
    return [
        "## What avoiding them would have been worth",
        "",
        "Every entry we actually submitted, replayed with the guardrails applied.",
        "*Flip* takes the other side of the same game; *substitute* swaps in the",
        "room's most-agreed unflagged game. Leave-one-season-out fits on the other",
        "four seasons, walk-forward on earlier ones only.",
        "",
        *body.splitlines()[2:],
    ]


def _ledger_section(season: int) -> list[str]:
    from g_nfl.api.main import get_ledger

    table = get_ledger(season)
    if not table.standings:
        return ["## This season", "", f"Nothing graded yet for {season}."]

    out = [
        "## This season",
        "",
        f"{season}, in pool points. **Majority** is the side most of us took;",
        "**Best member** follows whoever led going into that week.",
        "",
        "| entry | points | available | share | weeks |",
        "|---|---|---|---|---|",
    ]
    for e in table.standings:
        share = f"{e.share:.1%}" if e.share is not None else "-"
        out.append(
            f"| {e.entry} | {e.points:.1f} | {e.available:.0f} | {share} | {e.weeks} |"
        )
    return out


def build(season: int | None = None) -> str:
    """The whole case as markdown."""
    season = season or current_season()
    rows = load_history(drop_team=False)

    parts = [
        "# Why we pick this way",
        "",
        "The pool went 1258-1252 last season, 50.12%. Its best entry sits exactly",
        "where chance puts the best of sixteen, so nobody in it has shown skill.",
        "Both bottom entries are past the noise threshold on the losing side, and",
        "one of them is us. In this pool it is measurably easier to be bad than to",
        "be good, so the goal is to stop losing.",
        "",
        *_rules_section(rows),
        "",
        *_backtest_section(rows),
        "",
        *_ledger_section(season),
        "",
        "## Read this before quoting any of it",
        "",
        CAVEAT,
    ]
    return "\n".join(parts)


def main() -> None:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--season", type=int)
    parser.add_argument("--output", help="write here instead of stdout")
    args = parser.parse_args()

    text = build(args.season)
    if args.output:
        Path(args.output).write_text(text)
        print(f"wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
