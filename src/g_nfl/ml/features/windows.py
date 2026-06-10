"""Season-to-date and rolling-window team stats, forward-filled.

Every team gets a row for every (season, week) in the schedule, so a
team's latest stats are available on its bye week and the lagged join
in `matrix` never drops a game.
"""

import polars as pl
import polars.selectors as cs

DEFAULT_ROLLING_WEEKS = 4


def rolling_suffix(rolling_weeks: int) -> str:
    return f"_last_{rolling_weeks}w"


def add_windows(
    weekly: pl.DataFrame,
    schedule: pl.DataFrame,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
) -> pl.DataFrame:
    """Rolling + season-to-date sums per team, on a full team-week grid.

    `weekly` is the team-week frame from `team_week_stats`; `schedule`
    (regular season only) supplies the full set of (season, week) rows.
    Each stat column gets a ``_last_{n}w`` rolling sum and a ``_season``
    cumulative sum, forward-filled over team/season so weeks without a
    game (byes) carry the previous week's values.
    """
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

    all_weeks = schedule.select("season", "week").unique()
    all_teams = rolled.select("team").unique()
    grid = all_teams.join(all_weeks, how="cross")

    return (
        grid.join(rolled, on=["team", "season", "week"], how="left")
        .sort("team", "season", "week")
        .with_columns(
            cs.ends_with("_season", suffix).forward_fill().over("team", "season")
        )
    )
