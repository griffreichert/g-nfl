from pathlib import Path

import polars as pl
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def pbp_sample() -> pl.DataFrame:
    """Play-by-play for 10 games (KC/BUF, 2023 weeks 1-5).

    Regenerate with tests/fixtures/make_fixtures.py.
    """
    return pl.read_parquet(FIXTURES_DIR / "pbp_sample.parquet")


@pytest.fixture(scope="session")
def schedule_sample() -> pl.DataFrame:
    """Schedule rows for the same 10 games as pbp_sample."""
    return pl.read_parquet(FIXTURES_DIR / "schedule_sample.parquet")
