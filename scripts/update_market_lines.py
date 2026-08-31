#!/usr/bin/env python3
"""Fetch market spreads and totals from nflverse and store them (#58).

    uv run python scripts/update_market_lines.py --season 2026 --week 1
    uv run python scripts/update_market_lines.py --seasons 2020-2025 --snapshot close
    uv run python scripts/update_market_lines.py --season 2026 --snapshot deadline

`spread_line` is the closing number for a game already played and the current
number for one still ahead, so a backfill of past seasons is always `--snapshot
close`. In-season the crons write `friday` and `deadline`; the deadline pull is
what makes the pool-vs-market gap measurable rather than look-ahead
(notes/pool-spread-edge.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parents[1] / "src"))

import nflreadpy as nfl  # noqa: E402
import polars as pl  # noqa: E402

from g_nfl.utils.config import CUR_SEASON  # noqa: E402
from g_nfl.utils.database import MarketLinesDatabase, dump_table  # noqa: E402

SNAPSHOTS = ("open", "friday", "deadline", "close")


def store_season(
    season: int, snapshot: str, weeks: list[int] | None = None, dry_run: bool = False
) -> int:
    """Write one season's lines, a week at a time. Returns rows written."""
    schedule = nfl.load_schedules(seasons=[season]).filter(
        pl.col("spread_line").is_not_null()
    )
    if weeks is not None:
        schedule = schedule.filter(pl.col("week").is_in(weeks))
    if schedule.is_empty():
        print(f"  {season}: no games with a line")
        return 0

    db = MarketLinesDatabase()
    written = 0
    for week, block in schedule.group_by("week", maintain_order=True):
        week = week[0] if isinstance(week, tuple) else week
        lines = {
            row["game_id"]: {"spread": row["spread_line"], "total": row["total_line"]}
            for row in block.iter_rows(named=True)
        }
        if dry_run:
            print(f"  {season} wk {week:>2}: would write {len(lines)} ({snapshot})")
            written += len(lines)
            continue
        written += db.save_market_lines(season, week, lines, snapshot=snapshot)
    return written


def parse_seasons(spec: str) -> list[int]:
    """'2020-2025' or '2021' or '2021,2023'."""
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            out.extend(range(lo, hi + 1))
        else:
            out.append(int(part))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--season", type=int, default=CUR_SEASON)
    parser.add_argument("--seasons", help="range or list, e.g. 2020-2025")
    parser.add_argument("--week", type=int, help="one week; omit for the whole season")
    parser.add_argument("--weeks", help="range, e.g. 1-18")
    parser.add_argument("--snapshot", choices=SNAPSHOTS, default="close")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    seasons = parse_seasons(args.seasons) if args.seasons else [args.season]
    weeks = None
    if args.week:
        weeks = [args.week]
    elif args.weeks:
        lo, hi = (int(x) for x in args.weeks.split("-"))
        weeks = list(range(lo, hi + 1))

    if not args.dry_run:
        dump_table("market_lines")

    total = 0
    for season in seasons:
        total += store_season(season, args.snapshot, weeks, args.dry_run)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {total} market lines ({args.snapshot})")


if __name__ == "__main__":
    main()
