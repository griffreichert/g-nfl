"""Training entrypoint: build the game matrix, train, persist the model.

Run via ``make train`` or directly:

    uv run python -m g_nfl.ml.train --seasons 2022 2023 --config configs/spread_params.yaml

MLflow tracking arrives in #12; walk-forward evaluation in #11.
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from g_nfl.ml.data import DEFAULT_CACHE_DIR, load_pbp, load_schedule
from g_nfl.ml.features import build_features
from g_nfl.ml.features.registry import get_feature_set
from g_nfl.ml.features.windows import DEFAULT_ROLLING_WEEKS
from g_nfl.ml.models.spread import DEFAULT_PARAMS, SpreadModel, save_artifact

# drop early-season games where windowed stats are still thin (notebook used 4)
DEFAULT_MIN_WEEK = 4
# notebook training seasons
DEFAULT_SEASONS = [2018, 2019, 2022, 2023, 2024, 2025]
DEFAULT_OUTPUT_DIR = Path(__file__).parents[3] / "data" / "ml_models"


def load_params_config(path: Path | str) -> dict[str, Any]:
    """Hyperparameter overrides from a yaml (or json) file, merged over
    DEFAULT_PARAMS."""
    with open(path) as f:
        overrides = yaml.safe_load(f) or {}
    return {**DEFAULT_PARAMS, **overrides}


def train(
    seasons: list[int],
    feature_set: str = "v1_team",
    params: dict[str, Any] | None = None,
    *,
    min_week: int = DEFAULT_MIN_WEEK,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> Path:
    """Train the spread model on completed games; returns the artifact dir."""
    pbp = load_pbp(seasons, cache_dir=cache_dir, refresh=refresh)
    schedule = load_schedule(seasons, cache_dir=cache_dir, refresh=refresh)

    matrix = build_features(
        pbp, schedule, rolling_weeks=rolling_weeks, min_week=min_week
    ).filter(pl.col("result").is_not_null())

    fs = get_feature_set(feature_set)
    feature_cols = fs.columns(matrix)
    X = matrix.select(feature_cols).to_numpy()
    y = matrix["result"].to_numpy()

    model = SpreadModel(params)
    model.fit(X, y)

    trained_at = datetime.now(UTC)
    metadata = {
        "model": "spread_xgb",
        "feature_set": fs.name,
        "feature_cols": feature_cols,
        "seasons": list(seasons),
        "params": model.params,
        "rolling_weeks": rolling_weeks,
        "min_week": min_week,
        "n_games": matrix.height,
        "trained_at": trained_at.isoformat(),
    }
    artifact_dir = Path(output_dir) / f"spread_{fs.name}_{trained_at:%Y%m%d_%H%M%S}"
    return save_artifact(model, metadata, artifact_dir)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train the spread model")
    parser.add_argument("--seasons", type=int, nargs="+", default=DEFAULT_SEASONS)
    parser.add_argument("--feature-set", default="v1_team")
    parser.add_argument(
        "--config", type=Path, help="yaml/json file with hyperparameter overrides"
    )
    parser.add_argument("--min-week", type=int, default=DEFAULT_MIN_WEEK)
    parser.add_argument("--rolling-weeks", type=int, default=DEFAULT_ROLLING_WEEKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--refresh", action="store_true", help="refetch source data, ignore cache"
    )
    args = parser.parse_args(argv)

    params = load_params_config(args.config) if args.config else None
    artifact_dir = train(
        args.seasons,
        args.feature_set,
        params,
        min_week=args.min_week,
        rolling_weeks=args.rolling_weeks,
        output_dir=args.output_dir,
        refresh=args.refresh,
    )
    print(f"saved model artifact to {artifact_dir}")


if __name__ == "__main__":
    main()
