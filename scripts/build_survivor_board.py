"""Generate the survivor board artifact the API plans against (#72).

The planner needs a win probability for every (team, week) left in the
season, including weeks no book has priced yet. That means the forward
schedule and a power rating per team, neither of which the deployed API
can reach: Render has no nflverse access and no polars, and there is no
schedule table in Supabase.

So it is generated here and committed:
``src/g_nfl/picks/boards/survivor_board_<season>.json``. Ratings are the
market-derived ones (#50) solved through the last week that has a full
slate of lines, and every game carries a model spread from
``ovr_home - ovr_away + hfa``. The API overrides that with a real market
line wherever Supabase has one, so the near weeks use the book and the
far weeks use the ratings.

Rerun weekly, after the lines land:

    uv run python scripts/build_survivor_board.py --season 2026
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from g_nfl.ml.data import load_schedule
from g_nfl.ml.market_ratings import market_ratings
from g_nfl.picks.boards import board_path
from g_nfl.picks.calendar import current_season

# Weeks priced only for a handful of lookahead games do not describe the
# market's view of the league, and solving a week off 1 game is noise.
MIN_GAMES_FOR_A_RATED_WEEK = 12

# Seasons of lines the ratings are solved from. The trajectory is ridged
# week to week and carried across seasons, so a couple of prior seasons
# is enough to have converged by the time it reaches the current one.
LOOKBACK_SEASONS = 2


def rated_schedule(seasons: list[int]) -> pl.DataFrame:
    """Priced REG games, dropping weeks the book has barely opened."""
    sched = load_schedule(seasons, refresh=True).filter(
        (pl.col("game_type") == "REG") & pl.col("spread_line").is_not_null()
    )
    counts = sched.group_by("season", "week").len()
    full = counts.filter(pl.col("len") >= MIN_GAMES_FOR_A_RATED_WEEK).select(
        "season", "week"
    )
    return sched.join(full, on=["season", "week"], how="inner")


def build(season: int) -> dict:
    seasons = list(range(season - LOOKBACK_SEASONS, season + 1))
    ratings = market_ratings(rated_schedule(seasons))

    # the freshest solve available: the last rated week of the last season
    latest_season = ratings["season"].max()
    in_season = ratings.filter(pl.col("season") == latest_season)
    latest_week = in_season["week"].max()
    latest = in_season.filter(pl.col("week") == latest_week)

    ovr = dict(zip(latest["team"], latest["ovr_rating"], strict=True))
    hfa = float(latest["hfa"][0])

    games = []
    schedule = load_schedule([season]).filter(pl.col("game_type") == "REG")
    for row in schedule.sort("week", "game_id").iter_rows(named=True):
        home, away = row["home_team"], row["away_team"]
        if home not in ovr or away not in ovr:
            continue  # a team with no rating cannot be planned around
        neutral = row.get("location") == "Neutral"
        games.append(
            {
                "game_id": row["game_id"],
                "week": int(row["week"]),
                "home": home,
                "away": away,
                # positive = home favoured, the nflverse spread_line convention
                "model_spread": round(
                    ovr[home] - ovr[away] + (0.0 if neutral else hfa), 2
                ),
                "market_spread": (
                    None if row["spread_line"] is None else float(row["spread_line"])
                ),
            }
        )

    return {
        "season": season,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ratings_through": {"season": int(latest_season), "week": int(latest_week)},
        "hfa": round(hfa, 2),
        "ratings": {t: round(float(r), 2) for t, r in sorted(ovr.items())},
        "games": games,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, default=current_season())
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()

    board = build(args.season)
    out = args.output or board_path(args.season)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, indent=1) + "\n")

    through = board["ratings_through"]
    print(
        f"{out}: {len(board['games'])} games, {len(board['ratings'])} teams, "
        f"ratings through {through['season']} wk {through['week']}"
    )


if __name__ == "__main__":
    main()
