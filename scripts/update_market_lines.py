#!/usr/bin/env python3
"""
Script to fetch market spreads and totals from nfl_data and store in database.
This should be run locally where nfl_data_py is available.
"""

import os
import sys
from typing import Any, Dict

# Add the project root to the path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.g_nfl.modelling.utils import get_week_spreads
from src.g_nfl.utils.config import CUR_SEASON
from src.g_nfl.utils.database import MarketLinesDatabase


def fetch_and_store_market_lines(season: int, week: int) -> bool:
    """Fetch market lines and store in database

    Args:
        season: NFL season year
        week: Week number

    Returns:
        True if successful
    """
    try:
        print(f"Fetching market lines for {season} Week {week}...")

        # Get spreads and totals from nfl_data
        games_df = get_week_spreads(week, season)

        if games_df.empty:
            print(f"No games found for {season} Week {week}")
            return False

        # Convert to dictionary format for database storage
        lines = {}
        for game_id, game in games_df.iterrows():
            lines[game_id] = {
                "spread": game.get("spread_line"),
                "total": game.get("total_line"),
            }

        print(f"Found {len(lines)} games with market lines")

        # Store in database
        db = MarketLinesDatabase()
        saved_count = db.save_market_lines(season, week, lines)

        print(f"Successfully saved {saved_count} market lines to database")

        # Print summary
        spreads_count = sum(
            1 for line in lines.values() if line.get("spread") is not None
        )
        totals_count = sum(
            1 for line in lines.values() if line.get("total") is not None
        )

        print(f"Summary:")
        print(f"  - Games with spreads: {spreads_count}")
        print(f"  - Games with totals: {totals_count}")

        return True

    except Exception as e:
        print(f"Error fetching/storing market lines: {e}")
        return False


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Update market lines in database")
    parser.add_argument(
        "--season", type=int, default=CUR_SEASON, help="NFL season year"
    )
    parser.add_argument("--week", type=int, required=True, help="Week number")
    parser.add_argument(
        "--weeks", type=str, help="Week range (e.g., '1-18' or '1,3,5')"
    )

    args = parser.parse_args()

    if args.weeks:
        # Handle multiple weeks
        if "-" in args.weeks:
            # Range format: 1-18
            start, end = map(int, args.weeks.split("-"))
            weeks = list(range(start, end + 1))
        else:
            # Comma-separated format: 1,3,5
            weeks = [int(w.strip()) for w in args.weeks.split(",")]

        success_count = 0
        for week in weeks:
            if fetch_and_store_market_lines(args.season, week):
                success_count += 1
            print()  # Add spacing between weeks

        print(f"Successfully updated {success_count}/{len(weeks)} weeks")

    else:
        # Single week
        success = fetch_and_store_market_lines(args.season, args.week)
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()
