#!/usr/bin/env python3
"""Push per-game context and weekly team EPA into Supabase (#71).

The deployed API can't fetch nflverse — `nflreadpy` is an analysis-group
dep, the same reason game_results exists — so the game detail page reads
these tables instead of computing anything at request time.

One-time setup: run scripts/pending_migrations.sql in the SQL editor.
Safe to re-run: everything upserts.

    make update-context                                  # current season
    uv run python scripts/update_game_context.py --season 2024 2025
"""

import argparse
import sys

import nflreadpy as nfl
import polars as pl

from g_nfl.ml.features.plays import play_features
from g_nfl.ml.features.team_week import team_week_stats
from g_nfl.utils.config import CUR_SEASON
from g_nfl.utils.database import GameContextDatabase, TeamWeekStatsDatabase
from g_nfl.utils.web_app import normalize_game_id

# Only players the room would argue about. A full participation report is
# 2,000 rows a week and none of it changes a pick.
INJURY_STATUSES = ("Out", "Doubtful", "Questionable")

# team_week_stats column -> the aggregate team_week_stats() produced
STAT_MAP = {
    "off_epa_play": "epa_mean",
    "def_epa_play": "epa_mean_def",
    "off_success_rate": "success_mean",
    "def_success_rate": "success_mean_def",
    "off_explosive_rate": "explosive_play_mean",
    "def_explosive_rate": "explosive_play_mean_def",
    "off_pass_epa": "pass_epa_mean",
    "off_rush_epa": "rush_epa_mean",
}


def _clean(v):
    """Polars gives NaN for empty aggregates; JSON and Postgres want null."""
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    return v


def push_team_stats(season: int) -> int:
    print(f"Loading {season} play-by-play...")
    pbp = nfl.load_pbp(seasons=[season])
    plays = play_features(pbp, epa_splits=True)
    weekly = team_week_stats(plays)

    rows = []
    for r in weekly.iter_rows(named=True):
        row = {
            "season": season,
            "week": r["week"],
            "team": r["team"],
            "plays": r["plays"],
        }
        for out_col, src in STAT_MAP.items():
            row[out_col] = _clean(r.get(src))
        rows.append(row)
    saved = TeamWeekStatsDatabase().save_stats(rows)
    print(f"Upserted {saved} team-weeks")
    return saved


def push_game_context(season: int) -> int:
    schedule = nfl.load_schedules(seasons=[season]).filter(pl.col("season") == season)
    injuries = nfl.load_injuries(seasons=[season]).filter(
        pl.col("report_status").is_in(INJURY_STATUSES)
    )

    by_team_week: dict[tuple[int, str], list[dict]] = {}
    for i in injuries.iter_rows(named=True):
        by_team_week.setdefault((i["week"], i["team"]), []).append(
            {
                "team": i["team"],
                "name": i["full_name"],
                "position": i["position"],
                "status": i["report_status"],
                "practice": i["practice_status"],
            }
        )

    rows = []
    for g in schedule.iter_rows(named=True):
        hurt = by_team_week.get((g["week"], g["away_team"]), []) + by_team_week.get(
            (g["week"], g["home_team"]), []
        )
        rows.append(
            {
                "game_id": normalize_game_id(g["game_id"]),
                "season": g["season"],
                "week": g["week"],
                "away_team": g["away_team"],
                "home_team": g["home_team"],
                "gameday": str(g["gameday"]) if g["gameday"] else None,
                "gametime": g["gametime"],
                "roof": g["roof"],
                "surface": g["surface"],
                "temp": _clean(g["temp"]),
                "wind": _clean(g["wind"]),
                "stadium": g["stadium"],
                "div_game": bool(g["div_game"]) if g["div_game"] is not None else None,
                "away_rest": g["away_rest"],
                "home_rest": g["home_rest"],
                "away_qb": g["away_qb_name"],
                "home_qb": g["home_qb_name"],
                "away_coach": g["away_coach"],
                "home_coach": g["home_coach"],
                "referee": g["referee"],
                "injuries": hurt,
            }
        )
    saved = GameContextDatabase().save_context(rows)
    print(f"Upserted {saved} games ({injuries.height} injury rows across the season)")
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Push game context into Supabase")
    parser.add_argument("--season", type=int, nargs="+", default=[CUR_SEASON])
    parser.add_argument(
        "--skip-pbp",
        action="store_true",
        help="context only; play-by-play is the slow half",
    )
    args = parser.parse_args()

    for season in args.season:
        if push_game_context(season) == 0:
            print(f"WARNING: no context saved for {season}")
            sys.exit(1)
        if not args.skip_pbp:
            push_team_stats(season)


if __name__ == "__main__":
    main()
