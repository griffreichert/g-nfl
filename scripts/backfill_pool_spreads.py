#!/usr/bin/env python3
"""Rebuild `pool_spreads` from the pool picks we already hold (#58).

    uv run python scripts/backfill_pool_spreads.py --seasons 2020-2025 --dry-run
    uv run python scripts/backfill_pool_spreads.py --seasons 2020-2025

The NY Post Friday number exists nowhere in nflverse, so it cannot be fetched.
Every one of the `pool_picks` rows carries the picked team's pool spread and a
`game_id`, so the game's line is recoverable: flip the sign when the picked team
is at home, then take the median across the room. That procedure was verified
against `standings_2025.xlsx` in notes/pick-analytics.md — 95.0% of games
identical, mean absolute difference 0.041, and no game changing its ATS winner.

Home perspective throughout, the nflverse `spread_line` convention: positive
means the home team is favoured.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).parents[1] / "src"))

from g_nfl.utils.database import (  # noqa: E402
    PicksDatabase,
    PoolSpreadsDatabase,
    dump_table,
)
from g_nfl.utils.web_app import normalize_game_id  # noqa: E402

# A game whose sides disagree by more than this is not one line with a sign
# error; it is two different lines, and averaging them would invent a third.
MAX_SPREAD_DISAGREEMENT = 1.0


def load_pool_picks(seasons: list[int]) -> list[dict]:
    """Every pool pick for these seasons, paging past PostgREST's 1000 cap.

    `.order("id")` is load-bearing: range paging over an unordered query lets
    the server return rows in a different order per page, so pages overlap and
    others are never seen. Two runs of this without it disagreed by 107 games.
    """
    client = PicksDatabase().client
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            client.table("pool_picks")
            .select("season,week,team_picked,spread,game_id")
            .in_("season", seasons)
            .order("id")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000


def to_home_spreads(rows: list[dict]) -> tuple[dict, list[str]]:
    """(season, week, game_id) -> median home spread, plus games to look at."""
    by_game: dict[tuple[int, int, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["spread"] is None:
            continue
        game_id = normalize_game_id(row["game_id"])
        parts = game_id.split("_")
        if len(parts) < 4:
            continue
        home = parts[3]
        spread = float(row["spread"])
        home_spread = -spread if row["team_picked"] == home else spread
        by_game[(row["season"], row["week"], game_id)].append(home_spread)

    spreads, suspect = {}, []
    for key, values in by_game.items():
        span = max(values) - min(values)
        if span > MAX_SPREAD_DISAGREEMENT:
            suspect.append(f"{key[2]}: {sorted(set(values))}")
        spreads[key] = statistics.median(values)
    return spreads, suspect


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seasons", default="2020-2025", help="range, e.g. 2020-2025")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lo, hi = (int(x) for x in args.seasons.split("-"))
    seasons = list(range(lo, hi + 1))

    rows = load_pool_picks(seasons)
    spreads, suspect = to_home_spreads(rows)
    print(f"{len(rows)} pool picks -> {len(spreads)} games with a pool line")

    if suspect:
        print(
            f"\n{len(suspect)} games whose sides disagree by more than "
            f"{MAX_SPREAD_DISAGREEMENT}, written as the median anyway:"
        )
        for line in suspect[:20]:
            print(f"  {line}")

    by_week: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    for (season, week, game_id), spread in spreads.items():
        by_week[(season, week)][game_id] = spread

    if not args.dry_run:
        dump_table("pool_spreads")

    db = PoolSpreadsDatabase()
    written = 0
    for (season, week), games in sorted(by_week.items()):
        if args.dry_run:
            written += len(games)
            continue
        written += db.save_pool_spreads(season, week, games)

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n{verb} {written} pool spreads across {len(by_week)} season-weeks")


if __name__ == "__main__":
    main()
