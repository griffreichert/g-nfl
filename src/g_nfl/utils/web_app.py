import os
from typing import Optional

from PIL import Image

from .database import PicksDatabase


def get_team_logo(team_name):
    """Get team logo image from bin/logos/ directory"""
    # Navigate from src/utils back to project root, then to bin/logos
    logo_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "bin", "logos", f"{team_name}.tif"
    )
    if os.path.exists(logo_path):
        try:
            return Image.open(logo_path)
        except Exception:
            return None
    return None


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
        db = PicksDatabase()
        picks_saved = db.save_picks(season, week, picks, picker)
        return f"Successfully saved {picks_saved} picks to database"
    except Exception as e:
        print(f"Error saving picks to database: {e}")
        return None


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
        Dictionary mapping game_id to team_picked
    """
    try:
        db = PicksDatabase()
        picks_list = db.get_picks(season, week, picker)

        # Convert to dictionary format expected by streamlit session state
        picks_dict = {}
        for pick in picks_list:
            picks_dict[pick["game_id"]] = pick["team_picked"]

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
