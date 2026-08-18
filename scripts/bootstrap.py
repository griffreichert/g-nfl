#!/usr/bin/env python3
"""Take a fresh clone to a working repo (issue #96).

    make bootstrap

Warms the caches by calling the loaders the pipeline itself calls, then pulls
the handful of files that cannot be regenerated. Slow once, correct always: a
synced cache can go stale silently, a regenerated one cannot.

``uv sync`` is the Make target's job, not this script's — by the time Python is
running, the environment already exists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parents[1] / "src"))

from g_nfl.ml.data import DEFAULT_CACHE_DIR, load_pbp, load_schedule  # noqa: E402
from g_nfl.sleeper.client import KNOWN_LEAGUES, SleeperClient  # noqa: E402
from g_nfl.utils.storage import pull_data  # noqa: E402

# What `make train` and the backtest run on. Play-by-play is ~10M a season, so
# this is the slow step and the one worth being explicit about.
DEFAULT_SEASONS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]


def warm_nflverse(seasons: list[int], refresh: bool) -> None:
    print(f"→ nflverse cache: {len(seasons)} seasons into {DEFAULT_CACHE_DIR}")
    for season in seasons:
        load_schedule([season], refresh=refresh)
        load_pbp([season], refresh=refresh)
        print(f"  {season} ok")


def warm_sleeper() -> None:
    print("→ Sleeper cache: players blob + known leagues")
    client = SleeperClient()
    client.players()  # ~5MB, the expensive one
    for name, league_id in KNOWN_LEAGUES.items():
        client.league(league_id)
        print(f"  {name} ok")


def fetch_source_documents() -> None:
    print("→ Source documents from Supabase Storage")
    try:
        result = pull_data()
    except Exception as e:  # noqa: BLE001 — a fresh clone may have no keys yet
        print(f"  skipped: {e}")
        print("  (fix the bucket or the .env keys, then run `make pull-data`)")
        return
    print(f"  {result.summary()}")
    for key in result.refused:
        print(f"  refused {key}: local file is newer than the remote copy")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a fresh clone.")
    parser.add_argument("--seasons", type=int, nargs="+", default=DEFAULT_SEASONS)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refetch cached seasons. Do this for the current season in-year, "
        "since its play-by-play grows every week.",
    )
    parser.add_argument(
        "--skip-nflverse",
        action="store_true",
        help="Skip the slow step when you only want the caches you are missing.",
    )
    args = parser.parse_args()

    if args.skip_nflverse:
        print("→ nflverse cache: skipped")
    else:
        warm_nflverse(args.seasons, args.refresh)
    warm_sleeper()
    fetch_source_documents()

    print("\nDone. Try:")
    print("  uv run python -m g_nfl.fantasy.draft_board --preset ppr_12")
    print("  make run")


if __name__ == "__main__":
    main()
