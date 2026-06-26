# Model baselines

The numbers to beat. Append a row only when a model becomes the new
benchmark — not for every experiment (full run history goes to MLflow,
#12). All rows are walk-forward backtests (`make backtest`); regenerate
any row's full report by checking out its SHA:

```bash
git checkout <sha> && make backtest ARGS="--seasons 2018 2019 2022 2023 2024 2025"
```

Note: re-runs may drift slightly — nflverse data can be restated and
in-progress seasons grow. The row records what was measured at the time.

| date | sha | feature set | games | ATS% (all) | ROI (all) | top-1/wk ATS% | model RMSE | market RMSE | notes |
|------|-----|-------------|------:|-----------:|----------:|--------------:|-----------:|------------:|-------|
| 2026-06-11 | 9d28393 | v1_team | 1103 | 50.0% | −4.5% | 42.9% | 13.71 | 12.36 | First honest baseline (default xgb params, 2019+2022–25 evaluated). Confidence is anti-signal: biggest market disagreements are the worst picks — market likely pricing injuries/QB news the features can't see. |
