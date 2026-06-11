"""Tests for the walk-forward backtest (#11): temporal anti-leakage,
betting metric arithmetic, and the end-to-end report."""

import numpy as np
import polars as pl
import pytest

from g_nfl.ml import evaluate as eval_mod
from g_nfl.ml.features import build_features
from g_nfl.ml.features.registry import get_feature_set

# tiny model so fixture-sized training stays fast
SMALL_PARAMS = {"n_estimators": 10, "max_depth": 2}


@pytest.fixture(scope="module")
def fixture_matrix(pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame):
    # min_week=2 keeps weeks 2-5 of the fixture so several folds exist
    return build_features(pbp_sample, schedule_sample, min_week=2).filter(
        pl.col("result").is_not_null()
    )


@pytest.fixture(scope="module")
def feature_cols(fixture_matrix: pl.DataFrame) -> list[str]:
    return get_feature_set("v1_team").columns(fixture_matrix)


def test_walk_forward_trains_only_on_strictly_earlier_games(
    fixture_matrix, feature_cols
):
    preds = eval_mod.walk_forward_predictions(
        fixture_matrix, feature_cols, SMALL_PARAMS, min_train_games=1
    )
    # every fold's training size must equal the games strictly before it
    for season, week, n_train in (
        preds.select("season", "week", "n_train").unique().iter_rows()
    ):
        expected = fixture_matrix.filter(
            (pl.col("season") < season)
            | ((pl.col("season") == season) & (pl.col("week") < week))
        ).height
        assert n_train == expected
    # the earliest week has no prior games, so it can never be a fold
    first_week = fixture_matrix["week"].min()
    assert preds.filter(pl.col("week") == first_week).is_empty()


def test_walk_forward_predictions_immune_to_eval_week_results(
    fixture_matrix, feature_cols
):
    """Flipping the outcomes of an evaluation week must not move that
    week's predictions — the model never saw them."""
    week = 4
    preds = eval_mod.walk_forward_predictions(
        fixture_matrix, feature_cols, SMALL_PARAMS, min_train_games=1
    )
    perturbed = fixture_matrix.with_columns(
        pl.when(pl.col("week") == week)
        .then(pl.col("result") + 100)
        .otherwise(pl.col("result"))
        .alias("result")
    )
    preds_perturbed = eval_mod.walk_forward_predictions(
        perturbed, feature_cols, SMALL_PARAMS, min_train_games=1
    )
    np.testing.assert_allclose(
        preds.filter(pl.col("week") == week).sort("game_id")["pred"],
        preds_perturbed.filter(pl.col("week") == week).sort("game_id")["pred"],
    )


def test_walk_forward_orders_across_seasons(feature_cols):
    """A week-1 game of a later season trains on all of the earlier
    season, regardless of week numbers."""
    n = len(feature_cols)
    rng = np.random.default_rng(0)

    def fake_rows(season: int, weeks: list[int]) -> pl.DataFrame:
        base = pl.DataFrame(
            {
                "game_id": [f"{season}_{w:02d}" for w in weeks],
                "season": [season] * len(weeks),
                "week": weeks,
                "away_team": ["A"] * len(weeks),
                "home_team": ["B"] * len(weeks),
                "result": rng.normal(size=len(weeks)),
                "spread_line": rng.normal(size=len(weeks)),
            }
        )
        feats = pl.DataFrame(rng.normal(size=(len(weeks), n)), schema=feature_cols)
        return pl.concat([base, feats], how="horizontal")

    matrix = pl.concat([fake_rows(2022, list(range(1, 6))), fake_rows(2023, [1, 2])])
    preds = eval_mod.walk_forward_predictions(
        matrix, feature_cols, SMALL_PARAMS, min_train_games=1
    )
    fold_2023_w1 = preds.filter((pl.col("season") == 2023) & (pl.col("week") == 1))
    assert fold_2023_w1["n_train"][0] == 5  # all of 2022


def test_walk_forward_raises_when_no_fold_has_enough_data(fixture_matrix, feature_cols):
    with pytest.raises(ValueError, match="min-train-games"):
        eval_mod.walk_forward_predictions(
            fixture_matrix, feature_cols, SMALL_PARAMS, min_train_games=10_000
        )


def _preds_frame(rows: list[tuple[float, float, float]]) -> pl.DataFrame:
    """(pred, spread_line, result) rows with dummy meta columns."""
    return pl.DataFrame(
        {
            "season": [2023] * len(rows),
            "week": list(range(1, len(rows) + 1)),
            "pred": [r[0] for r in rows],
            "spread_line": [r[1] for r in rows],
            "result": [r[2] for r in rows],
        }
    )


