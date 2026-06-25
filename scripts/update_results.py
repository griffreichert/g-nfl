#!/usr/bin/env python3
"""Fetch final game results from nflverse and upsert into Supabase.

Run locally (nflreadpy is an analysis-group dep, not available on the
deployed API). Safe to re-run: rows upsert on game_id, and games
without a final score are skipped until they finish.

    make update-results                      # current season
    uv run python scripts/update_results.py --season 2024
"""

import argparse
import sys

import nflreadpy as nfl

from g_nfl.utils.config import CUR_SEASON
from g_nfl.utils.database import GameResultsDatabase
from g_nfl.utils.web_app import normalize_game_id


def fetch_and_store_results(season: int) -> int:
    """Upsert finished games for a season; returns rows saved."""
    print(f"Fetching {season} schedule from nflverse...")
    schedule = nfl.load_schedules(seasons=[season])

    finished = schedule.filter(schedule["result"].is_not_null())
    rows = [
        {
            "game_id": normalize_game_id(g["game_id"]),
            "season": g["season"],
            "week": g["week"],
            "away_team": g["away_team"],
            "home_team": g["home_team"],
            "away_score": g["away_score"],
            "home_score": g["home_score"],
            "result": g["result"],
        }
        for g in finished.iter_rows(named=True)
    ]
    print(f"{len(rows)} finished games ({schedule.height - len(rows)} not played yet)")

    saved = GameResultsDatabase().save_results(rows)
    print(f"Upserted {saved} results for {season}")
    return saved


def main():
    parser = argparse.ArgumentParser(description="Update game results in database")
    parser.add_argument(
        "--season",
        type=int,
        nargs="+",
        default=[CUR_SEASON],
        help="NFL season year(s)",
    )
    args = parser.parse_args()

    for season in args.season:
        if fetch_and_store_results(season) == 0:
            print(f"WARNING: no results saved for {season}")
            sys.exit(1)


if __name__ == "__main__":
    main()
