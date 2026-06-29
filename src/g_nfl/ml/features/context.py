"""L3 schedule context: rest, short-week / off-bye, day-of-week, division.

All values come straight off the schedule and are known pre-kickoff, so
unlike performance stats they need **no lag** — joined on ``game_id``.
Off by default (see ``build_features`` ``schedule_ctx``).
"""

import polars as pl


def add_schedule_context(matrix: pl.DataFrame, schedule: pl.DataFrame) -> pl.DataFrame:
    """Append rest/day-of-week/division context columns, joined on game_id.

    ``rest_diff`` is the home minus away rest-day gap (the market's rest
    edge); ``*_off_bye`` flags >9 days (coming off a bye), ``*_short_week``
    flags <7 (Thu game after a Sunday); ``thursday``/``monday`` mark the
    standalone slots; ``div_game`` the divisional matchup. All boolean flags
    are 0/1 ints so the tree treats them as plain features.
    """
    ctx = schedule.select(
        "game_id",
        rest_diff=pl.col("home_rest") - pl.col("away_rest"),
        home_off_bye=(pl.col("home_rest") > 9).cast(pl.Int8),
        away_off_bye=(pl.col("away_rest") > 9).cast(pl.Int8),
        home_short_week=(pl.col("home_rest") < 7).cast(pl.Int8),
        away_short_week=(pl.col("away_rest") < 7).cast(pl.Int8),
        thursday=(pl.col("weekday") == "Thursday").cast(pl.Int8),
        monday=(pl.col("weekday") == "Monday").cast(pl.Int8),
        div_game=pl.col("div_game").cast(pl.Int8),
    )
    return matrix.join(ctx, on="game_id", how="left")
