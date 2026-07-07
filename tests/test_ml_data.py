"""Tests for the g_nfl.ml.data parquet cache (#9). Network fetches are
stubbed out via _fetch."""

import polars as pl
import pytest

from g_nfl.ml import data


@pytest.fixture
def fetch_calls(monkeypatch, pbp_sample: pl.DataFrame):
    calls: list[tuple[str, int]] = []

    def fake_fetch(dataset: str, season: int) -> pl.DataFrame:
        calls.append((dataset, season))
        return pbp_sample

    monkeypatch.setattr(data, "_fetch", fake_fetch)
    return calls


def test_load_pbp_caches_per_season(tmp_path, fetch_calls, pbp_sample):
    out = data.load_pbp([2023], cache_dir=tmp_path)
    assert fetch_calls == [("pbp", 2023)]
    assert (tmp_path / "pbp_2023.parquet").exists()
    assert out.equals(pbp_sample)

    # second call served from the parquet cache, no refetch
    cached = data.load_pbp([2023], cache_dir=tmp_path)
    assert fetch_calls == [("pbp", 2023)]
    assert cached.equals(out)


def test_load_pbp_refresh_refetches(tmp_path, fetch_calls):
    data.load_pbp([2023], cache_dir=tmp_path)
    data.load_pbp([2023], cache_dir=tmp_path, refresh=True)
    assert fetch_calls == [("pbp", 2023), ("pbp", 2023)]


def test_load_schedule_caches(tmp_path, monkeypatch, schedule_sample):
    calls: list[tuple[str, int]] = []

    def fake_fetch(dataset: str, season: int) -> pl.DataFrame:
        calls.append((dataset, season))
        return schedule_sample

    monkeypatch.setattr(data, "_fetch", fake_fetch)
    out = data.load_schedule([2023], cache_dir=tmp_path)
    data.load_schedule([2023], cache_dir=tmp_path)
    assert calls == [("schedule", 2023)]
    assert (tmp_path / "schedule_2023.parquet").exists()
    assert out.equals(schedule_sample)


def test_unknown_dataset_raises():
    with pytest.raises(ValueError, match="unknown dataset"):
        data._fetch("nope", 2023)


def test_load_injuries_handles_schema_drift(tmp_path, monkeypatch):
    """2024 has date_modified/game_type, no season_type; 2025 has
    season_type/game_type, no date_modified (#42)."""
    injuries_2024 = pl.DataFrame(
        {
            "season": [2024],
            "game_type": ["REG"],
            "team": ["KC"],
            "week": [1],
            "gsis_id": ["00-1"],
            "date_modified": ["2024-09-01"],
        }
    )
    injuries_2025 = pl.DataFrame(
        {
            "season": [2025],
            "season_type": ["REG"],
            "game_type": ["REG"],
            "team": ["BUF"],
            "week": [1],
            "gsis_id": ["00-2"],
        }
    )
    samples = {2024: injuries_2024, 2025: injuries_2025}

    def fake_fetch(dataset: str, season: int) -> pl.DataFrame:
        return samples[season]

    monkeypatch.setattr(data, "_fetch", fake_fetch)

    out = data.load_injuries([2024, 2025], cache_dir=tmp_path)
    assert out.height == 2
    assert out["game_type"].null_count() == 0
    assert set(out["game_type"].unique().to_list()) == {"REG"}