def test_betting_metrics_sides_pushes_and_roi():
    preds = _preds_frame(
        [
            (3.0, 1.0, 5.0),  # edge +2, home covers -> win
            (3.0, 1.0, -4.0),  # edge +2, home fails -> loss
            (-6.0, -2.0, -7.0),  # edge -4, away covers -> win
            (-6.0, -2.0, 0.0),  # edge -4, home wins outright -> loss
            (4.0, 1.0, 1.0),  # edge +3, lands on spread -> push
            (2.0, 2.0, 9.0),  # edge 0 -> never bet
        ]
    )
    sweep = eval_mod.betting_metrics(preds, edge_thresholds=(0, 3))

    k0 = sweep.filter(pl.col("edge_threshold") == 0).row(0, named=True)
    assert (k0["n_bets"], k0["wins"], k0["losses"], k0["pushes"]) == (5, 2, 2, 1)
    assert k0["ats_pct"] == 0.5
    assert k0["vs_break_even"] == pytest.approx(0.5 - eval_mod.BREAK_EVEN)
    # 2 wins at +100/110, 2 losses, push stakes returned; 5 units staked
    assert k0["roi"] == pytest.approx((2 * 100 / 110 - 2) / 5)

    k3 = sweep.filter(pl.col("edge_threshold") == 3).row(0, named=True)
    assert (k3["n_bets"], k3["wins"], k3["losses"], k3["pushes"]) == (3, 1, 1, 1)


def test_betting_metrics_empty_threshold_bucket():
    preds = _preds_frame([(3.0, 1.0, 5.0)])
    sweep = eval_mod.betting_metrics(preds, edge_thresholds=(20,))
    row = sweep.row(0, named=True)
    assert row["n_bets"] == 0
    assert row["ats_pct"] is None and row["roi"] is None


def test_top_n_metrics_ranks_within_each_week():
    # two weeks; per-week confidence order differs from global order
    preds = pl.DataFrame(
        {
            "season": [2023] * 6,
            "week": [1, 1, 1, 2, 2, 2],
            #                    week 1            |        week 2
            # edges:    +5 (win), +2 (loss), -1 (win) | -8 (loss), +3 (win), +1 (push)
            "pred": [6.0, 3.0, -2.0, -10.0, 4.0, 2.0],
            "spread_line": [1.0, 1.0, -1.0, -2.0, 1.0, 1.0],
            "result": [9.0, -1.0, -3.0, 5.0, 7.0, 1.0],
        }
    )
    top = eval_mod.top_n_metrics(preds, max_n=2)

    n1 = top.filter(pl.col("top_n") == 1).row(0, named=True)
    # top pick each week: +5 edge (win) and -8 edge (loss)
    assert (n1["n_bets"], n1["wins"], n1["losses"], n1["pushes"]) == (2, 1, 1, 0)

    n2 = top.filter(pl.col("top_n") == 2).row(0, named=True)
    # adds +2 (loss) and +3 (win)
    assert (n2["n_bets"], n2["wins"], n2["losses"], n2["pushes"]) == (4, 2, 2, 0)
    assert n2["ats_pct"] == 0.5


def test_top_n_metrics_counts_pushes_and_short_weeks():
    # only 2 bettable games in the week; n=3 must not invent bets
    preds = _preds_frame(
        [
            (4.0, 1.0, 1.0),  # edge +3 -> push
            (-3.0, -1.0, -4.0),  # edge -2 -> win
        ]
    ).with_columns(week=pl.lit(1))
    top = eval_mod.top_n_metrics(preds, max_n=3)
    n3 = top.filter(pl.col("top_n") == 3).row(0, named=True)
    assert (n3["n_bets"], n3["wins"], n3["losses"], n3["pushes"]) == (2, 1, 0, 1)
    # push excluded from ATS%, included in ROI stake
    assert n3["ats_pct"] == 1.0
    assert n3["roi"] == pytest.approx((100 / 110) / 2)


def test_regression_metrics_known_values():
    preds = _preds_frame([(3.0, 0.0, 0.0), (-1.0, 2.0, 3.0)])
    reg = eval_mod.regression_metrics(preds)
    assert reg["mae"] == pytest.approx((3 + 4) / 2)
    assert reg["rmse"] == pytest.approx(np.sqrt((9 + 16) / 2))
    assert reg["market_rmse"] == pytest.approx(np.sqrt((0 + 1) / 2))


def test_backtest_cli_end_to_end(
    tmp_path, monkeypatch, pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    monkeypatch.setattr(eval_mod, "load_pbp", lambda seasons, **kw: pbp_sample)
    monkeypatch.setattr(
        eval_mod, "load_schedule", lambda seasons, **kw: schedule_sample
    )
    cfg = tmp_path / "params.yaml"
    cfg.write_text("n_estimators: 5\nmax_depth: 2\n")
    out = tmp_path / "report.md"

    eval_mod.main(
        [
            "--seasons",
            "2023",
            "--min-week",
            "2",
            "--min-train-games",
            "1",
            "--config",
            str(cfg),
            "--output",
            str(out),
        ]
    )
    report = out.read_text()
    assert "# Spread model walk-forward backtest" in report
    assert "| 20 |" in report  # full default sweep rendered
    assert "Break-even ATS%: 52.38%" in report
    assert "## Top-n confidence picks per week" in report
