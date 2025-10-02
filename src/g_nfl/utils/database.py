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
            picks: Dictionary mapping game_id to pick data {'team_picked': str, 'spread': float, 'pick_type': str}
            picker: Name of the person making picks
            replace: If True, replace existing picks for this picker/season/week

        Returns:
            Number of picks saved
        """
        try:
            # If replace is True, delete existing picks for this picker/season/week
            if replace:
                print(
                    f"DEBUG: Deleting existing picks for season={season}, week={week}, picker={picker}"
                )
                delete_result = (
                    self.client.table("picks")
                    .delete()
                    .eq("season", season)
                    .eq("week", week)
                    .eq("picker", picker)
                    .execute()
                )
                print(f"DEBUG: Delete result: {delete_result}")

            # Prepare picks data for insertion
            picks_data = []
            for pick_key, pick_data in picks.items():
                # Handle special pick keys vs regular game_id keys
                if pick_key.startswith(("survivor_", "underdog_", "mnf_")):
                    # Special picks: extract game_id from after the prefix
                    prefix, game_id = pick_key.split("_", 1)
                else:
                    # Regular picks: key is the game_id
                    game_id = pick_key

                pick_record = {
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
                    "pick_type": (
                        pick_data.get("pick_type", "regular")
                        if isinstance(pick_data, dict)
                        else "regular"
                    ),
                    "picker": picker,
                }
                picks_data.append(pick_record)
                print(f"DEBUG: Prepared pick record: {pick_record}")

            print(f"DEBUG: Total picks to insert: {len(picks_data)}")

            # Insert picks
            print(f"DEBUG: Attempting to insert picks into 'picks' table")
            result = self.client.table("picks").insert(picks_data).execute()
            print(f"DEBUG: Insert result: {result}")

            return len(picks_data)

        except Exception as e:
            print(f"DEBUG: Exception in PicksDatabase.save_picks: {e}")
            import traceback

            print(f"DEBUG: Traceback in save_picks: {traceback.format_exc()}")
            raise  # Re-raise the exception so it can be caught by the calling function

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


class MarketLinesDatabase:
    """Supabase database handler for storing market spread and total lines"""

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = get_supabase()

    def save_market_lines(
        self,
        season: int,
        week: int,
        lines: Dict[str, Dict[str, float]],
        replace: bool = True,
    ) -> int:
        """Save market lines to Supabase

        Args:
            season: NFL season year
            week: Week number
            lines: Dictionary mapping game_id to line data {'spread': float, 'total': float}
            replace: If True, replace existing lines for this season/week

        Returns:
            Number of lines saved
        """
        # If replace is True, delete existing lines for this season/week
        if replace:
            self.client.table("market_lines").delete().eq("season", season).eq(
                "week", week
            ).execute()

        # Prepare lines data for insertion
        lines_data = []
        for game_id, line_data in lines.items():
            lines_data.append(
                {
                    "season": season,
                    "week": week,
                    "game_id": game_id,
                    "spread": line_data.get("spread"),
                    "total": line_data.get("total"),
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

        # Insert lines
        if lines_data:
            result = self.client.table("market_lines").insert(lines_data).execute()
            return len(lines_data)
        return 0

    def get_market_lines(self, season: int, week: int) -> List[Dict]:
        """Retrieve market lines from Supabase

        Args:
            season: NFL season year
            week: Week number

        Returns:
            List of market line dictionaries
        """
        query = (
            self.client.table("market_lines")
            .select("*")
            .eq("season", season)
            .eq("week", week)
        )

        result = query.execute()
        return result.data

    def get_available_weeks(self, season: int) -> List[int]:
        """Get all weeks that have market lines data for a given season

        Args:
            season: NFL season year

        Returns:
            List of week numbers that have market lines data, sorted ascending
        """
        query = self.client.table("market_lines").select("week").eq("season", season)

        result = query.execute()

        if not result.data:
            return []

        # Extract unique weeks and sort them
        weeks = list(set(row["week"] for row in result.data if row["week"]))
        return sorted(weeks)

    def get_max_week_for_season(self, season: int) -> Optional[int]:
        """Get the maximum week number that has market lines data for a given season

        Args:
            season: NFL season year

        Returns:
            Maximum week number with data, or None if no data exists
        """
        available_weeks = self.get_available_weeks(season)
        return max(available_weeks) if available_weeks else None


class PoolSpreadsDatabase:
    """Supabase database handler for storing pool/competition spread lines"""

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = get_supabase()

    def save_pool_spreads(
        self,
        season: int,
        week: int,
        spreads: Dict[str, float],
        replace: bool = True,
    ) -> int:
        """Save pool spreads to Supabase

        Args:
            season: NFL season year
            week: Week number
            spreads: Dictionary mapping game_id to spread value
            replace: If True, replace existing spreads for this season/week

        Returns:
            Number of spreads saved
        """
        # If replace is True, delete existing spreads for this season/week
        if replace:
            self.client.table("pool_spreads").delete().eq("season", season).eq(
                "week", week
            ).execute()

        # Prepare spreads data for insertion
        spreads_data = []
        for game_id, spread in spreads.items():
            spreads_data.append(
                {
                    "season": season,
                    "week": week,
                    "game_id": game_id,
                    "spread": spread,
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

        # Insert spreads
        if spreads_data:
            result = self.client.table("pool_spreads").insert(spreads_data).execute()
            return len(spreads_data)
        return 0

    def get_pool_spreads(self, season: int, week: int) -> List[Dict]:
        """Retrieve pool spreads from Supabase

        Args:
            season: NFL season year
            week: Week number

        Returns:
            List of pool spread dictionaries
        """
        query = (
            self.client.table("pool_spreads")
            .select("*")
            .eq("season", season)
            .eq("week", week)
        )

        result = query.execute()
        return result.data

    def update_pool_spread(
        self, season: int, week: int, game_id: str, spread: float
    ) -> bool:
        """Update a single pool spread

        Args:
            season: NFL season year
            week: Week number
            game_id: Game identifier
            spread: New spread value

        Returns:
            True if successful
        """
        try:
            # Try to update existing record
            update_result = (
                self.client.table("pool_spreads")
                .update({"spread": spread})
                .eq("season", season)
                .eq("week", week)
                .eq("game_id", game_id)
                .execute()
            )

            # If no record was updated, insert a new one
            if not update_result.data:
                insert_result = (
                    self.client.table("pool_spreads")
                    .insert(
                        {
                            "season": season,
                            "week": week,
                            "game_id": game_id,
                            "spread": spread,
                            "created_at": datetime.utcnow().isoformat(),
                        }
                    )
                    .execute()
                )
                return len(insert_result.data) > 0

            return len(update_result.data) > 0
        except Exception as e:
            print(f"Error updating pool spread: {e}")
            return False
