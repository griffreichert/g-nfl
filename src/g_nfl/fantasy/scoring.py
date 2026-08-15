"""League scoring config and stat-line -> projected-points scoring (issue #88).

Consumes the stat-line schema pinned in #88/#87: ``gsis_id, espn_id,
player_name, position, team, pass_yd, pass_td, ints, rush_yd, rush_td, rec,
rec_yd, rec_td, fum`` (season totals). ``score()`` is a dot product against
``Scoring`` and adds ``proj_points`` and ``proj_ppg`` (the column name
``fantasy/projections/board.py`` expects).
"""

import polars as pl
from pydantic import BaseModel


class Scoring(BaseModel):
    """Points per stat. Season totals in, so these are per-unit weights."""

    reception: float = 0.5  # 0 standard, 0.5 half, 1.0 full
    te_premium: float = 0.0  # extra per reception, TE only
    rec_yd: float = 0.1
    rush_yd: float = 0.1
    pass_yd: float = 0.04
    td: float = 6.0  # rushing + receiving
    pass_td: float = 4.0
    interception: float = -2.0
    fumble_lost: float = -2.0


class LeagueConfig(BaseModel):
    """A league's roster shape and scoring rules."""

    teams: int = 12
    roster_positions: list[str]  # Sleeper slot vocabulary: see board.FLEX_ELIGIBILITY
    bench: int = 6
    scoring: Scoring = Scoring()


def score(stat_lines: pl.DataFrame, config: LeagueConfig) -> pl.DataFrame:
    """Season stat lines -> ``proj_points`` and ``proj_ppg`` under ``config``."""
    s = config.scoring
    te_bonus = pl.when(pl.col("position") == "TE").then(s.te_premium).otherwise(0.0)
    proj_points = (
        (s.reception + te_bonus) * pl.col("rec")
        + s.rec_yd * pl.col("rec_yd")
        + s.rush_yd * pl.col("rush_yd")
        + s.pass_yd * pl.col("pass_yd")
        + s.td * (pl.col("rush_td") + pl.col("rec_td"))
        + s.pass_td * pl.col("pass_td")
        + s.interception * pl.col("ints")
        + s.fumble_lost * pl.col("fum")
    )
    return stat_lines.with_columns(
        proj_points.alias("proj_points"),
        (proj_points / 17).alias("proj_ppg"),
    )


HALF_PPR_12 = LeagueConfig(
    teams=12,
    roster_positions=["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"],
    bench=6,
    scoring=Scoring(reception=0.5),
)

# Primary preset (confirmed 2026-08-15): Griffin's league is 12-team full PPR, 1QB.
PPR_12 = LeagueConfig(
    teams=12,
    roster_positions=["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"],
    bench=6,
    scoring=Scoring(reception=1.0),
)

SUPERFLEX_12 = LeagueConfig(
    teams=12,
    roster_positions=["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX"],
    bench=6,
    scoring=Scoring(reception=1.0),
)

TE_PREMIUM_12 = LeagueConfig(
    teams=12,
    roster_positions=["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"],
    bench=6,
    scoring=Scoring(reception=0.5, te_premium=0.5),
)

PRESETS: dict[str, LeagueConfig] = {
    "ppr_12": PPR_12,
    "half_ppr_12": HALF_PPR_12,
    "superflex_12": SUPERFLEX_12,
    "te_premium_12": TE_PREMIUM_12,
}
