"""Season-to-date and rolling-window team stats, forward-filled.

Every team gets a row for every (season, week) in the schedule, so a
team's latest stats are available on its bye week and the lagged join
in `matrix` never drops a game.
"""

import polars as pl
import polars.selectors as cs

from g_nfl.ml.features.carryover import add_carryover

DEFAULT_ROLLING_WEEKS = 4


def rolling_suffix(rolling_weeks: int) -> str:
    return f"_last_{rolling_weeks}w"


def add_windows(
    weekly: pl.DataFrame,
    schedule: pl.DataFrame,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
    half_life: float | None = None,
    carryover_k: float | None = None,
) -> pl.DataFrame:
    """Per-team windowed stats on a full team-week grid.

    `weekly` is the team-week frame from `team_week_stats`; `schedule`
    (regular season only) supplies the full set of (season, week) rows.
    With ``half_life=None`` (L1): each stat gets a ``_last_{n}w`` rolling
    sum and a ``_season`` cumulative sum. With ``half_life`` set (L2 time
    decay): each rate (``*_mean``) stat gets one exponentially-weighted
    ``_ewm`` column instead — half-life in *games*, volume sums dropped.
    ``carryover_k`` (flat path only) appends prior-season-carryover
    ``_carry`` rate cols (see `carryover.add_carryover`). Either way columns
    are forward-filled over team/season so bye weeks carry the previous
    week's values.
    """
    if half_life is not None:
        return _decayed_windows(weekly, schedule, half_life)

    suffix = rolling_suffix(rolling_weeks)
    stat_cols = cs.exclude("team", "season", "week")

    rolled = weekly.sort("team", "season", "week").with_columns(
        stat_cols.rolling_sum(window_size=rolling_weeks, min_samples=1)
        .over("team", "season")
        .name.suffix(suffix)
    )
    rolled = rolled.with_columns(
        (stat_cols - cs.ends_with(suffix))
        .cum_sum()
        .over("team", "season")
        .name.suffix("_season")
    )

    if carryover_k is not None:
        rolled = add_carryover(rolled, carryover_k)

    all_weeks = schedule.select("season", "week").unique()
    all_teams = rolled.select("team").unique()
    grid = all_teams.join(all_weeks, how="cross")

    return (
        grid.join(rolled, on=["team", "season", "week"], how="left")
        .sort("team", "season", "week")
        .with_columns(
            cs.ends_with("_season", suffix, "_carry")
            .forward_fill()
            .over("team", "season")
        )
    )


def _decayed_windows(
    weekly: pl.DataFrame, schedule: pl.DataFrame, half_life: float
) -> pl.DataFrame:
    """L2 time decay: one EWMA ``_ewm`` column per rate stat.

    Keeps only rate (``*_mean`` / ``*_mean_def``) columns — raw volume
    sums are dropped (L1 found them dead weight). The EWMA runs over the
    team's actual game rows within a season (half-life in games, so byes
    aren't double-penalised), then forward-fills onto the bye grid.
    """
    rate_cols = cs.contains("_mean")

    decayed = (
        weekly.sort("team", "season", "week")
        .select("team", "season", "week", rate_cols)
        .with_columns(
            rate_cols.ewm_mean(half_life=half_life, min_samples=1, ignore_nulls=True)
            .over("team", "season")
            .name.suffix("_ewm")
        )
        .select("team", "season", "week", cs.ends_with("_ewm"))
    )

    all_weeks = schedule.select("season", "week").unique()
    all_teams = decayed.select("team").unique()
    grid = all_teams.join(all_weeks, how="cross")

    return (
        grid.join(decayed, on=["team", "season", "week"], how="left")
        .sort("team", "season", "week")
        .with_columns(cs.ends_with("_ewm").forward_fill().over("team", "season"))
    )
