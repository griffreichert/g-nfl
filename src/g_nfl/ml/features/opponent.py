"""Opponent-adjusted team ratings via weighted ridge regression.

All other team stats in the pipeline are raw: a team's EPA/success/CPOE
mean is unadjusted for who it played. This module fits a per-(season,
week) two-way (offense/defense) ridge regression at team-game grain —
the standard "strength of schedule" adjustment — so a team's rating
reflects performance relative to the opponents it actually faced.

Anti-leak contract (hard requirement): ratings for game week ``w`` are
fit on strictly-prior data only — weeks ``< w`` of the same season, plus
the *entire* prior season at a lower sample weight (so week-1 of a
season isn't cold). Nothing from week ``w`` or later ever enters the
fit, so joining the (season, week) rating onto that week's matrix row
needs no additional lag (same pattern as `injuries.add_injuries`). Off
by default (see `build_features` ``opp_adjust``).
"""

import numpy as np
import polars as pl

STATS = ["epa", "success", "cpoe"]


def team_games_frame(plays: pl.DataFrame) -> pl.DataFrame:
    """One row per (season, week, posteam, defteam) with null-safe stat means.

    ``plays`` is the filtered play-level frame (`plays.play_features`);
    cpoe is null on non-pass plays so a team-game with no dropbacks gets
    a null cpoe mean.
    """
    return plays.group_by("season", "week", "posteam", "defteam").agg(
        [pl.col(stat).mean().alias(stat) for stat in STATS]
    )


def fit_opponent_ratings(
    team_games: pl.DataFrame,
    stat: str,
    lam: float,
    prior_weight: float,
    season: int,
    week: int,
) -> pl.DataFrame:
    """Weighted ridge fit of per-team offense/defense ratings for one stat.

    Training rows: current-``season`` team-games with ``week <= week - 1``
    at sample weight 1.0, plus every ``season - 1`` team-game at weight
    ``prior_weight`` — nothing else. y is the team-game ``stat`` mean,
    centered on its weighted mean first, so ratings sit relative to the
    (weighted) league average and the intercept isn't penalized. Returns
    one row per team with ``off_rating``/``def_rating``; a team with no
    rows in the training window simply isn't in the output (callers treat
    that as league average, 0).
    """
    cur = team_games.filter(
        (pl.col("season") == season)
        & (pl.col("week") <= week - 1)
        & pl.col(stat).is_not_null()
    ).with_columns(_w=pl.lit(1.0))
    prior = team_games.filter(
        (pl.col("season") == season - 1) & pl.col(stat).is_not_null()
    ).with_columns(_w=pl.lit(float(prior_weight)))
    rows = pl.concat([cur, prior], how="vertical_relaxed")

    empty = pl.DataFrame(
        schema={"team": pl.Utf8, "off_rating": pl.Float64, "def_rating": pl.Float64}
    )
    if rows.height == 0:
        return empty

    teams = sorted(set(rows["posteam"].to_list()) | set(rows["defteam"].to_list()))
    idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)
    n = rows.height

    off_idx = np.array([idx[t] for t in rows["posteam"].to_list()])
    def_idx = np.array([idx[t] for t in rows["defteam"].to_list()])
    X = np.zeros((n, 2 * n_teams))
    X[np.arange(n), off_idx] = 1.0
    X[np.arange(n), n_teams + def_idx] = 1.0

    y = rows[stat].to_numpy().astype(float)
    w = rows["_w"].to_numpy().astype(float)
    if w.sum() == 0:
        return empty

    y_centered = y - np.sum(w * y) / np.sum(w)
    xtw = X.T * w  # (2T, n), each row scaled by its sample weight
    a = xtw @ X + lam * np.eye(2 * n_teams)
    b = xtw @ y_centered
    beta = np.linalg.solve(a, b)

    return pl.DataFrame(
        {
            "team": teams,
            "off_rating": beta[:n_teams],
            "def_rating": beta[n_teams:],
        }
    )


def add_opponent_ratings(
    matrix: pl.DataFrame,
    team_games: pl.DataFrame,
    lam: float,
    prior_weight: float,
) -> pl.DataFrame:
    """Join per-(season, week) opponent-adjusted ratings onto the matrix.

    Adds 12 cols (``{home,away}_{epa,success,cpoe}_adj_{off,def}``) plus
    ``adj_rating_diff``. Ratings for a game's own week only use strictly
    earlier weeks (+ prior season) by construction (see
    `fit_opponent_ratings`), so this join needs no extra lag. Weeks with
    no usable training data at all (e.g. week 1 of the earliest loaded
    season with no prior season loaded) get null ratings for every team;
    weeks with data get 0 (league average) for any team absent from the
    fit (cold start / relocation).
    """
    all_teams = (
        pl.concat(
            [
                team_games.select(pl.col("posteam").alias("team")),
                team_games.select(pl.col("defteam").alias("team")),
            ]
        )
        .unique()
        .sort("team")
    )

    pairs = matrix.select("season", "week").unique().sort("season", "week")
    week_frames = []
    for season, week in pairs.iter_rows():
        stat_frames = []
        for stat in STATS:
            fit = fit_opponent_ratings(
                team_games, stat, lam, prior_weight, season, week
            )
            if fit.height == 0:
                joined = all_teams.with_columns(
                    pl.lit(None, dtype=pl.Float64).alias("off_rating"),
                    pl.lit(None, dtype=pl.Float64).alias("def_rating"),
                )
            else:
                joined = all_teams.join(fit, on="team", how="left").with_columns(
                    pl.col("off_rating", "def_rating").fill_null(0.0)
                )
            stat_frames.append(
                joined.rename(
                    {"off_rating": f"{stat}_adj_off", "def_rating": f"{stat}_adj_def"}
                )
            )
        combined = stat_frames[0]
        for f in stat_frames[1:]:
            combined = combined.join(f, on="team")
        week_frames.append(
            combined.with_columns(season=pl.lit(season), week=pl.lit(week))
        )

    ratings = pl.concat(week_frames).with_columns(
        pl.col("season").cast(matrix.schema["season"]),
        pl.col("week").cast(matrix.schema["week"]),
    )
    adj_cols = [f"{stat}_adj_{side}" for stat in STATS for side in ("off", "def")]
    away = ratings.rename({"team": "away_team", **{c: f"away_{c}" for c in adj_cols}})
    home = ratings.rename({"team": "home_team", **{c: f"home_{c}" for c in adj_cols}})
    return (
        matrix.join(away, on=["away_team", "season", "week"], how="left")
        .join(home, on=["home_team", "season", "week"], how="left")
        .with_columns(
            # def_rating is EPA *allowed* (higher = worse defense), so the
            # home margin gains from the away defense's rating and loses to
            # its own defense's: (home_off + away_def) - (away_off + home_def)
            adj_rating_diff=(pl.col("home_epa_adj_off") + pl.col("away_epa_adj_def"))
            - (pl.col("away_epa_adj_off") + pl.col("home_epa_adj_def"))
        )
    )
