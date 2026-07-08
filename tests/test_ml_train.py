"""Tests for the training pipeline (#10): config loading, training on the
fixture data, and artifact persistence round-trips."""

import json

import numpy as np
import polars as pl
import pytest

from g_nfl.ml import train as train_mod
from g_nfl.ml.features import build_features
from g_nfl.ml.models.spread import (
    DEFAULT_PARAMS,
    SpreadModel,
    load_artifact,
    save_artifact,
)

# tiny model so fixture-sized training stays fast
SMALL_PARAMS = {"n_estimators": 10, "max_depth": 2}


@pytest.fixture
def stub_loaders(monkeypatch, pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame):
    monkeypatch.setattr(train_mod, "load_pbp", lambda seasons, **kw: pbp_sample)
    monkeypatch.setattr(
        train_mod, "load_schedule", lambda seasons, **kw: schedule_sample
    )


def test_spread_model_params_merge_over_defaults():
    model = SpreadModel(SMALL_PARAMS)
    assert model.params["n_estimators"] == 10
    assert model.params["learning_rate"] == DEFAULT_PARAMS["learning_rate"]


def test_load_params_config(tmp_path):
    cfg = tmp_path / "params.yaml"
    cfg.write_text("n_estimators: 25\nmax_depth: 3\n")
    params = train_mod.load_params_config(cfg)
    assert params["n_estimators"] == 25
    assert params["max_depth"] == 3
    assert params["subsample"] == DEFAULT_PARAMS["subsample"]


def test_artifact_round_trip(tmp_path):
    rng = np.random.default_rng(0)
    X, y = rng.normal(size=(40, 3)), rng.normal(size=40)
    model = SpreadModel(SMALL_PARAMS).fit(X, y)

    artifact_dir = save_artifact(model, {"params": model.params}, tmp_path / "m")
    loaded, metadata = load_artifact(artifact_dir)

    assert metadata["params"]["n_estimators"] == 10
    np.testing.assert_allclose(loaded.predict(X), model.predict(X))


def test_train_produces_loadable_model(
    tmp_path, stub_loaders, pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    artifact_dir = train_mod.train([2023], params=SMALL_PARAMS, output_dir=tmp_path)
    assert artifact_dir.parent == tmp_path

    metadata = json.loads((artifact_dir / "metadata.json").read_text())
    assert metadata["feature_set"] == "v1_team"
    assert metadata["seasons"] == [2023]
    assert metadata["params"]["n_estimators"] == 10
    assert metadata["min_week"] == train_mod.DEFAULT_MIN_WEEK
    # champion config (#39/#47) rides the defaults into the artifact
    assert metadata["target"] == "spread_line"
    assert metadata["carryover_k"] == train_mod.DEFAULT_CARRYOVER_K
    # fixture has results for all games, so n_games = games from min_week on
    expected_games = schedule_sample.filter(
        pl.col("week") >= train_mod.DEFAULT_MIN_WEEK
    ).height
    assert metadata["n_games"] == expected_games

    model, meta = load_artifact(artifact_dir)
    matrix = build_features(
        pbp_sample,
        schedule_sample,
        min_week=train_mod.DEFAULT_MIN_WEEK,
        carryover_k=meta["carryover_k"],
    )
    preds = model.predict(matrix.select(meta["feature_cols"]).to_numpy())
    assert preds.shape == (matrix.height,)
    assert np.isfinite(preds).all()


def test_cli_main(tmp_path, stub_loaders, capsys):
    cfg = tmp_path / "params.yaml"
    cfg.write_text("n_estimators: 5\nmax_depth: 2\n")
    train_mod.main(
        [
            "--seasons",
            "2023",
            "--output-dir",
            str(tmp_path / "models"),
            "--config",
            str(cfg),
        ]
    )
    artifacts = list((tmp_path / "models").iterdir())
    assert len(artifacts) == 1
    metadata = json.loads((artifacts[0] / "metadata.json").read_text())
    assert metadata["params"]["n_estimators"] == 5
    assert str(artifacts[0]) in capsys.readouterr().out
