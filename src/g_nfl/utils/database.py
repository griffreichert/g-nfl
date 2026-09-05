from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase.client import Client

from .paths import DATA_PATH
from .supabase_client import get_supabase

BACKUP_DIR = DATA_PATH / "backups"

#: PostgREST returns at most this many rows and says nothing about the rest.
PAGE = 1000


def fetch_all(build, chunk: int = PAGE) -> list[dict]:
    """Every row a query matches, paging past PostgREST's 1000-row cap.

    `build` is called once per page and must return a fresh query builder, since
    a builder cannot be executed twice. Any getter whose table can hold more than
    `PAGE` rows for one filter has to go through here: `pool_picks` holds 2679
    rows for 2025 alone, and a plain `.execute()` returned the first 1000 of them
    with no error and no warning.

    `.order("id")` is load-bearing. Range paging over an unordered query lets the
    server return a different order per page, so pages overlap and other rows are
    never read. Two runs of the same backfill disagreed by 107 games.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        page = build().order("id").range(offset, offset + chunk - 1).execute().data
        rows.extend(page)
        if len(page) < chunk:
            return rows
        offset += chunk


def dump_table(table: str, chunk: int = 1000) -> Path:
    """Write every row of `table` to data/backups/ and return the path.

    Call this before any bulk write. The project is on Supabase's free plan,
    which has no backups, so a bad write is permanent. On 2026-08-31 a backfill
    deleted 319 rows of 2025 pick-time market snapshots that no longer exist
    anywhere.

    `.order("id")` matters: range paging over an unordered query lets the server
    return a different order per page, so pages overlap and other rows are never
    read. Two runs without it disagreed by 107 games.
    """
    client = get_supabase()
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            client.table(table)
            .select("*")
            .order("id")
            .range(offset, offset + chunk - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < chunk:
            break
        offset += chunk

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = BACKUP_DIR / f"{table}_{stamp}.json"
    path.write_text(json.dumps(rows, indent=2, default=str))
    print(f"  backed up {len(rows)} rows of {table} -> {path}")
    return path


class PicksDatabase:
    """Supabase database handler for storing NFL picks"""

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = get_supabase()

    def save_picks(
        self,
        season: int,
        week: int,
        picks: dict[str, dict[str, any]],
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
        submitted_at = datetime.now(UTC).isoformat()
        try:
            # Replace is insert-then-delete, never delete-then-insert: if the
            # insert fails (bad column, network) a prior delete would have
            # already wiped the picker's week with nothing to put back. The
            # old rows are captured by id here and removed only after the new
            # ones land. Worst case is leftover duplicates, which is fixable.
            stale_ids: list[int] = []
            if replace:
                existing = (
                    self.client.table("picks")
                    .select("id")
                    .eq("season", season)
                    .eq("week", week)
                    .eq("picker", picker)
                    .execute()
                )
                stale_ids = [row["id"] for row in existing.data]

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
                    "note": (
                        pick_data.get("note") if isinstance(pick_data, dict) else None
                    ),
                    "submitted_at": submitted_at,
                }
                picks_data.append(pick_record)
                print(f"DEBUG: Prepared pick record: {pick_record}")

            print(f"DEBUG: Total picks to insert: {len(picks_data)}")

            # Insert picks
            print("DEBUG: Attempting to insert picks into 'picks' table")
            result = self.client.table("picks").insert(picks_data).execute()
            print(f"DEBUG: Insert result: {result}")

            if stale_ids:
                self.client.table("picks").delete().in_("id", stale_ids).execute()

            return len(picks_data)

        except Exception as e:
            print(f"DEBUG: Exception in PicksDatabase.save_picks: {e}")
            import traceback

            print(f"DEBUG: Traceback in save_picks: {traceback.format_exc()}")
            raise  # Re-raise the exception so it can be caught by the calling function

    def get_picks(
        self, season: int, week: int, picker: str | None = None
    ) -> list[dict]:
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

    def get_season_picks(self, season: int) -> list[dict]:
        """All picks for a season, every picker and week."""
        return fetch_all(
            lambda: self.client.table("picks").select("*").eq("season", season)
        )

    def get_all_picks(self, limit: int | None = None) -> list[dict]:
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

    def get_database_stats(self) -> dict:
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


class PoolPicksDatabase:
    """Supabase database handler for every pool member's weekly picks (#20)"""

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = get_supabase()

    def save_picks(self, picks: list[dict]) -> int:
        """Upsert parsed pool picks (rows from g_nfl.pool.parse_workbook).

        Conflicts on (season, week, picker, slot) update in place, so
        re-loading a workbook refreshes results without duplicating rows.

        Returns:
            Number of picks saved
        """
        if not picks:
            return 0
        rows = [
            {
                "season": p["season"],
                "week": p["week"],
                "week_label": p["week_label"],
                "picker": p["picker"],
                "slot": p["slot"],
                "pick_type": p["pick_type"],
                "team_picked": p["team_picked"],
                "spread": p["spread"],
                "game_id": p["game_id"],
                "result": p["result"],
            }
            for p in picks
        ]
        # batch to stay under request size limits
        for i in range(0, len(rows), 500):
            self.client.table("pool_picks").upsert(
                rows[i : i + 500], on_conflict="season,week,picker,slot"
            ).execute()
        return len(rows)

    def get_picks(self, season: int, week: int | None = None) -> list[dict]:
        """Retrieve pool picks for a season (optionally one week)."""

        def build():
            query = self.client.table("pool_picks").select("*").eq("season", season)
            return query.eq("week", week) if week is not None else query

        return fetch_all(build)


