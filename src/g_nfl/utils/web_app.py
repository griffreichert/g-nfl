import os
from typing import Optional

from PIL import Image

from .database import MarketLinesDatabase, PicksDatabase, PoolSpreadsDatabase


def get_team_logo(team_name):
    """Get team logo URL from ESPN CDN"""
    if not team_name:
        return None

    # Convert team name to lowercase for ESPN URL
    team_lower = team_name.lower()
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{team_lower}.png"


def save_picks_data(season: int, week: int, picks: dict, picker: str) -> Optional[str]:
    """Save picks data to Supabase database

    Args:
        season: NFL season year
        week: Week number
        picks: Dictionary mapping game_id to team_picked
        picker: Name of the person making picks

    Returns:
        Success message or None if failed
    """
    if not picks:
        return None

    try:
        print(
            f"DEBUG: Attempting to save picks - season: {season}, week: {week}, picker: {picker}"
        )
        print(f"DEBUG: Number of picks to save: {len(picks)}")
        print(f"DEBUG: Picks data: {picks}")

        db = PicksDatabase()
        print(f"DEBUG: PicksDatabase created successfully")

        picks_saved = db.save_picks(season, week, picks, picker)
        print(f"DEBUG: save_picks returned: {picks_saved}")

        return f"Successfully saved {picks_saved} picks to database"
    except Exception as e:
        error_msg = f"Error saving picks to database: {e}"
        error_type = type(e).__name__
        print(f"DEBUG: {error_msg}")
        print(f"DEBUG: Error type: {error_type}")
        import traceback

        print(f"DEBUG: Traceback: {traceback.format_exc()}")

        # Return error message so it can be displayed in Streamlit
        return f"ERROR: {error_type}: {str(e)}"


def get_picks_data(season: int, week: int, picker: Optional[str] = None):
    """Retrieve picks data from Supabase database

    Args:
        season: NFL season year
        week: Week number
        picker: Optional picker name filter

    Returns:
        List of pick dictionaries
    """
    try:
        db = PicksDatabase()
        return db.get_picks(season, week, picker)
    except Exception as e:
        print(f"Error retrieving picks from database: {e}")
        return []


def load_existing_picks(season: int, week: int, picker: str) -> dict:
    """Load existing picks for a specific picker/season/week as a dictionary

    Args:
        season: NFL season year
        week: Week number
        picker: Picker name

    Returns:
        Dictionary mapping game_id to pick data {'team_picked': str, 'pick_type': str, 'spread': float}
    """
    try:
        db = PicksDatabase()
        picks_list = db.get_picks(season, week, picker)

        # Convert to dictionary format expected by streamlit session state
        picks_dict = {}
        for pick in picks_list:
            picks_dict[pick["game_id"]] = {
                "team_picked": pick["team_picked"],
                "pick_type": pick.get("pick_type", "regular"),
                "spread": pick.get("spread"),
            }

        return picks_dict
    except Exception as e:
        print(f"Error loading existing picks: {e}")
        return {}


def get_database_stats():
    """Get database statistics

    Returns:
        Dictionary with database stats
    """
    try:
        db = PicksDatabase()
        return db.get_database_stats()
    except Exception as e:
        print(f"Error getting database stats: {e}")
        return {}


def get_market_lines(season: int, week: int) -> dict:
    """Get market lines for a specific season/week

    Args:
        season: NFL season year
        week: Week number

    Returns:
        Dictionary mapping game_id to market line data
    """
    try:
        db = MarketLinesDatabase()
        lines_list = db.get_market_lines(season, week)

        # Convert to dictionary format
        lines_dict = {}
        for line in lines_list:
            lines_dict[line["game_id"]] = {
                "spread": line.get("spread"),
                "total": line.get("total"),
            }

        return lines_dict
    except Exception as e:
        print(f"Error getting market lines: {e}")
        return {}


def get_pool_spreads(season: int, week: int) -> dict:
    """Get pool spreads for a specific season/week

    Args:
        season: NFL season year
        week: Week number

    Returns:
        Dictionary mapping game_id to pool spread
    """
    try:
        db = PoolSpreadsDatabase()
        spreads_list = db.get_pool_spreads(season, week)

        # Convert to dictionary format
        spreads_dict = {}
        for spread in spreads_list:
            spreads_dict[spread["game_id"]] = spread.get("spread")

        return spreads_dict
    except Exception as e:
        print(f"Error getting pool spreads: {e}")
        return {}


def get_all_lines_data(season: int, week: int) -> dict:
    """Get combined market lines and pool spreads for a season/week

    Args:
        season: NFL season year
        week: Week number

    Returns:
        Dictionary with combined line data
    """
    market_lines = get_market_lines(season, week)
    pool_spreads = get_pool_spreads(season, week)

    # Combine data
    combined = {}
    all_game_ids = set(market_lines.keys()) | set(pool_spreads.keys())

    for game_id in all_game_ids:
        combined[game_id] = {
            "market_spread": market_lines.get(game_id, {}).get("spread"),
            "market_total": market_lines.get(game_id, {}).get("total"),
            "pool_spread": pool_spreads.get(game_id),
        }

    return combined
