"""Game-level training matrix: lagged team stats joined onto the schedule.

Each game row gets its home and away team's windowed stats as of the
*previous* week (1-week lag), so a game's features never include the
game itself — see the anti-leakage test.
"""

import polars as pl
import polars.selectors as cs

from g_nfl.ml.features.windows import DEFAULT_ROLLING_WEEKS, rolling_suffix

# schedule columns carried through the matrix; everything else is a feature
META_COLS = [
    "game_id",
    "season",
    "week",
    "away_team",
    "home_team",
    "result",
    "spread_line",
]


def build_game_matrix(
    windowed: pl.DataFrame,
    schedule: pl.DataFrame,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
    min_week: int | None = None,
) -> pl.DataFrame:
    """Join home/away windowed stats onto the schedule with a 1-week lag.

    `windowed` comes from `add_windows`; `schedule` must already be
    filtered to regular season. `min_week` drops early-season rows where
    the windowed stats are still thin (the notebooks used 4).
    """
    suffix = rolling_suffix(rolling_weeks)
    stats = windowed.select("team", "season", "week", cs.ends_with("_season", suffix))

    away_stats = stats.select(
        pl.col("team").alias("away_team"),
        "season",
        "week",
        cs.ends_with("_season", suffix).name.prefix("away_"),
    )
    home_stats = stats.select(
        pl.col("team").alias("home_team"),
        "season",
        "week",
        cs.ends_with("_season", suffix).name.prefix("home_"),
    )

    matrix = (
        schedule.select(META_COLS)
        .join(
            away_stats,
            left_on=["away_team", "season", pl.col("week") - 1],
            right_on=["away_team", "season", "week"],
            how="left",
        )
        .drop("season_right", "week_right", "away_team_right", strict=False)
        .join(
            home_stats,
            left_on=["home_team", "season", pl.col("week") - 1],
            right_on=["home_team", "season", "week"],
            how="left",
        )
        .drop("season_right", "week_right", "home_team_right", strict=False)
    )
    if min_week is not None:
        matrix = matrix.filter(pl.col("week") >= min_week)
    return matrix
