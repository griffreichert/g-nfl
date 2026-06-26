"""Central MLflow configuration for g-nfl ML experiments.

Backend: local SQLite at repo root (mlflow.db).
Artifacts: ./mlruns/ (default local artifact root).
Both are gitignored and local-only; this module is only reachable from
the ``analysis`` dep group so it never ships to the Render deploy.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parents[3]
TRACKING_URI = f"sqlite:///{REPO_ROOT / 'mlflow.db'}"
EXPERIMENT = "spread-model"
REGISTERED_MODEL = "spread_model"


def setup_mlflow(experiment: str = EXPERIMENT) -> None:
    """Set tracking URI and active experiment (idempotent)."""
    import mlflow

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(experiment)
