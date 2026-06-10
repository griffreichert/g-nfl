"""Feature engineering: play-level features, weekly team aggregates,
rolling windows, and the game-level training matrix.

Modules:
- plays: pbp filters + play-level features (havoc, explosive, ...)
- team_week: weekly offense/defense team aggregates
- windows: season-to-date + rolling windows with forward fill
- matrix: home/away join onto schedule with 1-week lag
- registry: named, versioned feature sets
"""

import polars as pl

from g_nfl.ml.features.matrix import build_game_matrix
from g_nfl.ml.features.plays import play_features
from g_nfl.ml.features.team_week import team_week_stats
from g_nfl.ml.features.windows import DEFAULT_ROLLING_WEEKS, add_windows
from g_nfl.utils.config import DEFAULT_WIN_PROB


def build_features(
    pbp: pl.DataFrame,
    schedule: pl.DataFrame,
    *,
    wp_filter: float = DEFAULT_WIN_PROB,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
    min_week: int | None = None,
) -> pl.DataFrame:
    """Full pipeline: raw pbp + schedule -> game-level training matrix."""
    reg_schedule = schedule.filter(pl.col("game_type") == "REG")
    plays = play_features(pbp, wp_filter)
    weekly = team_week_stats(plays)
    windowed = add_windows(weekly, reg_schedule, rolling_weeks)
    return build_game_matrix(windowed, reg_schedule, rolling_weeks, min_week=min_week)
