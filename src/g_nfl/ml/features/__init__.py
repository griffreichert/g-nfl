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

from g_nfl.ml.features.context import add_schedule_context
from g_nfl.ml.features.injuries import add_injuries
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
    half_life: float | None = None,
    epa_splits: bool = False,
    carryover_k: float | None = None,
    injuries: pl.DataFrame | None = None,
    schedule_ctx: bool = False,
) -> pl.DataFrame:
    """Full pipeline: raw pbp + schedule -> game-level training matrix.

    ``half_life`` set switches the windowing to L2 time decay (EWMA over
    games, rate cols only); None keeps the L1 flat rolling/season cols.
    ``epa_splits`` adds the L2 pass/rush/early-down EPA features.
    ``carryover_k`` (flat path) adds prior-season-carryover ``_carry`` rate
    cols (pseudo-games of prior; see `carryover.add_carryover`).
    ``injuries`` (L3) joins home/away team-week injury burden, no lag
    (see `injuries.add_injuries`); None leaves the matrix unchanged.
    ``schedule_ctx`` (L3) appends rest/day-of-week/division context, no lag
    (see `context.add_schedule_context`).
    """
    reg_schedule = schedule.filter(pl.col("game_type") == "REG")
    plays = play_features(pbp, wp_filter, epa_splits=epa_splits)
    weekly = team_week_stats(plays)
    windowed = add_windows(
        weekly,
        reg_schedule,
        rolling_weeks,
        half_life=half_life,
        carryover_k=carryover_k,
    )
    matrix = build_game_matrix(
        windowed,
        reg_schedule,
        rolling_weeks,
        min_week=min_week,
        half_life=half_life,
        carryover_k=carryover_k,
    )
    if injuries is not None:
        matrix = add_injuries(matrix, injuries)
    if schedule_ctx:
        matrix = add_schedule_context(matrix, reg_schedule)
    return matrix