class GameResultsDatabase:
    """Supabase database handler for final game results.

    Populated locally by scripts/update_results.py (nflverse data isn't
    available to the deployed API); read by the standings endpoint.
    """

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = get_supabase()

    def save_results(self, results: list[dict]) -> int:
        """Upsert result rows keyed by game_id.

        Each row: game_id, season, week, away_team, home_team,
        away_score, home_score, result (home margin).
        """
        if not results:
            return 0
        rows = [{**r, "updated_at": datetime.utcnow().isoformat()} for r in results]
        self.client.table("game_results").upsert(rows, on_conflict="game_id").execute()
        return len(rows)

    def graded_per_week(self, season: int) -> dict[int, int]:
        """How many games each week of `season` has a result for."""
        rows = fetch_all(
            lambda: (
                self.client.table("game_results")
                .select("week,result")
                .eq("season", season)
            )
        )
        counts: dict[int, int] = {}
        for row in rows:
            if row["result"] is not None:
                counts[row["week"]] = counts.get(row["week"], 0) + 1
        return counts

    def get_results(self, season: int) -> list[dict]:
        """All result rows for a season."""
        result = (
            self.client.table("game_results").select("*").eq("season", season).execute()
        )
        return result.data


class GameContextDatabase:
    """Per-game context for the detail page: weather, rest, QBs, injuries.

    Populated locally by scripts/update_game_context.py — nflverse data
    isn't available to the deployed API, same constraint as game_results.
    """

    def __init__(self):
        self.client: Client = get_supabase()

    def save_context(self, rows: list[dict]) -> int:
        """Upsert context rows keyed by game_id."""
        if not rows:
            return 0
        payload = [{**r, "updated_at": datetime.utcnow().isoformat()} for r in rows]
        self.client.table("game_context").upsert(
            payload, on_conflict="game_id"
        ).execute()
        return len(payload)

    def get_context(self, game_id: str) -> dict | None:
        """One game's context, or None if it hasn't been pushed yet."""
        result = (
            self.client.table("game_context")
            .select("*")
            .eq("game_id", game_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None


class TeamWeekStatsDatabase:
    """Weekly team EPA / success / explosive rates, offense and defense."""

    def __init__(self):
        self.client: Client = get_supabase()

    def save_stats(self, rows: list[dict]) -> int:
        """Upsert stat rows keyed by (season, week, team)."""
        if not rows:
            return 0
        payload = [{**r, "updated_at": datetime.utcnow().isoformat()} for r in rows]
        self.client.table("team_week_stats").upsert(
            payload, on_conflict="season,week,team"
        ).execute()
        return len(payload)

    def get_team_stats(self, season: int, teams: list[str]) -> list[dict]:
        """Every week so far for the given teams — the detail page shows the
        season to date, not just the week in question."""
        result = (
            self.client.table("team_week_stats")
            .select("*")
            .eq("season", season)
            .in_("team", teams)
            .execute()
        )
        return result.data


class MarketLinesDatabase:
    """Supabase database handler for storing market spread and total lines"""

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = get_supabase()

    def save_market_lines(
        self,
        season: int,
        week: int,
        lines: dict[str, dict[str, float]],
        snapshot: str = "close",
    ) -> int:
        """Save market lines to Supabase.

        Upserts on (season, week, game_id, snapshot). Nothing is deleted.

        A delete-then-insert stood here until 2026-08-31, when a backfill of
        closing lines wiped 319 rows of 2025 pick-time snapshots that nobody
        could see: RLS was enabled on the table with no policy, so every SELECT
        returned empty without erroring, and the table read as empty when it was
        not. Those snapshots are unrecoverable, the project has no backups, and
        nflverse only publishes the close.

        Args:
            season: NFL season year
            week: Week number
            lines: Dictionary mapping game_id to line data {'spread': float, 'total': float}
            snapshot: When the line was read. 'open', 'friday', 'deadline' or
                'close'. A backfill from nflverse is always 'close'. The
                in-season crons write 'friday' and 'deadline'.

        Returns:
            Number of lines saved
        """
        from g_nfl.utils.web_app import normalize_game_id

        lines_data = [
            {
                "season": season,
                "week": week,
                "game_id": normalize_game_id(game_id),
                "spread": line_data.get("spread"),
                "total": line_data.get("total"),
                "snapshot": snapshot,
                "created_at": datetime.utcnow().isoformat(),
            }
            for game_id, line_data in lines.items()
        ]

        if lines_data:
            self.client.table("market_lines").upsert(
                lines_data, on_conflict="season,week,game_id,snapshot"
            ).execute()
            return len(lines_data)
        return 0

    #: Which snapshot to believe when a game has several, sharpest first.
    SNAPSHOT_PRIORITY = ("close", "deadline", "friday", "open")

    def get_market_lines(
        self, season: int, week: int | None = None, snapshot: str | None = None
    ) -> list[dict]:
        """Retrieve market lines from Supabase

        Args:
            season: NFL season year
            week: Week number, or None for the whole season
            snapshot: Return only this snapshot. Omit to collapse to one row per
                game, taking the sharpest available per `SNAPSHOT_PRIORITY` — the
                close once a game has been played, the deadline pull while the
                week is live. Grading needs one line per game, so callers that do
                not care must not see the same game several times.

        Returns:
            List of market line dictionaries
        """

        def build():
            query = self.client.table("market_lines").select("*").eq("season", season)
            if week is not None:
                query = query.eq("week", week)
            if snapshot is not None:
                query = query.eq("snapshot", snapshot)
            return query

        if snapshot is not None:
            return fetch_all(build)

        rank = {s: i for i, s in enumerate(self.SNAPSHOT_PRIORITY)}
        best: dict[str, dict] = {}
        for row in fetch_all(build):
            gid = row["game_id"]
            held = best.get(gid)
            if held is None or rank.get(row.get("snapshot"), 99) < rank.get(
                held.get("snapshot"), 99
            ):
                best[gid] = row
        return list(best.values())

    def get_available_weeks(self, season: int) -> list[int]:
        """Get all weeks that have market lines data for a given season

        Args:
            season: NFL season year

        Returns:
            List of week numbers that have market lines data, sorted ascending
        """
        rows = fetch_all(
            lambda: (
                self.client.table("market_lines").select("week").eq("season", season)
            )
        )
        return sorted({row["week"] for row in rows if row["week"]})

    def latest_season(self) -> int | None:
        """The most recent season with market lines, or None if the table is empty."""
        rows = (
            self.client.table("market_lines")
            .select("season")
            .order("season", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return rows[0]["season"] if rows else None

    def seasons(self) -> list[int]:
        """Every season with market lines, ascending."""
        rows = fetch_all(lambda: self.client.table("market_lines").select("season"))
        return sorted({row["season"] for row in rows if row["season"]})

    def games_per_week(self, season: int) -> dict[int, int]:
        """How many distinct games each week of `season` has a line for."""
        rows = fetch_all(
            lambda: (
                self.client.table("market_lines")
                .select("week,game_id")
                .eq("season", season)
            )
        )
        by_week: dict[int, set[str]] = {}
        for row in rows:
            by_week.setdefault(row["week"], set()).add(row["game_id"])
        return {week: len(games) for week, games in by_week.items()}

    def get_max_week_for_season(self, season: int) -> int | None:
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
        spreads: dict[str, float],
    ) -> int:
        """Save pool spreads to Supabase.

        Upserts on (season, week, game_id). Nothing is deleted, for the reason
        given on `MarketLinesDatabase.save_market_lines`.

        Args:
            season: NFL season year
            week: Week number
            spreads: Dictionary mapping game_id to spread value

        Returns:
            Number of spreads saved
        """
        from g_nfl.utils.web_app import normalize_game_id

        spreads_data = [
            {
                "season": season,
                "week": week,
                # zero-padded week, or the join to picks silently misses
                "game_id": normalize_game_id(game_id),
                "spread": spread,
                "created_at": datetime.utcnow().isoformat(),
            }
            for game_id, spread in spreads.items()
        ]

        if spreads_data:
            self.client.table("pool_spreads").upsert(
                spreads_data, on_conflict="season,week,game_id"
            ).execute()
            return len(spreads_data)
        return 0

    def get_pool_spreads(self, season: int, week: int | None = None) -> list[dict]:
        """Retrieve pool spreads from Supabase

        Args:
            season: NFL season year
            week: Week number, or None for the whole season

        Returns:
            List of pool spread dictionaries
        """
        query = self.client.table("pool_spreads").select("*").eq("season", season)
        if week is not None:
            query = query.eq("week", week)

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


class FantasyProjectionsDatabase:
    """Dated snapshots of season-total fantasy stat lines (issue #81).

    Written by ``g_nfl.fantasy.ingest``, which Griffin runs by hand. Nothing in
    the request path scrapes, so a broken source degrades to a stale snapshot
    instead of an error, and the caller can see how stale from ``snapshot_date``.
    """

    #: Stat columns, matching the ESPN source contract in ``fantasy.sources.espn``.
    STAT_COLUMNS = (
        "pass_yd",
        "pass_td",
        "ints",
        "rush_yd",
        "rush_td",
        "rec",
        "rec_yd",
        "rec_td",
        "fum",
    )

    def __init__(self):
        self.client: Client = get_supabase()

    def save_snapshot(self, rows: list[dict]) -> int:
        """Upsert one snapshot's rows, keyed by (snapshot_date, source, player_id).

        Upsert rather than insert so re-running an ingest the same day is a
        no-op instead of a duplicate snapshot.
        """
        if not rows:
            return 0
        payload = [{**r, "updated_at": datetime.utcnow().isoformat()} for r in rows]
        self.client.table("fantasy_projections").upsert(
            payload, on_conflict="snapshot_date,source,player_id"
        ).execute()
        return len(payload)

    def latest_snapshot_date(self, source: str, season: int) -> str | None:
        """Newest ``snapshot_date`` for a source, or None if never ingested."""
        result = (
            self.client.table("fantasy_projections")
            .select("snapshot_date")
            .eq("source", source)
            .eq("season", season)
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0]["snapshot_date"] if result.data else None

    def get_snapshot(
        self, source: str, season: int, snapshot_date: str | None = None
    ) -> list[dict]:
        """One snapshot's rows; the newest one when ``snapshot_date`` is None.

        Returns an empty list when the source has never been ingested, which
        the caller should treat as "fall back to a live fetch", not as an error.
        """
        snapshot_date = snapshot_date or self.latest_snapshot_date(source, season)
        if snapshot_date is None:
            return []
        result = (
            self.client.table("fantasy_projections")
            .select("*")
            .eq("source", source)
            .eq("season", season)
            .eq("snapshot_date", snapshot_date)
            .execute()
        )
        return result.data


class SurvivorBeliefsDatabase:
    """What a picker thinks about a team, beyond what the ratings say (#72).

    ``confidence`` is how well that team's rating holds up across a season —
    5 is "they are this all year", 1 is an injury or a hot seat away from
    being somebody else, 3 is no opinion. Stored per picker rather than left
    in the browser because comparing them is the point: two entries plan
    different seasons off the same board because they trust different teams,
    and that disagreement is worth reading back at the end of a year.

    The table may not exist yet (``scripts/pending_migrations.sql``). Reads
    return empty rather than raising, so the planner works without it.
    """

    def __init__(self):
        self.client: Client = get_supabase()

    def get_beliefs(self, season: int, picker: str | None = None) -> list[dict]:
        """One picker's beliefs, or the whole room's when picker is None."""

        def build():
            query = (
                self.client.table("survivor_beliefs").select("*").eq("season", season)
            )
            return query.eq("picker", picker) if picker else query

        try:
            return fetch_all(build)
        except Exception:
            return []  # table not created yet: no beliefs is a valid answer

    def save_beliefs(self, season: int, picker: str, beliefs: list[dict]) -> int:
        """Upsert one picker's beliefs, keyed by (season, picker, team).

        Upsert rather than replace: a delete-then-insert would lose the whole
        set on a partial failure, and this project has no backups (CLAUDE.md).
        A team put back to 3 is written as 3, never removed.
        """
        if not beliefs:
            return 0
        rows = [
            {
                "season": season,
                "picker": picker,
                "team": b["team"],
                "confidence": float(b.get("confidence", 3)),
                "updated_at": datetime.utcnow().isoformat(),
            }
            for b in beliefs
        ]
        self.client.table("survivor_beliefs").upsert(
            rows, on_conflict="season,picker,team"
        ).execute()
        return len(rows)


class ModelRunsDatabase:
    """gModel's weekly board and the run that produced it (#13).

    A run is identified by a uuid and deduplicated by ``fingerprint``, a hash
    over the feature values that fed the fit and the lines read at run time.
    Re-running against unchanged inputs returns the existing run_id and
    upserts the same numbers over themselves; a run after new injury data or
    a corrected line gets its own row, and both stay readable.

    Schema in ``scripts/model_predictions_schema.sql``.
    """

    def __init__(self):
        self.client: Client = get_supabase()

    def find_run(
        self, season: int, week: int, model: str, fingerprint: str
    ) -> str | None:
        """The run_id already holding these inputs, if there is one."""
        rows = (
            self.client.table("model_runs")
            .select("run_id")
            .eq("season", season)
            .eq("week", week)
            .eq("model", model)
            .eq("fingerprint", fingerprint)
            .execute()
        ).data
        return rows[0]["run_id"] if rows else None

    def save_run(self, run: dict) -> str:
        """Upsert a run, returning its run_id.

        `run` carries season, week, model, fingerprint and the config needed
        to rebuild the prediction. An existing fingerprint keeps its uuid.
        """
        existing = self.find_run(
            run["season"], run["week"], run["model"], run["fingerprint"]
        )
        row = {**run, "run_id": existing or str(uuid.uuid4())}
        self.client.table("model_runs").upsert(
            row, on_conflict="season,week,model,fingerprint"
        ).execute()
        return row["run_id"]

    def save_predictions(self, run_id: str, rows: list[dict]) -> int:
        """Upsert the board for a run, keyed (run_id, game_id)."""
        if not rows:
            return 0
        payload = [{**r, "run_id": run_id} for r in rows]
        self.client.table("model_predictions").upsert(
            payload, on_conflict="run_id,game_id"
        ).execute()
        return len(payload)

    def mark_submitted(self, run_id: str, season: int, week: int, model: str) -> None:
        """Record that this run is the one that wrote the picks table.

        The week's other runs are cleared first. `picks` holds one entry per
        picker per week and carries no run_id, so this flag is the only link
        from a submitted entry back to the numbers behind it, and two runs
        claiming it makes that link ambiguous.
        """
        self.client.table("model_runs").update({"submitted": False}).eq(
            "season", season
        ).eq("week", week).eq("model", model).execute()
        self.client.table("model_runs").update({"submitted": True}).eq(
            "run_id", run_id
        ).execute()

    def latest_run(self, season: int, week: int, model: str) -> dict | None:
        """The most recent run for a week, config and all."""
        rows = (
            self.client.table("model_runs")
            .select("*")
            .eq("season", season)
            .eq("week", week)
            .eq("model", model)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data
        return rows[0] if rows else None

    def get_predictions(self, run_id: str) -> list[dict]:
        """Every game on a run's board."""
        return fetch_all(
            lambda: (
                self.client.table("model_predictions")
                .select("*")
                .eq("run_id", run_id)
                .order("id")
            )
        )
