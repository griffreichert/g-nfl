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
| 2026-06-29 | e8e9675 | v1_team | 1103 | 51.2% | −2.3% | 43.7% | 13.66 | 12.36 | **L2 baseline (#22).** L0 `max_depth=3` — the only config where full-set + top-5 ATS move together (the rest of L2 is the anti-signal trap). All 3 same-data FE levers (time decay, EPA splits, prior-season carryover) tested + REJECTED: reshaping rate features can't add signal the team base lacks → L2 ceiling. Reproduce: append `--config max_depth=3`. Next edge must come from L3 external data (schedule/rest/injury). |
| 2026-07-05 | 1834856 | v1_team | 448 | 48.6% | — | — | 12.99 | 12.18 | **Close-target baseline (#39).** `--target spread_line --config max_depth=3`, one-shot 2024/25 holdout. Gate is now sharpness: gap_rmse +0.81 (vs +1.36 result-trained), MAE-vs-close 2.83, tail>7 5.6% (vs 17.2%) — and better at actual margins too (12.99 < 13.53; close = denoised label). Per-season stable (+1.01/+0.62). Confirmed a-priori tune result, low selection risk. QB additive adjustment (k=10) inconclusive at holdout (subset n=8, 2025 blocked by injuries schema); keep as option, judge live. |
