"""Market-derived per-week power ratings (#50).

Decomposes each week's closing lines (``spread_line``, ``total_line``)
into per-team offense/defense power ratings plus a league-wide
home-field advantage. Solved as a **per-week snapshot**, ridged toward
the previous week's solve (a fixed-gain Kalman filter) rather than
pooling weeks with recency weights the way the archived
``old_utils.derive_market_power_ratings`` did — each week's lines are
already a complete snapshot of market belief (they embed everything the
market has learned through prior weeks), so pooling raw weeks
double-counts that information.

Sign convention (READ BEFORE USING, it's a bug farm): ``def_rating``
here is points *prevented* below league average — higher = better
defense, so power ratings read as power ratings. This is the
**opposite** of ``ml/features/opponent.py``, whose ``def_rating`` is
EPA *allowed* (higher = worse defense). See that module's docstring for
the mirror note.

``ovr_rating = off_rating + def_rating`` and the model's spread
identity is ``spread = ovr_home - ovr_away + hfa``.

Run via ``make market-ratings`` or directly:

    uv run python -m g_nfl.ml.market_ratings --seasons 2006 ... 2025 \\
        --output data/market_ratings.parquet
    uv run python -m g_nfl.ml.market_ratings --tune
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from g_nfl.ml.data import DEFAULT_CACHE_DIR, load_schedule
from g_nfl.utils.config import CUR_SEASON, HFA

DEFAULT_SEASONS = list(range(2006, CUR_SEASON + 1))
DEFAULT_OUTPUT = Path(__file__).parents[3] / "data" / "market_ratings.parquet"

# tuned on 2006-2019 next-week-line MAE, held out on 2020-2025 (#50, see
# notes/market-derived-ratings.md "Phase 1 results"): lam=0.5 won the grid
# cleanly (MAE rises monotonically with lam), carryover=0.7 edged 0.5.
DEFAULT_LAM = 0.5
DEFAULT_HFA_LAM = 20.0
DEFAULT_CARRYOVER = 0.7

TUNE_LAMS = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
TUNE_CARRYOVERS = [0.5, 0.7]

EMPTY_PRIOR = pl.DataFrame(
    schema={"team": pl.Utf8, "off_rating": pl.Float64, "def_rating": pl.Float64}
)


def implied_team_scores(schedule: pl.DataFrame) -> pl.DataFrame:
    """Per-game implied home/away scores, centered on the season-to-date mean.

    Filters to ``game_type == "REG"`` with non-null ``spread_line``/
    ``total_line``. ``spread_line`` is positive when the home team is
    favored (nflverse convention). ``mu`` (half the average total) is
    computed **per season**, expanding through the current week (never
    a later one) — a single per-week mean would be noisy on a handful
    of games, but pulling in the whole season would leak future weeks'
    lines into an earlier week's baseline, which the anti-leak contract
    (see `market_ratings`) forbids. ``neutral`` flags games where
    ``location != "Home"`` (London/Mexico/Super Bowl, ...), which get
    zero HFA rather than being dropped.
    """
    reg = schedule.filter(
        (pl.col("game_type") == "REG")
        & pl.col("spread_line").is_not_null()
        & pl.col("total_line").is_not_null()
    )
    weekly_mu = (
        reg.group_by("season", "week")
        .agg(pl.col("total_line").sum().alias("_sum"), pl.len().alias("_n"))
        .sort("season", "week")
        .with_columns(
            mu=pl.col("_sum").cum_sum().over("season")
            / pl.col("_n").cum_sum().over("season")
            / 2
        )
        .select("season", "week", "mu")
    )
    return (
        reg.join(weekly_mu, on=["season", "week"])
        .with_columns(
            y_home=(pl.col("total_line") + pl.col("spread_line")) / 2 - pl.col("mu"),
            y_away=(pl.col("total_line") - pl.col("spread_line")) / 2 - pl.col("mu"),
            neutral=pl.col("location") != "Home",
        )
        .select(
            "season",
            "week",
            "game_id",
            "home_team",
            "away_team",
            "y_home",
            "y_away",
            "neutral",
        )
    )


def solve_week(
    games: pl.DataFrame,
    teams: list[str],
    prior: pl.DataFrame,
    prior_hfa: float,
    lam: float,
    hfa_lam: float,
) -> tuple[pl.DataFrame, float]:
    """Ridge-to-prior solve for one week's per-team ratings + hfa.

    ``games`` is this week's rows from `implied_team_scores`. ``teams``
    is the season's full team universe: every team gets an output row
    even on a bye, where the absence of an equation means the ridge
    holds it exactly at its prior (no special-casing needed). ``prior``
    is a ``team, off_rating, def_rating`` frame; any team missing from
    it (cold start, expansion/relocation) gets prior 0.0.

    Minimises ``||y - X @ beta||^2 + lam * ||beta_team - p_team||^2 +
    hfa_lam * (beta_hfa - p_hfa)^2`` in closed form via
    ``np.linalg.solve``. Ratings are re-centered post-solve by
    subtracting one shared constant from off and def (see module-level
    identifiability note in `market_ratings`) so ``mean(ovr_rating) ==
    0`` without changing any fitted value; ``hfa`` is untouched.
    """
    idx = {t: i for i, t in enumerate(teams)}
    k = len(teams)
    n_games = games.height
    n_rows = 2 * n_games

    home_idx = np.array([idx[t] for t in games["home_team"].to_list()])
    away_idx = np.array([idx[t] for t in games["away_team"].to_list()])
    h = np.where(games["neutral"].to_numpy(), 0.0, 1.0)

    X = np.zeros((n_rows, 2 * k + 1))
    y = np.zeros(n_rows)
    home_rows = np.arange(n_games)
    away_rows = np.arange(n_games, n_rows)

    X[home_rows, home_idx] = 1.0
    X[home_rows, k + away_idx] = -1.0
    X[home_rows, 2 * k] = 0.5 * h
    y[home_rows] = games["y_home"].to_numpy().astype(float)

    X[away_rows, away_idx] = 1.0
    X[away_rows, k + home_idx] = -1.0
    X[away_rows, 2 * k] = -0.5 * h
    y[away_rows] = games["y_away"].to_numpy().astype(float)

    prior_off = dict(
        zip(prior["team"].to_list(), prior["off_rating"].to_list(), strict=True)
    )
    prior_def = dict(
        zip(prior["team"].to_list(), prior["def_rating"].to_list(), strict=True)
    )
    p = np.zeros(2 * k + 1)
    for t, i in idx.items():
        p[i] = prior_off.get(t, 0.0)
        p[k + i] = prior_def.get(t, 0.0)
    p[2 * k] = prior_hfa

    L = np.diag([lam] * (2 * k) + [hfa_lam])
    beta = np.linalg.solve(X.T @ X + L, X.T @ y + L @ p)

    off = beta[:k]
    defn = beta[k : 2 * k]
    hfa = float(beta[2 * k])

    # null direction is (off += c, def += c); subtract one shared constant
    # so predictions (off_i - def_j) are exactly unchanged
    c = (off.mean() + defn.mean()) / 2
    off = off - c
    defn = defn - c

    ratings = pl.DataFrame(
        {
            "team": teams,
            "off_rating": off,
            "def_rating": defn,
            "ovr_rating": off + defn,
        }
    )
    return ratings, hfa


def market_ratings(
    schedule: pl.DataFrame,
    lam: float = DEFAULT_LAM,
    hfa_lam: float = DEFAULT_HFA_LAM,
    carryover: float = DEFAULT_CARRYOVER,
) -> pl.DataFrame:
    """Full per-(season, week, team) market-implied ratings trajectory.

    Each season's week 1 is ridged toward ``carryover * (previous
    season's final ratings)`` (0.0 for a team missing from that prior,
    e.g. relocation); every later week is ridged toward the previous
    week's solve within the same season. If no earlier season is
    present at all in ``schedule``, the very first season loaded starts
    from an all-zero team prior and ``p_hfa = HFA`` (`utils.config`).
    ``hfa`` is never shrunk toward 0 on carryover — it isn't team
    specific.

    Returns columns ``season, week, team, off_rating, def_rating,
    ovr_rating, hfa`` (hfa repeated per row for easy consumption).
    """
    games = implied_team_scores(schedule)

    prior = EMPTY_PRIOR
    prior_hfa = HFA
    out = []
    for season in sorted(games["season"].unique().to_list()):
        season_games = games.filter(pl.col("season") == season)
        teams = sorted(
            set(season_games["home_team"].to_list())
            | set(season_games["away_team"].to_list())
        )
        cur_prior = (
            prior.with_columns(
                pl.col("off_rating") * carryover, pl.col("def_rating") * carryover
            )
            if prior.height
            else prior
        )
        cur_prior_hfa = prior_hfa  # hfa carries over unshrunk

        for week in sorted(season_games["week"].unique().to_list()):
            week_games = season_games.filter(pl.col("week") == week)
            ratings, hfa = solve_week(
                week_games, teams, cur_prior, cur_prior_hfa, lam, hfa_lam
            )
            out.append(
                ratings.with_columns(
                    season=pl.lit(season), week=pl.lit(week), hfa=pl.lit(hfa)
                )
            )
            cur_prior = ratings.select("team", "off_rating", "def_rating")
            cur_prior_hfa = hfa

        prior = cur_prior
        prior_hfa = cur_prior_hfa

    return pl.concat(out).select(
        "season", "week", "team", "off_rating", "def_rating", "ovr_rating", "hfa"
    )


def next_week_line_error(ratings: pl.DataFrame, schedule: pl.DataFrame) -> pl.DataFrame:
    """Predict week-``w`` spreads from week-``w-1`` ratings, diff vs the close.

    For each REG game with a non-null ``spread_line``, predicts
    ``ovr[home] - ovr[away] + hfa`` using ratings solved as of the
    *prior* week of the same season, and compares to the actual line.
    Games with no prior week available (season's week 1) are dropped —
    there's nothing to predict from.
    """
    games = schedule.filter(
        (pl.col("game_type") == "REG") & pl.col("spread_line").is_not_null()
    ).select("season", "week", "game_id", "home_team", "away_team", "spread_line")

    # shift each rating row forward one week so it lines up with the week
    # it's used to *predict*, not the week it was solved for
    prior_ratings = ratings.with_columns(week=pl.col("week") + 1)
    home = prior_ratings.select(
        "season",
        "week",
        pl.col("team").alias("home_team"),
        pl.col("ovr_rating").alias("home_ovr"),
        "hfa",
    )
    away = prior_ratings.select(
        "season",
        "week",
        pl.col("team").alias("away_team"),
        pl.col("ovr_rating").alias("away_ovr"),
    )
    return (
        games.join(home, on=["season", "week", "home_team"], how="inner")
        .join(away, on=["season", "week", "away_team"], how="inner")
        .with_columns(
            pred_spread=pl.col("home_ovr") - pl.col("away_ovr") + pl.col("hfa")
        )
        .with_columns(error=pl.col("pred_spread") - pl.col("spread_line"))
        .select(
            "season",
            "week",
            "game_id",
            "home_team",
            "away_team",
            "spread_line",
            "pred_spread",
            "error",
        )
    )


def line_error_summary(errors: pl.DataFrame) -> pl.DataFrame:
    """MAE/RMSE of `next_week_line_error` output: a pooled ``season ==
    "all"`` row plus one row per season."""

    def _row(df: pl.DataFrame) -> dict:
        e = df["error"].to_numpy()
        return {
            "n_games": df.height,
            "mae": float(np.mean(np.abs(e))),
            "rmse": float(np.sqrt(np.mean(e**2))),
        }

    rows = [{"season": "all", **_row(errors)}]
    for season in sorted(errors["season"].unique().to_list()):
        rows.append(
            {"season": str(season), **_row(errors.filter(pl.col("season") == season))}
        )
    return pl.DataFrame(rows)


def tune(
    schedule: pl.DataFrame,
    lams: list[float] = TUNE_LAMS,
    carryovers: list[float] = TUNE_CARRYOVERS,
    hfa_lam: float = DEFAULT_HFA_LAM,
) -> pl.DataFrame:
    """Grid sweep over ``lam``/``carryover``, scored by pooled next-week
    line MAE on ``schedule``. Returns the sweep table sorted best-first."""
    rows = []
    for lam in lams:
        for carryover in carryovers:
            ratings = market_ratings(
                schedule, lam=lam, hfa_lam=hfa_lam, carryover=carryover
            )
            summary = (
                line_error_summary(next_week_line_error(ratings, schedule))
                .filter(pl.col("season") == "all")
                .row(0, named=True)
            )
            rows.append(
                {
                    "lam": lam,
                    "carryover": carryover,
                    "hfa_lam": hfa_lam,
                    "n_games": summary["n_games"],
                    "mae": summary["mae"],
                    "rmse": summary["rmse"],
                }
            )
    return pl.DataFrame(rows).sort("mae")


def compare_ratings(
    market: pl.DataFrame, mine: pl.DataFrame, on: str = "team"
) -> pl.DataFrame:
    """Join two per-``on`` rating frames and add ``diff`` = mine's
    ``ovr_rating`` minus market's, sorted descending — "where am I
    above/below the market". Only ``ovr_rating`` is trustworthy across
    sources (module docstring); off/def split isn't compared here."""
    joined = (
        market.select(on, "ovr_rating")
        .join(mine.select(on, "ovr_rating"), on=on, suffix="_mine")
        .rename({"ovr_rating": "ovr_rating_market"})
    )
    return joined.with_columns(
        diff=pl.col("ovr_rating_mine") - pl.col("ovr_rating_market")
    ).sort("diff", descending=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Market-derived power ratings")
    parser.add_argument("--seasons", type=int, nargs="+", default=DEFAULT_SEASONS)
    parser.add_argument("--lam", type=float, default=DEFAULT_LAM)
    parser.add_argument("--hfa-lam", type=float, default=DEFAULT_HFA_LAM)
    parser.add_argument("--carryover", type=float, default=DEFAULT_CARRYOVER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--tune",
        action="store_true",
        help="run the lam/carryover sweep (TUNE_LAMS x TUNE_CARRYOVERS) instead of fitting",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="refetch source data, ignore cache"
    )
    args = parser.parse_args(argv)

    schedule = load_schedule(
        args.seasons, cache_dir=DEFAULT_CACHE_DIR, refresh=args.refresh
    )

    if args.tune:
        print(tune(schedule, hfa_lam=args.hfa_lam))
        return

    ratings = market_ratings(
        schedule, lam=args.lam, hfa_lam=args.hfa_lam, carryover=args.carryover
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ratings.write_parquet(args.output)
    print(f"wrote {ratings.height} rows to {args.output}")


if __name__ == "__main__":
    main()
