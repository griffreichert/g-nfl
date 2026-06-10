"""Play-level filters and features.

The havoc definition here (any of forced fumble / TFL / INT / sack /
QB hit on a play) is the canonical one; it supersedes the pandas
``g_nfl.modelling.metrics.calculate_havoc``, which omits qb_hit.
"""

import polars as pl

from g_nfl.utils.config import (
    DEFAULT_WIN_PROB,
    EXPLOSIVE_PASS_THRESHOLD,
    EXPLOSIVE_RUN_THRESHOLD,
)

ID_COLS = ["season", "week", "posteam", "defteam"]

HAVOC_COLS = ["fumble_forced", "tackled_for_loss", "interception", "sack", "qb_hit"]

# play-level features fed into the team-week aggregates
PLAY_FEATURE_COLS = [
    "yards_gained",
    "air_yards",
    "yards_after_catch",
    "epa",
    "interception",
    "fumble_forced",
    "tackled_for_loss",
    "qb_hit",
    "sack",
    "touchdown",
    "cpoe",
    "success",
    "first_down",
    "pass_oe",
    "pass_yards",
    "rush_yards",
    "explosive_pass",
    "explosive_rush",
    "explosive_play",
    "havoc",
]


def filter_plays(
    pbp: pl.DataFrame, wp_filter: float = DEFAULT_WIN_PROB
) -> pl.DataFrame:
    """Regular-season run/pass plays with garbage time removed.

    Keeps plays where the offense's win probability is within
    [wp_filter, 1 - wp_filter].
    """
    return pbp.filter(
        pl.col("play_type").is_in(["run", "pass"])
        & (pl.col("season_type") == "REG")
        & pl.col("wp").is_between(wp_filter, 1 - wp_filter)
    )


def add_play_features(
    pbp: pl.DataFrame,
    explosive_pass_yards: int = EXPLOSIVE_PASS_THRESHOLD,
    explosive_rush_yards: int = EXPLOSIVE_RUN_THRESHOLD,
) -> pl.DataFrame:
    """Derived play-level features: havoc, explosive plays, split yards.

    Also rescales cpoe / pass_oe from percentage points to rates.
    """
    return pbp.with_columns(
        pl.any_horizontal(HAVOC_COLS).alias("havoc"),
        (pl.col("pass_oe") / 100).alias("pass_oe"),
        (pl.col("cpoe") / 100).alias("cpoe"),
        pl.when(pl.col("pass_attempt") == 1)
        .then(pl.col("yards_gained"))
        .otherwise(None)
        .alias("pass_yards"),
        pl.when(pl.col("rush_attempt") == 1)
        .then(pl.col("yards_gained"))
        .otherwise(None)
        .alias("rush_yards"),
        (
            (pl.col("yards_gained") >= explosive_pass_yards)
            & (pl.col("play_type") == "pass")
        ).alias("explosive_pass"),
        (
            (pl.col("yards_gained") >= explosive_rush_yards)
            & (pl.col("play_type") == "run")
        ).alias("explosive_rush"),
        (
            (
                (pl.col("yards_gained") >= explosive_pass_yards)
                & (pl.col("play_type") == "pass")
            )
            | (
                (pl.col("yards_gained") >= explosive_rush_yards)
                & (pl.col("play_type") == "run")
            )
        ).alias("explosive_play"),
    )


def play_features(
    pbp: pl.DataFrame,
    wp_filter: float = DEFAULT_WIN_PROB,
) -> pl.DataFrame:
    """Filter raw pbp and return id + play-level feature columns only."""
    return add_play_features(filter_plays(pbp, wp_filter)).select(
        ID_COLS + PLAY_FEATURE_COLS
    )
