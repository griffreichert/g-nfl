import os
from datetime import datetime
from typing import Dict, List, Optional

from supabase import Client

from .supabase_client import get_supabase


class PicksDatabase:
    """Supabase database handler for storing NFL picks"""

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = get_supabase()

    def save_picks(
        self,
        season: int,
        week: int,
        picks: Dict[str, Dict[str, any]],
        picker: str,
        replace: bool = True,
    ) -> int:
        """Save picks to Supabase

        Args:
            season: NFL season year
            week: Week number
            picks: Dictionary mapping game_id to pick data {'team_picked': str, 'spread': float}
            picker: Name of the person making picks
            replace: If True, replace existing picks for this picker/season/week

        Returns:
            Number of picks saved
        """
        # If replace is True, delete existing picks for this picker/season/week
        if replace:
            self.client.table("picks").delete().eq("season", season).eq(
                "week", week
            ).eq("picker", picker).execute()

        # Prepare picks data for insertion
        picks_data = []
        for game_id, pick_data in picks.items():
            picks_data.append(
                {
                    "season": season,
                    "week": week,
                    "game_id": game_id,
                    "team_picked": (
                        pick_data.get("team_picked", pick_data)
                        if isinstance(pick_data, dict)
                        else pick_data
                    ),
                    "spread": (
                        pick_data.get("spread") if isinstance(pick_data, dict) else None
                    ),
                    "picker": picker,
                }
            )

        # Insert picks
        result = self.client.table("picks").insert(picks_data).execute()
        return len(picks_data)

    def get_picks(
        self, season: int, week: int, picker: Optional[str] = None
    ) -> List[Dict]:
        """Retrieve picks from Supabase

        Args:
            season: NFL season year
            week: Week number
            picker: Optional picker name filter

        Returns:
            List of pick dictionaries
        """
        query = (
            self.client.table("picks").select("*").eq("season", season).eq("week", week)
        )

        if picker:
            query = query.eq("picker", picker)

        query = query.order("created_at", desc=True)
        result = query.execute()

        return result.data

    def get_all_picks(self, limit: Optional[int] = None) -> List[Dict]:
        """Get all picks with optional limit

        Args:
            limit: Maximum number of records to return

        Returns:
            List of all pick dictionaries
        """
        query = self.client.table("picks").select("*").order("created_at", desc=True)

        if limit:
            query = query.limit(limit)

        result = query.execute()
        return result.data

    def delete_picks(self, season: int, week: int, picker: str) -> int:
        """Delete picks for a specific season/week/picker

        Args:
            season: NFL season year
            week: Week number
            picker: Picker name

        Returns:
            Number of records deleted
        """
        result = (
            self.client.table("picks")
            .delete()
            .eq("season", season)
            .eq("week", week)
            .eq("picker", picker)
            .execute()
        )
        return len(result.data) if result.data else 0

    def get_database_stats(self) -> Dict:
        """Get database statistics

        Returns:
            Dictionary with database stats
        """
        # Get all picks to calculate stats
        all_picks_result = (
            self.client.table("picks").select("season, week, picker").execute()
        )
        all_picks = all_picks_result.data

        if not all_picks:
            return {
                "total_picks": 0,
                "unique_pickers": 0,
                "season_range": (None, None),
                "week_range": (None, None),
            }

        # Calculate stats
        total_picks = len(all_picks)
        unique_pickers = len(set(pick["picker"] for pick in all_picks))

        seasons = [pick["season"] for pick in all_picks if pick["season"]]
        season_range = (min(seasons), max(seasons)) if seasons else (None, None)

        weeks = [pick["week"] for pick in all_picks if pick["week"]]
        week_range = (min(weeks), max(weeks)) if weeks else (None, None)

        return {
            "total_picks": total_picks,
            "unique_pickers": unique_pickers,
            "season_range": season_range,
            "week_range": week_range,
        }
