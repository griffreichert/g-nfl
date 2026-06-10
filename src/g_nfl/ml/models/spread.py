"""XGBoost spread model: regresses home margin (schedule ``result``).

Hyperparameters come from a config dict merged over DEFAULT_PARAMS —
nothing tuned in code. Artifacts are a directory with the native
xgboost model file plus a metadata json; the save path is pluggable so
MLflow artifact logging (#12) can point it anywhere.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb

# notebook 01/02 hyperparameters
DEFAULT_PARAMS: dict[str, Any] = {
    "n_estimators": 500,
    "learning_rate": 0.05,
    "max_depth": 4,
    "min_child_weight": 3,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "colsample_bylevel": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
}

MODEL_FILENAME = "model.ubj"
METADATA_FILENAME = "metadata.json"


class SpreadModel:
    """Thin XGBRegressor wrapper with config-driven hyperparameters."""

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self._model = xgb.XGBRegressor(**self.params)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SpreadModel":
        self._model.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict(X)

    @property
    def feature_importances_(self) -> np.ndarray:
        return self._model.feature_importances_


def save_artifact(
    model: SpreadModel, metadata: dict[str, Any], artifact_dir: Path | str
) -> Path:
    """Write the model + metadata into ``artifact_dir``; returns the dir."""
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model._model.save_model(artifact_dir / MODEL_FILENAME)
    (artifact_dir / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2))
    return artifact_dir


def load_artifact(artifact_dir: Path | str) -> tuple[SpreadModel, dict[str, Any]]:
    """Load a saved model + its metadata from an artifact directory."""
    artifact_dir = Path(artifact_dir)
    metadata = json.loads((artifact_dir / METADATA_FILENAME).read_text())
    model = SpreadModel(metadata.get("params"))
    model._model.load_model(artifact_dir / MODEL_FILENAME)
    return model, metadata
