from datetime import datetime, timedelta

import nfl_data_py as nfl

# df.columns = flatten_grouped_cols(df.columns)
flatten_grouped_cols = lambda cols: list(map("_".join, cols))
coach_lambda = lambda row: (
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

    # Determine which season we're in
    # NFL season typically starts in September and runs through February
    # If we're in Jan-July, we're likely in the previous year's season
    # If we're in Aug-Dec, we're in the current year's season
    if reference_date.month <= 7:
        season = reference_date.year - 1
    else:
        season = reference_date.year

    # Get the NFL schedule for this season
    try:
        schedule = nfl.import_schedules([season])
    except Exception as e:
        # Fallback if schedule not available
        print(f"Warning: Could not load schedule for {season}: {e}")
        # Make a best guess based on date
        if reference_date.month == 9:
            return (season, 1)
        elif reference_date.month >= 10:
            # Rough estimate
            week = ((reference_date - datetime(season, 9, 1)).days // 7) + 1
            return (season, min(week, 18))
        else:
            return (season, 1)

    # NFL week runs Tuesday to Monday
    # Adjust reference date to the start of the NFL week (previous Tuesday)
    days_since_tuesday = (reference_date.weekday() - 1) % 7
    week_start = reference_date - timedelta(days=days_since_tuesday)

    # Find the week that contains this date
    for _, game in schedule.iterrows():
        if "gameday" not in schedule.columns:
            continue

        game_date = game["gameday"]
        if isinstance(game_date, str):
            game_date = datetime.strptime(game_date, "%Y-%m-%d")

        # Calculate the Tuesday of this game's week
        game_days_since_tuesday = (game_date.weekday() - 1) % 7
        game_week_start = game_date - timedelta(days=game_days_since_tuesday)

        # Check if our week_start matches this game's week_start
        if week_start.date() == game_week_start.date():
            return (season, int(game["week"]))

    # If no exact match found, find the closest week
    # This handles edge cases like dates before/after the season
    schedule["gameday_dt"] = schedule["gameday"].apply(
        lambda x: datetime.strptime(x, "%Y-%m-%d") if isinstance(x, str) else x
    )

    # Find the game closest to our reference date
    schedule["days_diff"] = (schedule["gameday_dt"] - reference_date).abs()
    closest_game = schedule.loc[schedule["days_diff"].idxmin()]

    return (season, int(closest_game["week"]))
