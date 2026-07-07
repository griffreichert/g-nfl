"""Play-by-play and schedule loaders with a local parquet cache.

Wraps `nflreadpy` so the rest of the pipeline never touches the network
layer directly. Each season is cached as one parquet under
``data/ml_cache/`` (gitignored). Pass ``refresh=True`` to refetch — do
this for the current season during the year, since its pbp grows weekly.
"""

from pathlib import Path

import nflreadpy as nfl
import polars as pl

# repo root: src/g_nfl/ml/data.py -> ml -> g_nfl -> src -> root
DEFAULT_CACHE_DIR = Path(__file__).parents[3] / "data" / "ml_cache"


def _fetch(dataset: str, season: int) -> pl.DataFrame:
    if dataset == "pbp":
        return nfl.load_pbp(seasons=[season])
    if dataset == "schedule":
        return nfl.load_schedules(seasons=[season])
    if dataset == "injuries":
        return nfl.load_injuries(seasons=[season])
    if dataset == "rosters_weekly":
        return nfl.load_rosters_weekly(seasons=[season])
    if dataset == "snap_counts":
        return nfl.load_snap_counts(seasons=[season])
    raise ValueError(f"unknown dataset {dataset!r}")


def _load_cached(
    dataset: str, season: int, cache_dir: Path, refresh: bool
) -> pl.DataFrame:
    path = cache_dir / f"{dataset}_{season}.parquet"
    if path.exists() and not refresh:
        return pl.read_parquet(path)
    df = _fetch(dataset, season)
    cache_dir.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return df


def load_pbp(
    seasons: list[int],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pl.DataFrame:
    """Play-by-play for the given seasons, cached per season."""
    return pl.concat(
        [_load_cached("pbp", s, Path(cache_dir), refresh) for s in seasons],
        how="vertical_relaxed",
    )


def load_schedule(
    seasons: list[int],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pl.DataFrame:
    """Schedules (with results and market lines) for the given seasons."""
    return pl.concat(
        [_load_cached("schedule", s, Path(cache_dir), refresh) for s in seasons],
        how="vertical_relaxed",
    )


def load_injuries(
    seasons: list[int],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pl.DataFrame:
    """Weekly injury reports (game status + practice status), 2009+.

    One row per player-team-week on the report; players not listed are
    healthy. Key columns: gsis_id, team, week, position, report_status
    (Out/Doubtful/Questionable, null = listed but no game designation),
    practice_status.

    Schema drifts across seasons (2025 adds `season_type`, drops
    `date_modified`; `game_type` is present in both) so this concats
    diagonally by column name instead of position — extra/missing columns
    null-fill rather than erroring.
    """
    return pl.concat(
        [_load_cached("injuries", s, Path(cache_dir), refresh) for s in seasons],
        how="diagonal_relaxed",
    )


def load_rosters_weekly(
    seasons: list[int],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pl.DataFrame:
    """Weekly roster snapshots; `status` catches IR/PUP stints (RES,
    INA, ...) that drop off the injury report."""
    return pl.concat(
        [_load_cached("rosters_weekly", s, Path(cache_dir), refresh) for s in seasons],
        how="vertical_relaxed",
    )


def load_snap_counts(
    seasons: list[int],
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pl.DataFrame:
    """Per-game snap counts (realized workload; pfr player ids)."""
    return pl.concat(
        [_load_cached("snap_counts", s, Path(cache_dir), refresh) for s in seasons],
        how="vertical_relaxed",
    )


def load_players(
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pl.DataFrame:
    """Master player table, career-spanning (no season split).

    Used as the `gsis_id` <-> `pfr_id` crosswalk between injuries and
    snap counts (`features.availability`).
    """
    path = Path(cache_dir) / "players.parquet"
    if path.exists() and not refresh:
        return pl.read_parquet(path)
    df = nfl.load_players()
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return df
