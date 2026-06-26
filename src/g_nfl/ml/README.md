# ML validation-loop workflow

Every `make backtest` and `make train` run is logged to a local MLflow experiment
(`spread-model`) backed by `mlflow.db` at the repo root. Both files are gitignored
and local-only.

## Step-by-step

1. **Make a model change** — tweak a feature set, hyperparams, or rolling window.

2. **Run a backtest** — logs a run with all params + metrics automatically:
   ```bash
   make backtest ARGS="--seasons 2022 2023 2024"
   ```

3. **Compare runs in the UI:**
   ```bash
   make mlflow-ui   # opens http://localhost:5000
   ```
   Filter by the `spread-model` experiment; sort by `rmse` or `best_roi` to find
   the winner.

4. **When a model beats the incumbent, train and register it:**
   ```bash
   make train ARGS="--seasons 2022 2023 2024"
   ```
   This logs the run and registers the booster under the `spread_model` name in
   the MLflow Model Registry.

5. **Promote to `prod` alias** — pick the version number from the UI, then run:
   ```python
   from mlflow.tracking import MlflowClient
   MlflowClient().set_registered_model_alias("spread_model", "prod", <version>)
   ```
   Or via the CLI:
   ```bash
   uv run mlflow models set-alias --name spread_model --alias prod --model-version <version>
   ```

## Notes

- `mlflow.db` and `mlruns/` are gitignored — experiment history is local only.
- MLflow lives in the `analysis` dep group and is never installed on Render.
- Pass `--no-mlflow` to either command to skip logging (offline / CI use).
- `reports/BASELINES.md` is still the single tracked file for milestone benchmarks;
  MLflow is for the full experiment log.
