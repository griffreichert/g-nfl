"""Wiring tests for the g_nfl.ml scaffold and test fixtures (#8)."""

import polars as pl


def test_ml_package_imports():
    from g_nfl.ml import data, evaluate, features, models, predict, train  # noqa: F401


def test_pbp_fixture(pbp_sample: pl.DataFrame):
    expected_cols = {
        "game_id",
        "season",
        "week",
        "posteam",
        "defteam",
        "play_type",
        "epa",
        "wp",
        "cpoe",
        "pass_oe",
        "success",
    }
    assert expected_cols <= set(pbp_sample.columns)
    assert pbp_sample["game_id"].n_unique() == 10
    assert pbp_sample["season"].unique().to_list() == [2023]
    assert pbp_sample["week"].max() <= 5


def test_schedule_fixture(pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame):
    expected_cols = {
        "game_id",
        "season",
        "week",
        "home_team",
        "away_team",
        "spread_line",
        "result",
    }
    assert expected_cols <= set(schedule_sample.columns)
    # schedule and pbp fixtures cover the same games
    assert set(schedule_sample["game_id"]) == set(pbp_sample["game_id"])
