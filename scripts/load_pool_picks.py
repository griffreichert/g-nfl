"""Load a Cville pool standings workbook into the Supabase pool_picks table (#20).

One-time setup: run scripts/pool_picks_schema.sql in the Supabase SQL editor.

Usage:
    uv run python scripts/load_pool_picks.py data/pool/standings_2025.xlsx --season 2025
    uv run python scripts/load_pool_picks.py <xlsx> --season 2025 --dry-run
"""

import argparse
from collections import Counter
from pathlib import Path

from g_nfl.pool.parser import parse_workbook
from g_nfl.utils.database import PoolPicksDatabase


def main() -> None:
    ap = argparse.ArgumentParser(description="Load pool picks workbook into Supabase")
    ap.add_argument("xlsx", type=Path, help="standings workbook (.xlsx)")
    ap.add_argument("--season", type=int, required=True, help="NFL season, e.g. 2025")
    ap.add_argument(
        "--dry-run", action="store_true", help="parse and summarize, don't write"
    )
    args = ap.parse_args()

    picks = parse_workbook(args.xlsx, args.season)
    weeks = Counter(p["week"] for p in picks)
    pickers = sorted({p["picker"] for p in picks})
    print(
        f"parsed {len(picks)} picks: weeks {min(weeks)}-{max(weeks)}, "
        f"{len(pickers)} pickers"
    )

    if args.dry_run:
        print("dry run — nothing written")
        return

    saved = PoolPicksDatabase().save_picks(picks)
    print(f"upserted {saved} picks into pool_picks")


if __name__ == "__main__":
    main()
