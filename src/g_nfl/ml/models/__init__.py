"""Model wrappers (spread: XGBoost regressor on home margin,
hyperparameters supplied via config)."""

from g_nfl.ml.models.spread import SpreadModel, load_artifact, save_artifact

__all__ = ["SpreadModel", "load_artifact", "save_artifact"]
