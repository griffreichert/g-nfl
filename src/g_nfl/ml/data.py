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
