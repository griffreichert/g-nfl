import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional


class PicksDatabase:
    """SQLite database handler for storing NFL picks"""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection

        Args:
            db_path: Path to SQLite database file. If None, uses default location.
        """
        if db_path is None:
            # Default to data/web_app/picks.db
            db_dir = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "web_app"
            )
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "picks.db")

        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS picks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    game_id TEXT NOT NULL,
                    team_picked TEXT NOT NULL,
                    picker TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create index for faster queries
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_picks_season_week_picker
                ON picks(season, week, picker)
            """
            )

            conn.commit()

    def save_picks(
        self,
        season: int,
        week: int,
        picks: Dict[str, str],
        picker: str,
        replace: bool = True,
    ) -> int:
        """Save picks to database

        Args:
            season: NFL season year
            week: Week number
            picks: Dictionary mapping game_id to team_picked
            picker: Name of the person making picks
            replace: If True, replace existing picks for this picker/season/week

        Returns:
            Number of picks saved
        """
        timestamp = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # If replace is True, delete existing picks for this picker/season/week
            if replace:
                cursor.execute(
                    """
                    DELETE FROM picks
                    WHERE season = ? AND week = ? AND picker = ?
                """,
                    (season, week, picker),
                )

            # Insert each pick
            picks_data = []
            for game_id, team_picked in picks.items():
                picks_data.append(
                    (season, week, game_id, team_picked, picker, timestamp)
                )

            cursor.executemany(
                """
                INSERT INTO picks (season, week, game_id, team_picked, picker, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                picks_data,
            )

            conn.commit()
            return len(picks_data)

    def get_picks(
        self, season: int, week: int, picker: Optional[str] = None
    ) -> List[Dict]:
        """Retrieve picks from database

        Args:
            season: NFL season year
            week: Week number
            picker: Optional picker name filter

        Returns:
            List of pick dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row  # Enable dict-like access
            cursor = conn.cursor()

            if picker:
                cursor.execute(
                    """
                    SELECT * FROM picks
                    WHERE season = ? AND week = ? AND picker = ?
                    ORDER BY created_at DESC
                """,
                    (season, week, picker),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM picks
                    WHERE season = ? AND week = ?
                    ORDER BY picker, created_at DESC
                """,
                    (season, week),
                )

            return [dict(row) for row in cursor.fetchall()]

    def get_all_picks(self, limit: Optional[int] = None) -> List[Dict]:
        """Get all picks with optional limit

        Args:
            limit: Maximum number of records to return

        Returns:
            List of all pick dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM picks ORDER BY created_at DESC"
            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def delete_picks(self, season: int, week: int, picker: str) -> int:
        """Delete picks for a specific season/week/picker

        Args:
            season: NFL season year
            week: Week number
            picker: Picker name

        Returns:
            Number of records deleted
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM picks
                WHERE season = ? AND week = ? AND picker = ?
            """,
                (season, week, picker),
            )
            conn.commit()
            return cursor.rowcount

    def get_database_stats(self) -> Dict:
        """Get database statistics

        Returns:
            Dictionary with database stats
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Total picks
            cursor.execute("SELECT COUNT(*) FROM picks")
            total_picks = cursor.fetchone()[0]

            # Unique pickers
            cursor.execute("SELECT COUNT(DISTINCT picker) FROM picks")
            unique_pickers = cursor.fetchone()[0]

            # Seasons covered
            cursor.execute("SELECT MIN(season), MAX(season) FROM picks")
            season_range = cursor.fetchone()

            # Weeks covered
            cursor.execute("SELECT MIN(week), MAX(week) FROM picks")
            week_range = cursor.fetchone()

            return {
                "total_picks": total_picks,
                "unique_pickers": unique_pickers,
                "season_range": season_range,
                "week_range": week_range,
                "database_path": self.db_path,
            }
