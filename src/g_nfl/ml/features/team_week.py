"""Weekly team aggregates: offense and defense stats per team-week."""

import polars as pl

from g_nfl.ml.features.plays import PLAY_FEATURE_COLS

# volume stats summed per team-week; rates/negatives are mean-only
SUM_COLS = [
    "yards_gained",
    "yards_after_catch",
    "epa",
    "sack",
    "qb_hit",
    "first_down",
    "touchdown",
    "pass_yards",
    "rush_yards",
    "explosive_pass",
    "explosive_rush",
    "explosive_play",
]
MEAN_COLS = PLAY_FEATURE_COLS


def team_week_stats(plays: pl.DataFrame) -> pl.DataFrame:
    """One row per team/season/week with offense and defense aggregates.

    Offense stats are aggregated over the team's plays as posteam,
    defense stats (suffix ``_def``) over its plays as defteam.
    """
    agg_exprs = (
        [pl.len().alias("plays")]
        + [pl.col(c).sum() for c in SUM_COLS]
        + [pl.col(c).mean().alias(f"{c}_mean") for c in MEAN_COLS]
    )
    weekly_off = plays.group_by(["season", "week", "posteam"]).agg(agg_exprs)
    weekly_def = plays.group_by(["season", "week", "defteam"]).agg(agg_exprs)
    return (
        weekly_off.join(
            weekly_def,
            left_on=["season", "week", "posteam"],
            right_on=["season", "week", "defteam"],
            suffix="_def",
        )
        .rename({"posteam": "team"})
        .sort("team", "season", "week")
    )
