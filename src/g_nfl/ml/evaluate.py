"""Walk-forward backtest and betting metrics (ATS accuracy, ROI at
-110, edge-threshold sweep).

Replaces the notebooks' random ``train_test_split``, which leaked
adjacent weeks through rolling features and made ATS accuracy look
optimistically good. Here each (season, week) is predicted by a model
trained only on games strictly before it, so every number is
out-of-sample in time.

Run via ``make backtest`` or directly:

    uv run python -m g_nfl.ml.evaluate --seasons 2022 2023 --output report.md

Conventions (nflverse schedule):
- ``result`` = home score - away score (the home margin the model predicts)
- ``spread_line`` = market's home margin (positive = home favored)
- edge = predicted margin - spread_line: bet home when positive, away
  when negative; a side covers when the actual margin lands on its side
  of the spread, equal is a push
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from g_nfl.ml.data import (
    DEFAULT_CACHE_DIR,
    load_injuries,
    load_pbp,
    load_players,
    load_schedule,
    load_snap_counts,
)
from g_nfl.ml.features import build_features
from g_nfl.ml.features.qb_change import apply_qb_adjustment
from g_nfl.ml.features.registry import get_feature_set
from g_nfl.ml.features.windows import DEFAULT_ROLLING_WEEKS
from g_nfl.ml.models.spread import DEFAULT_PARAMS, SpreadModel
from g_nfl.ml.train import (
    DEFAULT_MIN_WEEK,
    DEFAULT_SEASONS,
    load_params_config,
)

# at -110 a winning 1-unit bet profits 100/110
WIN_PROFIT = 100 / 110
# win rate needed to break even at -110: 110 / 210
BREAK_EVEN = 110 / 210

# skip walk-forward folds with fewer training games than this; early
# weeks of the first loaded season have nothing to train on
DEFAULT_MIN_TRAIN_GAMES = 200
# ml_odds margin-distribution reference: deep, strictly-prior schedule pull
# (REG results) so the implied-spread conversion is calibrated on a large,
# leak-free sample. ponytail: 2006 cutoff dodges the worst pre-OT-reform
# regime drift; widen if the PMF ever looks sample-starved.
MARGIN_REF_START = 2006
# notebook swept the pick cutoff k over 1..20; 0 = bet every game
DEFAULT_EDGE_THRESHOLDS = tuple(range(0, 21))
# report performance of each week's n most confident picks, n = 1..5
DEFAULT_TOP_N = 5


def walk_forward_predictions(
    matrix: pl.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any] | None = None,
    *,
    min_train_games: int = DEFAULT_MIN_TRAIN_GAMES,
) -> pl.DataFrame:
    """Predict each (season, week) using only strictly earlier games.

    `matrix` must have completed games (non-null ``result``). For each
    fold, training data is every game in an earlier season or an
    earlier week of the same season — never the evaluation week itself
    or anything after it. Returns the meta columns plus ``pred`` and
    ``n_train`` for every game in folds that met `min_train_games`.
    """
    matrix = matrix.sort("season", "week")
    folds = matrix.select("season", "week").unique().sort("season", "week")

    out: list[pl.DataFrame] = []
    for season, week in folds.iter_rows():
        before = (pl.col("season") < season) | (
            (pl.col("season") == season) & (pl.col("week") < week)
        )
        train_df = matrix.filter(before)
        if train_df.height < min_train_games:
            continue
        test_df = matrix.filter((pl.col("season") == season) & (pl.col("week") == week))

        model = SpreadModel(params)
        model.fit(
            train_df.select(feature_cols).to_numpy(),
            train_df["result"].to_numpy(),
        )
        preds = model.predict(test_df.select(feature_cols).to_numpy())
        out.append(
            test_df.drop(feature_cols).with_columns(
                pred=pl.Series(preds, dtype=pl.Float64),
                n_train=pl.lit(train_df.height),
            )
        )

    if not out:
        raise ValueError(
            f"no folds had >= {min_train_games} training games; "
            "lower --min-train-games or load more seasons"
        )
    return pl.concat(out)


def regression_metrics(preds: pl.DataFrame) -> dict[str, float]:
    """RMSE/MAE of predicted vs actual home margin, plus the market's
    own RMSE as the bar to clear."""
    err = (preds["pred"] - preds["result"]).to_numpy()
    market_err = (preds["spread_line"] - preds["result"]).to_numpy()
    return {
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "market_rmse": float(np.sqrt(np.mean(market_err**2))),
    }


def _sharpness_row(df: pl.DataFrame) -> dict[str, Any]:
    """Sharpness numbers for one slice of predictions (pooled or one season).

    Same market-implied-margin convention as ``regression_metrics``:
    ``spread_line`` is the market's home-margin prediction directly, no sign
    flip (see module docstring).
    """
    err = (df["pred"] - df["result"]).to_numpy()
    market_err = (df["spread_line"] - df["result"]).to_numpy()
    close_err = (df["pred"] - df["spread_line"]).to_numpy()
    rmse_model = float(np.sqrt(np.mean(err**2)))
    rmse_market = float(np.sqrt(np.mean(market_err**2)))
    abs_close_err = np.abs(close_err)
    return {
        "n_games": df.height,
        "rmse_model": rmse_model,
        "mae_model": float(np.mean(np.abs(err))),
        "rmse_market": rmse_market,
        "mae_market": float(np.mean(np.abs(market_err))),
        "gap_rmse": rmse_model - rmse_market,
        "mae_vs_close": float(np.mean(abs_close_err)),
        "rmse_vs_close": float(np.sqrt(np.mean(close_err**2))),
        "tail_gt3_pct": float(np.mean(abs_close_err > 3)),
        "tail_gt7_pct": float(np.mean(abs_close_err > 7)),
    }


def sharpness_metrics(preds: pl.DataFrame) -> pl.DataFrame:
    """Model sharpness vs the market close: pooled row (``season == "all"``)
    plus one row per season.

    ``gap_rmse`` (model RMSE − market RMSE vs actual margin) is the headline
    number per the sharpness gate (notes/sharpness-player-availability.md):
    the model no longer needs to beat the close, it needs to approach it.
    ``mae_vs_close``/``rmse_vs_close`` and the disagreement tails
    (``tail_gt3_pct``/``tail_gt7_pct``) measure line tracking directly.
    """
    seasons = sorted(preds["season"].unique().to_list())
    rows = [{"season": "all", **_sharpness_row(preds)}]
    for season in seasons:
        rows.append(
            {
                "season": str(season),
                **_sharpness_row(preds.filter(pl.col("season") == season)),
            }
        )
    return pl.DataFrame(rows)


def _score_picks(preds: pl.DataFrame) -> pl.DataFrame:
    """Add edge / push / win columns; drop edge == 0 (no side to bet)."""
    return (
        preds.with_columns(
            edge=pl.col("pred") - pl.col("spread_line"),
            home_margin_vs_spread=pl.col("result") - pl.col("spread_line"),
        )
        .with_columns(
            push=pl.col("home_margin_vs_spread") == 0,
            # bet home when edge > 0, away when edge < 0; win when the
            # actual margin lands on the same side of the spread
            win=(pl.col("edge") * pl.col("home_margin_vs_spread")) > 0,
        )
        .filter(pl.col("edge") != 0)
    )


def _record_row(bets: pl.DataFrame) -> dict[str, Any]:
    """W/L/P, ATS% and ROI for a set of bets. Pushes return the stake:
    excluded from ATS%, counted as 0 profit in ROI."""
    wins = bets.filter(pl.col("win") & ~pl.col("push")).height
    pushes = bets.filter(pl.col("push")).height
    losses = bets.height - wins - pushes
    decided = wins + losses
    profit = wins * WIN_PROFIT - losses
    return {
        "n_bets": bets.height,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "ats_pct": wins / decided if decided else None,
        "vs_break_even": wins / decided - BREAK_EVEN if decided else None,
        "roi": profit / bets.height if bets.height else None,
    }


def betting_metrics(
    preds: pl.DataFrame,
    edge_thresholds: tuple[int, ...] = DEFAULT_EDGE_THRESHOLDS,
) -> pl.DataFrame:
    """ATS record and ROI per edge threshold: bet every game where
    |pred - spread_line| >= threshold. ROI is profit per unit staked
    at -110."""
    scored = _score_picks(preds)
    return pl.DataFrame(
        [
            {
                "edge_threshold": k,
                **_record_row(scored.filter(pl.col("edge").abs() >= k)),
            }
            for k in edge_thresholds
        ]
    )


def top_n_metrics(preds: pl.DataFrame, max_n: int = DEFAULT_TOP_N) -> pl.DataFrame:
    """ATS record and ROI betting only each week's n highest-confidence
    picks (largest |pred - spread_line|), for n = 1..max_n.

    Mirrors how the picks are actually played: a fixed number of bets
    per week rather than a fixed edge cutoff.
    """
    ranked = _score_picks(preds).with_columns(
        confidence_rank=pl.col("edge")
        .abs()
        .rank("ordinal", descending=True)
        .over("season", "week")
    )
    return pl.DataFrame(
        [
            {
                "top_n": n,
                **_record_row(ranked.filter(pl.col("confidence_rank") <= n)),
            }
            for n in range(1, max_n + 1)
        ]
    )


def _record_cells(r: dict[str, Any]) -> str:
    """`W-L-P | ATS% | vs break-even | ROI` markdown cells for a record row."""
    ats = f"{r['ats_pct']:.1%}" if r["ats_pct"] is not None else "-"
    vbe = f"{r['vs_break_even']:+.1%}" if r["vs_break_even"] is not None else "-"
    roi = f"{r['roi']:+.1%}" if r["roi"] is not None else "-"
    return f"{r['wins']}-{r['losses']}-{r['pushes']} | {ats} | {vbe} | {roi} |"


def _sharpness_row_cells(r: dict[str, Any]) -> str:
    """`RMSE gap | MAE/RMSE vs close | tail>3 | tail>7` markdown cells for a
    sharpness row."""
    return (
        f"{r['rmse_model']:.2f} | {r['rmse_market']:.2f} | {r['gap_rmse']:+.2f} | "
        f"{r['mae_vs_close']:.2f} | {r['rmse_vs_close']:.2f} | "
        f"{r['tail_gt3_pct']:.1%} | {r['tail_gt7_pct']:.1%} |"
    )


def format_report(
    preds: pl.DataFrame,
    sweep: pl.DataFrame,
    top_n: pl.DataFrame,
    reg: dict[str, float],
    sharpness: pl.DataFrame,
    config: dict[str, Any],
) -> str:
    """Markdown backtest summary."""
    seasons = sorted(preds["season"].unique().to_list())
    lines = [
        "# Spread model walk-forward backtest",
        "",
        f"- generated: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        f"- evaluated seasons: {seasons} ({preds.height} games, "
        f"{preds.select('season', 'week').unique().height} weekly folds)",
        *[f"- {k}: {v}" for k, v in config.items()],
        "",
        "## Margin regression",
        "",
        f"- model RMSE: {reg['rmse']:.2f} | MAE: {reg['mae']:.2f}",
        f"- market (spread_line) RMSE: {reg['market_rmse']:.2f} "
        "<- model must approach this to find value",
        "",
        "## Sharpness (vs market close)",
        "",
        "Gate: model no longer needs to beat the close, it needs to approach "
        "it. `gap_rmse` = model RMSE − market RMSE vs actual margin "
        "(negative = model sharper). `vs close` columns track the model line "
        "against the market line directly; tails are the share of games with "
        "|model − close| over 3 / 7 points.",
        "",
        "| season | n | RMSE model | RMSE market | gap | MAE vs close | "
        "RMSE vs close | tail>3 | tail>7 |",
        "|-------:|--:|-----------:|------------:|----:|-------------:|"
        "--------------:|-------:|-------:|",
    ]
    for r in sharpness.iter_rows(named=True):
        lines.append(f"| {r['season']} | {r['n_games']} | {_sharpness_row_cells(r)}")
    lines += [
        "",
        "## Betting (1 unit at -110)",
        "",
        f"Break-even ATS%: {BREAK_EVEN:.2%}. Bet when |model - market| >= k.",
        "",
        "| k | bets | W-L-P | ATS% | vs break-even | ROI |",
        "|--:|-----:|------:|-----:|--------------:|----:|",
    ]
    for r in sweep.iter_rows(named=True):
        lines.append(f"| {r['edge_threshold']} | {r['n_bets']} | {_record_cells(r)}")
    lines += [
        "",
        "## Top-n confidence picks per week",
        "",
        "Each week, bet only the n games with the largest |model - market|.",
        "",
        "| n/week | bets | W-L-P | ATS% | vs break-even | ROI |",
        "|-------:|-----:|------:|-----:|--------------:|----:|",
    ]
    for r in top_n.iter_rows(named=True):
        lines.append(f"| {r['top_n']} | {r['n_bets']} | {_record_cells(r)}")
    return "\n".join(lines) + "\n"


def backtest(
    seasons: list[int],
    feature_set: str = "v1_team",
    params: dict[str, Any] | None = None,
    *,
    min_week: int = DEFAULT_MIN_WEEK,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
    min_train_games: int = DEFAULT_MIN_TRAIN_GAMES,
    edge_thresholds: tuple[int, ...] = DEFAULT_EDGE_THRESHOLDS,
    half_life: float | None = None,
    epa_splits: bool = False,
    carryover_k: float | None = None,
    with_injuries: bool = False,
    schedule_ctx: bool = False,
    qb_ctx: bool = False,
    qb_history: int = 3,
    qb_change: bool = False,
    qb_adjust_k: float | None = None,
    continuity: bool = False,
    ml_odds: bool = False,
    availability: bool = False,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> tuple[pl.DataFrame, str]:
    """Full backtest: load data, walk forward, score; returns the
    per-game predictions and the markdown report.

    ``qb_ctx``/``qb_change`` load ``qb_history`` extra contiguous seasons of
    pbp before the earliest eval season to warm the per-QB EWMA; the matrix
    rows stay eval-season only (schedule is loaded for ``seasons`` alone), so
    the training set is identical to the baseline — a clean A/B.

    ``qb_adjust_k`` applies the explicit additive QB-change correction
    (`features.qb_change.apply_qb_adjustment`) to the walk-forward
    predictions before any metric is computed, so sharpness/betting/top-n
    all see the adjusted line. Requires ``qb_change=True``.
    """
    if qb_adjust_k is not None and not qb_change:
        raise ValueError("qb_adjust_k requires qb_change=True")
    pbp_seasons = (
        list(range(min(seasons) - qb_history, max(seasons) + 1))
        if (qb_ctx or qb_change)
        else seasons
    )
    pbp = load_pbp(pbp_seasons, cache_dir=cache_dir, refresh=refresh)
    schedule = load_schedule(seasons, cache_dir=cache_dir, refresh=refresh)
    injuries = (
        load_injuries(seasons, cache_dir=cache_dir, refresh=refresh)
        if (with_injuries or qb_change or availability)
        else None
    )
    snaps = (
        load_snap_counts(seasons, cache_dir=cache_dir, refresh=refresh)
        if (continuity or availability)
        else None
    )
    players = (
        load_players(cache_dir=cache_dir, refresh=refresh) if availability else None
    )
    ml_margins = None
    if ml_odds:
        ref_seasons = list(range(MARGIN_REF_START, min(seasons)))
        if ref_seasons:
            ref = load_schedule(ref_seasons, cache_dir=cache_dir, refresh=refresh)
            ml_margins = (
                ref.filter(
                    (pl.col("game_type") == "REG") & pl.col("result").is_not_null()
                )["result"]
                .to_numpy()
                .astype(float)
            )
    matrix = build_features(
        pbp,
        schedule,
        rolling_weeks=rolling_weeks,
        min_week=min_week,
        half_life=half_life,
        epa_splits=epa_splits,
        carryover_k=carryover_k,
        injuries=injuries if with_injuries else None,
        schedule_ctx=schedule_ctx,
        qb_ctx=qb_ctx,
        qb_change=injuries if qb_change else None,
        snaps=snaps,
        continuity=continuity,
        ml_odds=ml_odds,
        ml_margins=ml_margins,
        availability=injuries if availability else None,
        players=players,
    ).filter(pl.col("result").is_not_null())

    fs = get_feature_set(feature_set)
    preds = walk_forward_predictions(
        matrix, fs.columns(matrix), params, min_train_games=min_train_games
    )
    if qb_adjust_k is not None:
        downgrades = matrix.select("game_id", "home_qb_downgrade", "away_qb_downgrade")
        preds = apply_qb_adjustment(
            preds.join(downgrades, on="game_id", how="left"), qb_adjust_k
        ).drop("home_qb_downgrade", "away_qb_downgrade")
    report = format_report(
        preds,
        betting_metrics(preds, edge_thresholds),
        top_n_metrics(preds),
        regression_metrics(preds),
        sharpness_metrics(preds),
        config={
            "feature_set": fs.name,
            "seasons_loaded": list(seasons),
            "min_week": min_week,
            "rolling_weeks": rolling_weeks,
            "min_train_games": min_train_games,
            "half_life": half_life,
            "epa_splits": epa_splits,
            "carryover_k": carryover_k,
            "with_injuries": with_injuries,
            "schedule_ctx": schedule_ctx,
            "qb_ctx": qb_ctx,
            "qb_change": qb_change,
            "qb_adjust_k": qb_adjust_k,
            "continuity": continuity,
            "ml_odds": ml_odds,
            "availability": availability,
        },
    )
    return preds, report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Walk-forward backtest")
    parser.add_argument("--seasons", type=int, nargs="+", default=DEFAULT_SEASONS)
    parser.add_argument("--feature-set", default="v1_team")
    parser.add_argument(
        "--config", type=Path, help="yaml/json file with hyperparameter overrides"
    )
    parser.add_argument("--min-week", type=int, default=DEFAULT_MIN_WEEK)
    parser.add_argument("--rolling-weeks", type=int, default=DEFAULT_ROLLING_WEEKS)
    parser.add_argument("--min-train-games", type=int, default=DEFAULT_MIN_TRAIN_GAMES)
    parser.add_argument(
        "--half-life",
        type=float,
        default=None,
        help="L2 time decay half-life in games (omit = L1 flat windows)",
    )
    parser.add_argument(
        "--epa-splits",
        action="store_true",
        help="add L2 pass/rush/early-down EPA features",
    )
    parser.add_argument(
        "--carryover-k",
        type=float,
        default=None,
        help="L2 prior-season carryover, pseudo-games of prior (omit = off)",
    )
    parser.add_argument(
        "--injuries",
        action="store_true",
        help="L3 team-week injury burden features (no lag)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="L3 schedule context: rest, short-week/off-bye, day, division",
    )
    parser.add_argument(
        "--qb",
        action="store_true",
        help="L4 starting-QB player-grain features (lagged EWMA + volume)",
    )
    parser.add_argument(
        "--qb-change",
        action="store_true",
        help="L4 QB-change delta triggered by the injury report (Out/Doubtful)",
    )
    parser.add_argument(
        "--qb-adjust-k",
        type=float,
        default=None,
        help="L4 explicit additive QB-change correction on pred (requires --qb-change)",
    )
    parser.add_argument(
        "--continuity",
        action="store_true",
        help="L4 O-line continuity index (lagged season-to-date lineup stability)",
    )
    parser.add_argument(
        "--ml-odds",
        action="store_true",
        help="L4 moneyline-implied spread + divergence from posted line",
    )
    parser.add_argument(
        "--availability",
        action="store_true",
        help=(
            "L4 availability-weighted unit snap-value lost (#39 lever 2), "
            "by OL/skill/front-7/secondary"
        ),
    )
    parser.add_argument(
        "--output", type=Path, help="also write the markdown report to this path"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="refetch source data, ignore cache"
    )
    parser.add_argument(
        "--no-mlflow", action="store_true", help="skip MLflow logging (offline/CI)"
    )
    args = parser.parse_args(argv)

    params = load_params_config(args.config) if args.config else None
    preds, report = backtest(
        args.seasons,
        args.feature_set,
        params,
        min_week=args.min_week,
        rolling_weeks=args.rolling_weeks,
        min_train_games=args.min_train_games,
        half_life=args.half_life,
        epa_splits=args.epa_splits,
        carryover_k=args.carryover_k,
        with_injuries=args.injuries,
        schedule_ctx=args.schedule,
        qb_ctx=args.qb,
        qb_change=args.qb_change,
        qb_adjust_k=args.qb_adjust_k,
        continuity=args.continuity,
        ml_odds=args.ml_odds,
        availability=args.availability,
        refresh=args.refresh,
    )
    print(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"report written to {args.output}")

    if not args.no_mlflow:
        import mlflow

        from g_nfl.ml.tracking import setup_mlflow

        # ponytail: per-fold nested runs skipped — we compare model versions,
        # not weekly folds; add nested runs if per-fold drilldown is ever needed
        setup_mlflow()
        run_name = f"backtest-{datetime.now(UTC):%Y%m%d-%H%M%S}"
        resolved_params = params if params is not None else DEFAULT_PARAMS
        with mlflow.start_run(run_name=run_name):
            mlflow.log_params(
                {
                    "run_type": "backtest",
                    "feature_set": args.feature_set,
                    "seasons": str(args.seasons),
                    "min_week": args.min_week,
                    "rolling_weeks": args.rolling_weeks,
                    "min_train_games": args.min_train_games,
                    "half_life": args.half_life,
                    "epa_splits": args.epa_splits,
                    "carryover_k": args.carryover_k,
                    "with_injuries": args.injuries,
                    "schedule_ctx": args.schedule,
                    "qb_ctx": args.qb,
                    "qb_change": args.qb_change,
                    "qb_adjust_k": args.qb_adjust_k,
                    "continuity": args.continuity,
                    "ml_odds": args.ml_odds,
                    "availability": args.availability,
                    **resolved_params,
                }
            )
            reg = regression_metrics(preds)
            mlflow.log_metrics(
                {
                    "rmse": reg["rmse"],
                    "mae": reg["mae"],
                    "market_rmse": reg["market_rmse"],
                }
            )
            sharp = (
                sharpness_metrics(preds)
                .filter(pl.col("season") == "all")
                .row(0, named=True)
            )
            mlflow.log_metrics(
                {
                    "gap_rmse": sharp["gap_rmse"],
                    "mae_vs_close": sharp["mae_vs_close"],
                    "rmse_vs_close": sharp["rmse_vs_close"],
                    "tail_gt3_pct": sharp["tail_gt3_pct"],
                    "tail_gt7_pct": sharp["tail_gt7_pct"],
                }
            )
            bm = betting_metrics(preds)
            bettable = bm.filter((pl.col("n_bets") > 0) & pl.col("roi").is_not_null())
            if bettable.height > 0:
                best = bettable.sort("roi", descending=True).row(0, named=True)
                mlflow.log_metrics(
                    {
                        "best_roi": best["roi"],
                        "best_roi_edge_k": best["edge_threshold"],
                        "best_roi_ats_pct": best["ats_pct"],
                    }
                )
            bet_all_rows = bm.filter(pl.col("edge_threshold") == 0)
            if bet_all_rows.height > 0:
                bet_all = bet_all_rows.row(0, named=True)
                if bet_all["ats_pct"] is not None:
                    mlflow.log_metric("bet_all_ats_pct", bet_all["ats_pct"])
                if bet_all["roi"] is not None:
                    mlflow.log_metric("bet_all_roi", bet_all["roi"])
            tn = top_n_metrics(preds)
            for n in [1, 3, 5]:
                row = tn.filter(pl.col("top_n") == n).row(0, named=True)
                if row["ats_pct"] is not None:
                    mlflow.log_metric(f"top{n}_ats_pct", row["ats_pct"])
                if row["roi"] is not None:
                    mlflow.log_metric(f"top{n}_roi", row["roi"])
            mlflow.log_text(report, "report.md")


if __name__ == "__main__":
    main()
