"""Build the head-coach layer of data/coaches/playcallers.csv from nflreadpy schedules.

HC name and week ranges are authoritative from schedule.home_coach/away_coach,
so this needs no scraping. Everything else in the playcaller-network schema
(OC, DC, offensive_playcaller, defensive_playcaller, prior_team, prior_role,
first_year_in_role, is_interim) is not derivable from the schedule and is
researched separately. See notes/playcaller-network.md for the full schema.
"""

import nflreadpy as nfl
import polars as pl

from g_nfl.utils.teams import standardize_teams

PLAYCALLER_COLUMNS = [
    "season",
    "team",
    "role",
    "name",
    "start_week",
    "end_week",
    "is_interim",
    "first_year_in_role",
    "prior_team",
    "prior_role",
    "source_url",
    "confidence",
]


def build_hc_spells(start_season: int = 2015, end_season: int = 2025) -> pl.DataFrame:
    """One row per (season, team) head-coach spell, derived from schedule coach fields."""
    sched = nfl.load_schedules().filter(
        (pl.col("season") >= start_season)
        & (pl.col("season") <= end_season)
        & (pl.col("game_type") == "REG")
    )

    long = (
        pl.concat(
            [
                sched.select(
                    "season",
                    "week",
                    pl.col("home_team").alias("team"),
                    pl.col("home_coach").alias("coach"),
                ),
                sched.select(
                    "season",
                    "week",
                    pl.col("away_team").alias("team"),
                    pl.col("away_coach").alias("coach"),
                ),
            ]
        )
        .unique()
        .sort(["season", "team", "week"])
    )
    long = long.with_columns(
        pl.col("team").map_elements(standardize_teams, return_dtype=pl.Utf8)
    )

    spells = []
    for (season, team), group in long.group_by(["season", "team"], maintain_order=True):
        weeks = group.sort("week")
        rows = list(weeks.iter_rows(named=True))
        spell_start = rows[0]["week"]
        spell_coach = rows[0]["coach"]
        for i in range(1, len(rows)):
            if rows[i]["coach"] != spell_coach:
                spells.append(
                    (season, team, spell_coach, spell_start, rows[i - 1]["week"])
                )
                spell_start = rows[i]["week"]
                spell_coach = rows[i]["coach"]
        spells.append((season, team, spell_coach, spell_start, rows[-1]["week"]))

    out = pl.DataFrame(
        spells,
        schema=["season", "team", "name", "start_week", "end_week"],
        orient="row",
    )
    out = out.with_columns(
        pl.lit("HC").alias("role"),
        pl.lit(None, dtype=pl.Int64).alias("is_interim"),
        pl.lit(None, dtype=pl.Int64).alias("first_year_in_role"),
        pl.lit(None, dtype=pl.Utf8).alias("prior_team"),
        pl.lit(None, dtype=pl.Utf8).alias("prior_role"),
        pl.lit("nflreadpy load_schedules() home_coach/away_coach").alias("source_url"),
        pl.lit("high").alias("confidence"),
    )
    return out.select(PLAYCALLER_COLUMNS)


if __name__ == "__main__":
    import os

    hc = build_hc_spells()
    path = "data/coaches/playcallers.csv"
    if os.path.exists(path):
        existing = pl.read_csv(path)
        other_roles = existing.filter(pl.col("role") != "HC")
        out = pl.concat([hc, other_roles], how="diagonal_relaxed")
    else:
        out = hc
    out = out.sort(["season", "team", "role", "start_week"])
    out.write_csv(path)
    print(f"wrote {len(hc)} HC rows + {len(out) - len(hc)} other-role rows to {path}")
