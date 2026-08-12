"""Load every season of pool picks and pool spreads into Supabase.

Two sources feed one pair of tables:

- **2020-2024** — the family workbooks in Drive, via `pool.gsheets`. Six
  entries: the five members and `Team`, the set Reichert actually submits.
- **2025** — the Cville standings workbook, via `pool.parser`. All sixteen
  pool entries, where Reichert is one row among the field.

`Team` and `Reichert` are the same entry under two spellings, so the older
seasons are renamed to `Reichert` and the series runs 2020-2025 unbroken.

Both tables use the nflverse sign convention: a spread is positive when the
**home** team is favoured. That was verified against the rows already in
`pool_spreads` — as-is the mean absolute difference from `spread_line` is
0.50, negated it is 10.2.

    uv run python -m g_nfl.pool.load --seasons 2020 2021 2022 2023 2024 2025
"""

from __future__ import annotations

import polars as pl

from g_nfl.pool.grade import grade, load_games
from g_nfl.pool.gsheets import POOL_DIR, WORKBOOKS, pull_picks, pull_pool_lines
from g_nfl.utils.database import PoolPicksDatabase, PoolSpreadsDatabase

# the family workbooks call it TEAM; the Cville workbook calls it Reichert
TEAM_ENTRY = "Reichert"
CVILLE_SEASONS = (2025,)


def _cville(season: int) -> pl.DataFrame:
    """Picks from the Cville standings workbook, in `pull_picks` shape."""
    from g_nfl.pool.parser import parse_workbook

    rows = parse_workbook(POOL_DIR / f"standings_{season}.xlsx", season=season)
    return pl.DataFrame(rows).select(
        "season", "week", "week_label", "picker", "slot", "pick_type", "team_picked"
    )


def season_picks(season: int) -> pl.DataFrame:
    picks = _cville(season) if season in CVILLE_SEASONS else pull_picks(season)
    return picks.with_columns(
        picker=pl.col("picker").replace({"Team": TEAM_ENTRY}),
    )


def season_pool_lines(season: int) -> pl.DataFrame:
    """Pool spreads per game, home perspective.

    The Cville workbook has no lines block this parser reads directly, but
    every picker's row carries the spread they were graded against, and all
    sixteen record the same number — so the game's line is recoverable from
    the picks themselves.
    """
    if season not in CVILLE_SEASONS:
        return pull_pool_lines(season)

    from g_nfl.pool.parser import parse_workbook

    rows = pl.DataFrame(parse_workbook(POOL_DIR / f"standings_{season}.xlsx", season))
    games = load_games([season]).select("season", "week", "home_team", "away_team")
    return (
        rows.filter(pl.col("game_id").is_not_null(), pl.col("spread").is_not_null())
        .join(games, on=["season", "week"], how="inner")
        .filter(
            (pl.col("team_picked") == pl.col("home_team"))
            | (pl.col("team_picked") == pl.col("away_team"))
        )
        # the workbook signs the spread for the team picked, so flip the home side
        .with_columns(
            pool_spread=pl.when(pl.col("team_picked") == pl.col("home_team"))
            .then(-pl.col("spread"))
            .otherwise(pl.col("spread"))
        )
        .group_by("season", "week", "home_team", "away_team")
        .agg(pool_spread=pl.col("pool_spread").median())
    )


def load(seasons: list[int], *, dry_run: bool = False) -> dict[str, int]:
    """Grade every season and upsert both tables. Returns row counts."""
    picks = pl.concat([season_picks(s) for s in seasons], how="diagonal_relaxed")
    lines = pl.concat(
        [
            season_pool_lines(s)
            for s in seasons
            if s in WORKBOOKS or s in CVILLE_SEASONS
        ],
        how="diagonal_relaxed",
    )
    graded = grade(picks, load_games(seasons), lines)

    if dry_run:
        return {"picks": graded.height, "spreads": lines.height}

    spread_db = PoolSpreadsDatabase()
    written_spreads = 0
    with_ids = lines.join(
        load_games(seasons).select("season", "week", "home_team", "game_id"),
        on=["season", "week", "home_team"],
        how="inner",
    )
    for (season, week), block in with_ids.group_by(["season", "week"]):
        # replace=True also repairs the 13 week-8 rows whose game_id was
        # written without a zero-padded week and joined to nothing
        written_spreads += spread_db.save_pool_spreads(
            season,
            week,
            dict(zip(block["game_id"], block["pool_spread"], strict=True)),
            replace=True,
        )

    rows = graded.select(
        "season",
        "week",
        "week_label",
        "picker",
        "slot",
        "pick_type",
        "team_picked",
        pl.col("team_spread").alias("spread"),
        "game_id",
        pl.col("ats_result").alias("result"),
    ).to_dicts()
    written_picks = PoolPicksDatabase().save_picks(rows)
    return {"picks": written_picks, "spreads": written_spreads}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--seasons", type=int, nargs="+", default=[2020, 2021, 2022, 2023, 2024, 2025]
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    counts = load(args.seasons, dry_run=args.dry_run)
    print(f"{counts['picks']} picks, {counts['spreads']} pool spreads")


if __name__ == "__main__":
    main()
