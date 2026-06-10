"""Regenerate the test fixture parquets from nflreadpy.

Run from the repo root:

    uv run python tests/fixtures/make_fixtures.py

Downloads 2023 pbp (~50MB, cached by nflreadpy) and keeps every game
involving KC or BUF in weeks 1-5: 10 games, ~1700 plays. Big enough to
exercise weekly aggregates, rolling windows, and lagged joins; small
enough to commit.
"""

from pathlib import Path

import nflreadpy as nfl
import polars as pl

TEAMS = ["KC", "BUF"]
SEASON, MAX_WEEK = 2023, 5

FIXTURES_DIR = Path(__file__).parent


def main() -> None:
    sched = nfl.load_schedules(seasons=[SEASON])
    sched_sample = sched.filter(
        (pl.col("week") <= MAX_WEEK)
        & (pl.col("home_team").is_in(TEAMS) | pl.col("away_team").is_in(TEAMS))
    )
    game_ids = sched_sample["game_id"].to_list()
    print(f"{len(game_ids)} games: {game_ids}")

    pbp = nfl.load_pbp(seasons=[SEASON])
    pbp_sample = pbp.filter(pl.col("game_id").is_in(game_ids))
    print(f"pbp rows: {pbp_sample.shape}")

    pbp_sample.write_parquet(FIXTURES_DIR / "pbp_sample.parquet")
    sched_sample.write_parquet(FIXTURES_DIR / "schedule_sample.parquet")


if __name__ == "__main__":
    main()
