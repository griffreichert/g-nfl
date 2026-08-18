"""Push a dated snapshot of fantasy projections to Supabase (issue #81).

    uv run python -m g_nfl.fantasy.ingest --season 2026

Griffin runs this by hand. **The API never scrapes**, which buys three things
worth protecting: a broken scraper leaves the last good snapshot serving, no
scrape sits in the request path to blow a Render cold start, and staleness is
visible in ``snapshot_date`` instead of silent.

The table is created separately — run ``scripts/fantasy_projections_schema.sql``
in the Supabase SQL editor first. This repo has no migration runner, and #81 is
not the place to invent one.
"""

from __future__ import annotations

import argparse
from datetime import date

import polars as pl

from g_nfl.fantasy.sources.espn import fetch_espn_projections
from g_nfl.utils.database import FantasyProjectionsDatabase

#: source name -> loader. One entry today; the schema is keyed on ``source`` so
#: a second feed lands beside ESPN without a migration.
SOURCES = {"espn": fetch_espn_projections}

# Rows missing a gsis_id cannot be joined to anything downstream. The ESPN
# loader already fails below a 95% match rate, so this only drops the tail.
_KEY = "gsis_id"


def to_rows(
    stat_lines: pl.DataFrame, source: str, season: int, snapshot_date: date
) -> list[dict]:
    """Stat lines -> ``fantasy_projections`` rows, dropping unjoinable players."""
    stats = list(FantasyProjectionsDatabase.STAT_COLUMNS)
    return (
        stat_lines.drop_nulls(_KEY)
        .select(
            pl.lit(snapshot_date.isoformat()).alias("snapshot_date"),
            pl.lit(source).alias("source"),
            pl.lit(season).alias("season"),
            pl.col(_KEY).alias("player_id"),
            "player_name",
            "position",
            "team",
            *stats,
        )
        .to_dicts()  # hard boundary: supabase-py speaks dicts, not frames
    )


def ingest(
    season: int,
    source: str = "espn",
    snapshot_date: date | None = None,
    db: FantasyProjectionsDatabase | None = None,
) -> int:
    """Fetch one source and upsert it as today's snapshot. Returns rows written."""
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}; known: {', '.join(SOURCES)}")

    stat_lines = SOURCES[source](season)
    rows = to_rows(stat_lines, source, season, snapshot_date or date.today())
    dropped = stat_lines.height - len(rows)
    if dropped:
        print(f"Dropped {dropped} row(s) with no gsis_id")

    return (db or FantasyProjectionsDatabase()).save_snapshot(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push a dated snapshot of fantasy projections to Supabase. "
        "Run scripts/fantasy_projections_schema.sql once before the first use."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--source", default="espn", choices=sorted(SOURCES))
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Snapshot date (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args()

    written = ingest(args.season, args.source, args.date)
    print(f"Wrote {written} rows for {args.source} {args.season}")


if __name__ == "__main__":
    main()
