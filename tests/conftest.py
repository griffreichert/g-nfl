from pathlib import Path

import polars as pl
import pytest

from g_nfl.utils.supabase_client import SupabaseClient

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


@pytest.fixture(autouse=True)
def no_supabase(monkeypatch):
    """Fail any test that reaches Supabase.

    CI holds no credentials, so a test that opens a client passes here, off a
    developer's `.env`, and dies in CI. Twice on 2026-09-05 (#137).
    """

    def _blocked(*_args, **_kwargs):
        raise RuntimeError(
            "This test opened a Supabase client. Stub the call: CI has no credentials."
        )

    monkeypatch.setattr(SupabaseClient, "get_client", classmethod(_blocked))
