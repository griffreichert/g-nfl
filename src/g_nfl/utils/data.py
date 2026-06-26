from datetime import datetime, timedelta

import nflreadpy as nfl
import polars as pl


def flatten_grouped_cols(cols) -> list[str]:
    # df.columns = flatten_grouped_cols(df.columns)
    return list(map("_".join, cols))


def coach_lambda(row):
    return (
        row["home_coach"] if row["posteam"] == row["home_team"] else row["away_coach"]
    )


def get_current_nfl_week(reference_date: datetime = None) -> tuple[int, int]:
    """
    Determine the current NFL season and week based on the date.

    NFL week runs Tuesday -> Monday (inclusive):
    - Tuesday through Monday = same NFL week
    - Tuesday starts a new week

    Args:
        reference_date: Date to check (defaults to today)

    Returns:
        Tuple of (season, week)

    Example:
        >>> get_current_nfl_week()  # If today is Oct 23, 2025 (Thursday)
        (2025, 8)
    """
    if reference_date is None:
        reference_date = datetime.now()

    # NFL season: Jan-Jul → previous year's season; Aug-Dec → current year
    if reference_date.month <= 7:
        season = reference_date.year - 1
    else:
        season = reference_date.year

    # NFL week runs Tuesday to Monday; find this week's Tuesday
    days_since_tuesday = (reference_date.weekday() - 1) % 7
    week_start = (reference_date - timedelta(days=days_since_tuesday)).date()

    try:
        schedule = nfl.load_schedules(seasons=[season])
    except Exception as e:
        print(f"Warning: Could not load schedule for {season}: {e}")
        if reference_date.month == 9:
            return (season, 1)
        elif reference_date.month >= 10:
            week = ((reference_date - datetime(season, 9, 1)).days // 7) + 1
            return (season, min(week, 18))
        else:
            return (season, 1)

    # Parse gameday strings to dates, compute each game's NFL-week Tuesday
    parsed = (
        schedule.select(["gameday", "week"])
        .with_columns(pl.col("gameday").str.to_date("%Y-%m-%d").alias("gameday_dt"))
        .with_columns(
            (
                pl.col("gameday_dt")
                - pl.duration(days=(pl.col("gameday_dt").dt.weekday() - 1) % 7)
            ).alias("game_week_start")
        )
    )

    match = parsed.filter(pl.col("game_week_start") == pl.lit(week_start))
    if not match.is_empty():
        return (season, int(match["week"][0]))

    # Fallback: closest game by date
    ref_date = reference_date.date()
    closest = (
        parsed.with_columns(
            (pl.col("gameday_dt") - pl.lit(ref_date))
            .dt.total_days()
            .abs()
            .alias("days_diff")
        )
        .sort("days_diff")
        .row(0, named=True)
    )
    return (season, int(closest["week"]))
