"""Weekly prediction: model line, market line, edge, for one week's slate.

The entry gModel submits to the pool is built on top of this (#13). The job
is deliberately small: no registry, no artifact to go stale. It refits on
every completed game strictly before the week being predicted, which is
exactly what `evaluate.walk_forward_predictions` does per fold, so the
number the site shows and the number the backtest reports come from the
same code path.

**Why `v3_early`, every week.** The game matrix lags team stats by a
week, so a week-1 game has no stats row to join and every in-season
feature is null. Left alone the model answers with one constant for the
whole slate and ``edge = pred - spread`` then ranks the board by
``|spread|`` -- its top pick is the biggest underdog every time.
`v3_early` adds the preseason block (prior-season form and market
rating, coach and QB change, draft capital, snap retention), which is
the only thing week 1 has to go on.

On a 5-season window the block looked like it cost late-season MAE, and
the first cut of this job switched back to `v1_team` from week 5. On the
11-season window that reverses: paired on the same 2687 games, the block
is better in every band -- week 1 by 1.63 points of MAE (t=8.9), weeks
5-8 by 0.09 (t=2.0), weeks 9+ by 0.04 (t=1.5). The late-season cost was
a small-training-set artifact, so there is one feature set and no
regime switch. Method and every null result in
`notes/modelling/early-weeks.md`.

`DEFAULT_PREDICT_SEASONS` is that deep window, and it matters: the same
feature set on 5 seasons gives a week-1 MAE of 2.50 against 2.39 on 11.

Run:

    uv run python -m g_nfl.ml.predict --season 2026 --week 1
"""

import argparse
from pathlib import Path
from typing import Any

import polars as pl

from g_nfl.ml.data import (
    DEFAULT_CACHE_DIR,
    load_draft_picks,
    load_pbp,
    load_players,
    load_rosters_weekly,
    load_schedule,
    load_snap_counts,
)
from g_nfl.ml.features import build_features
from g_nfl.ml.features.registry import get_feature_set
from g_nfl.ml.features.windows import DEFAULT_ROLLING_WEEKS
from g_nfl.ml.models.spread import SpreadModel
from g_nfl.ml.train import CHAMPION_PARAMS, DEFAULT_CARRYOVER_K, DEFAULT_TARGET

#: The feature set every week is predicted with (see the module note).
FEATURE_SET = "v3_early"

#: Training window. Deep history is what makes the preseason block pay:
#: the pbp cache starts in 2013 and a season needs a prior season behind
#: it, so 2015 is the first year everything is available.
DEEP_SEASONS_START = 2015

#: Games with no closing line yet still get a prediction; edge is null.
OUTPUT_COLS = [
    "game_id",
    "season",
    "week",
    "away_team",
    "home_team",
    "spread_line",
    "pred",
    "edge",
    "pick",
]


def training_seasons(season: int) -> list[int]:
    """The deep window, ending at the season being predicted."""
    return list(range(DEEP_SEASONS_START, season + 1))


def build_matrix(
    seasons: list[int],
    *,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
    carryover_k: float | None = DEFAULT_CARRYOVER_K,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pl.DataFrame:
    """Game matrix over ``seasons``, unplayed games included.

    ``min_week=1`` so week 1 is in the matrix at all, and the preseason
    block is always attached -- `v1_team` ignores it, so the late regime
    is unaffected by its presence.
    """
    pbp = load_pbp(seasons, cache_dir=cache_dir, refresh=refresh)
    schedule = load_schedule(seasons, cache_dir=cache_dir, refresh=refresh)
    return build_features(
        pbp,
        schedule,
        rolling_weeks=rolling_weeks,
        min_week=1,
        carryover_k=carryover_k,
        preseason=True,
        draft=load_draft_picks(seasons, cache_dir=cache_dir, refresh=refresh),
        snaps=load_snap_counts(seasons, cache_dir=cache_dir, refresh=refresh),
        rosters=load_rosters_weekly(seasons, cache_dir=cache_dir, refresh=refresh),
        players=load_players(cache_dir=cache_dir, refresh=refresh),
    )


def predict_week(
    season: int,
    week: int,
    *,
    seasons: list[int] | None = None,
    params: dict[str, Any] | None = None,
    target: str = DEFAULT_TARGET,
    carryover_k: float | None = DEFAULT_CARRYOVER_K,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pl.DataFrame:
    """Model line, market line and edge for every game in one week.

    Trains on every completed game strictly before ``(season, week)`` --
    the same rule the walk-forward backtest applies, so a week predicted
    here and the same week in a backtest see identical training data.

    ``edge = pred - spread_line`` is the home side's edge: positive means
    the model likes the home side, negative the away side. ``pick`` names
    that side. Games without a posted line get a ``pred`` and a null
    ``edge``.
    """
    seasons = sorted(set((seasons or training_seasons(season)) + [season - 1, season]))
    matrix = build_matrix(
        seasons, carryover_k=carryover_k, cache_dir=cache_dir, refresh=refresh
    )

    fs = get_feature_set(FEATURE_SET)
    cols = fs.columns(matrix)

    before = (pl.col("season") < season) | (
        (pl.col("season") == season) & (pl.col("week") < week)
    )
    train = matrix.filter(
        before & pl.col("result").is_not_null() & pl.col(target).is_not_null()
    )
    if train.is_empty():
        raise ValueError(f"no completed games before {season} week {week} to train on")

    slate = matrix.filter((pl.col("season") == season) & (pl.col("week") == week))
    if slate.is_empty():
        raise ValueError(f"no games scheduled for {season} week {week}")

    model = SpreadModel({**CHAMPION_PARAMS, **(params or {})})
    model.fit(train.select(cols).to_numpy(), train[target].to_numpy())
    preds = model.predict(slate.select(cols).to_numpy())

    return (
        slate.with_columns(pred=pl.Series(preds, dtype=pl.Float64))
        .with_columns(edge=pl.col("pred") - pl.col("spread_line"))
        .with_columns(
            pick=pl.when(pl.col("edge") > 0)
            .then(pl.col("home_team"))
            .when(pl.col("edge") < 0)
            .then(pl.col("away_team"))
            .otherwise(None)
        )
        .select(OUTPUT_COLS)
        .sort(pl.col("edge").abs(), descending=True, nulls_last=True)
    )


def main(argv: list[str] | None = None) -> None:
    from g_nfl.picks.calendar import current_season, current_week

    parser = argparse.ArgumentParser(description="Predict one week's slate")
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=None,
        help="training seasons (the season being predicted is always added)",
    )
    parser.add_argument("--output", type=Path, help="write the table as parquet")
    parser.add_argument(
        "--refresh", action="store_true", help="refetch source data, ignore cache"
    )
    args = parser.parse_args(argv)

    season = args.season or current_season()
    week = args.week or current_week(season)
    table = predict_week(season, week, seasons=args.seasons, refresh=args.refresh)

    print(f"{season} week {week}, feature set {FEATURE_SET}\n")
    with pl.Config(tbl_rows=32, tbl_width_chars=140):
        print(table)
    if args.output:
        table.write_parquet(args.output)
        print(f"\nwrote {args.output}")


if __name__ == "__main__":
    main()
