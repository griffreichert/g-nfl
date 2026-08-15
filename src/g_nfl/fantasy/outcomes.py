"""Historical residual outcome distributions: role vs luck (issue #86).

A season misses its August projection for two different reasons, and
``load_ff_opportunity`` separates them:

```
actual ppg  =  baseline * role_ratio  +  luck_delta
               |                         |
               how the role landed       touchdown and efficiency luck
               (xFP vs what ADP implied) (actual minus xFP)
```

Role is partly forecastable — a rookie back in a committee has a wider role than
a 28-year-old WR2, and you can see why in August. Luck is not forecastable at
all, only its typical size at a given position. Modelling them apart gives every
player a distribution with a principled shape instead of one fudge factor.

The baseline is **ADP**, the market's August projection, reconstructed from
MyFantasyLeague's free feed. The residual is measured against it.

Run: ``uv run python -m g_nfl.fantasy.outcomes --seasons 2019 2025``
"""

from __future__ import annotations

import argparse

import nflreadpy
import numpy as np
import polars as pl
import requests

from g_nfl.fantasy.scoring import PRESETS, LeagueConfig

MFL_ADP_URL = "https://api.myfantasyleague.com/{season}/export"

# ff_opportunity's column names -> the #87 stat-line schema ``score()`` consumes.
# ``_exp`` variants of these are the expected side; the names are otherwise equal.
STAT_MAP: dict[str, str] = {
    "pass_yards_gained": "pass_yd",
    "pass_touchdown": "pass_td",
    "pass_interception": "ints",
    "rush_yards_gained": "rush_yd",
    "rush_touchdown": "rush_td",
    "receptions": "rec",
    "rec_yards_gained": "rec_yd",
    "rec_touchdown": "rec_td",
}

BOARD_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

# ADP tiers, in overall picks. Three rounds, then five, then the rest: the round
# where a bust is unreplaceable, the round where it hurts, and the rest.
ADP_TIERS: tuple[tuple[str, int], ...] = (("early", 36), ("mid", 96), ("late", 10_000))

# A bucket needs this many player-seasons before its percentiles mean anything.
MIN_BUCKET = 25

# Player-seasons pooled per rolling window when smoothing the ADP -> ppg curve.
BASELINE_WINDOW = 51

# Fewer games than this and per-game scoring is noise, so the season is dropped
# from the residual pool and counted in the no-show rate instead.
MIN_GAMES = 4

DRAWS = 4_000
SEED = 86


def load_adp(season: int) -> pl.DataFrame:
    """MyFantasyLeague ADP for ``season``, keyed on ``gsis_id``.

    Free and unauthenticated, and the only source that reaches back years, which
    is what makes it the reconstruction of "the projection you would have had in
    that August". ECR cannot do this: FantasyPros publishes the current year.
    """
    params = {
        "TYPE": "adp",
        "FCOUNT": "12",
        "IS_PPR": "1",
        "IS_KEEPER": "N",
        "IS_MOCK": "-1",
        "PERIOD": "DRAFT",
        "JSON": "1",
    }
    response = requests.get(
        MFL_ADP_URL.format(season=season),
        params=params,
        headers={"User-Agent": "g-nfl"},
        timeout=30,
    )
    response.raise_for_status()
    players = response.json()["adp"]["player"]

    adp = pl.DataFrame(players).select(
        pl.col("id").alias("mfl_id"),
        pl.col("averagePick").cast(pl.Float64).alias("adp"),
        pl.col("minPick").cast(pl.Float64).alias("adp_min"),
        pl.col("maxPick").cast(pl.Float64).alias("adp_max"),
        pl.col("draftsSelectedIn").cast(pl.Int64).alias("adp_drafts"),
        pl.lit(season).alias("season"),
    )

    # Position comes from the crosswalk, not the feed: MFL's ADP rows carry an
    # id and nothing else, and the no-show rows need a position to be bucketed.
    ids = (
        nflreadpy.load_ff_playerids()
        .select("mfl_id", "gsis_id", "position", "name")
        .drop_nulls(["mfl_id", "gsis_id"])
        .with_columns(pl.col("mfl_id").cast(pl.Utf8))
        .unique("mfl_id")
    )
    return (
        adp.join(ids, on="mfl_id")
        .drop_nulls("gsis_id")
        .filter(pl.col("position").is_in(BOARD_POSITIONS))
    )


def _score_stat_lines(lines: pl.DataFrame, config: LeagueConfig) -> pl.Expr:
    """The nine-float dot product as an expression, so it runs on either side.

    ``scoring.score()`` wants a full stat-line frame and divides by a flat 17.
    Historical seasons need division by games played, so this borrows the
    weights and leaves the denominator to the caller.
    """
    s = config.scoring
    te_bonus = pl.when(pl.col("position") == "TE").then(s.te_premium).otherwise(0.0)
    return (
        (s.reception + te_bonus) * pl.col("rec")
        + s.rec_yd * pl.col("rec_yd")
        + s.rush_yd * pl.col("rush_yd")
        + s.pass_yd * pl.col("pass_yd")
        + s.td * (pl.col("rush_td") + pl.col("rec_td"))
        + s.pass_td * pl.col("pass_td")
        + s.interception * pl.col("ints")
        + s.fumble_lost * pl.col("fum")
    )


def season_outcomes(seasons: list[int], config: LeagueConfig) -> pl.DataFrame:
    """Per player-season: games, ``actual_ppg`` and ``xfp_ppg`` under ``config``.

    Both sides are scored with the same nine floats, so the split is league-
    specific rather than borrowed from whatever scoring ffopportunity assumed.
    Expected fumbles do not exist in the feed, so fumbles land entirely in the
    luck component — which is where they belong anyway.
    """
    weekly = nflreadpy.load_ff_opportunity(seasons=seasons, stat_type="weekly").filter(
        pl.col("position").is_in(BOARD_POSITIONS)
    )

    totals = (
        weekly.with_columns(
            pl.col("season").cast(pl.Int64),
            (pl.col("rec_fumble_lost") + pl.col("rush_fumble_lost")).alias("fum"),
            pl.lit(0.0).alias("fum_exp"),
        )
        .group_by("player_id", "full_name", "position", "season")
        .agg(
            pl.len().alias("games"),
            *[pl.col(src).sum().alias(dst) for src, dst in STAT_MAP.items()],
            *[
                pl.col(f"{src}_exp").sum().alias(f"{dst}_exp")
                for src, dst in STAT_MAP.items()
            ],
            pl.col("fum").sum(),
            pl.col("fum_exp").sum(),
        )
    )

    stats = [*STAT_MAP.values(), "fum"]
    expected_side = totals.drop(stats).rename({f"{s}_exp": s for s in stats})

    return (
        totals.with_columns(
            (_score_stat_lines(totals, config) / pl.col("games")).alias("actual_ppg"),
            (
                expected_side.select(
                    _score_stat_lines(expected_side, config)
                ).to_series()
                / totals["games"]
            ).alias("xfp_ppg"),
        )
        .drop([f"{s}_exp" for s in stats])
        .rename({"player_id": "gsis_id"})
    )


def _experience(seasons: list[int]) -> pl.DataFrame:
    """``gsis_id`` x season -> experience bucket, from ``rookie_season``."""
    players = nflreadpy.load_players().select("gsis_id", "rookie_season").drop_nulls()
    return (
        pl.DataFrame({"season": seasons}, schema={"season": pl.Int64})
        .join(players, how="cross")
        .with_columns((pl.col("season") - pl.col("rookie_season")).alias("years_in"))
        .with_columns(
            pl.when(pl.col("years_in") <= 0)
            .then(pl.lit("rookie"))
            .when(pl.col("years_in") <= 2)
            .then(pl.lit("year 2-3"))
            .when(pl.col("years_in") <= 6)
            .then(pl.lit("prime"))
            .otherwise(pl.lit("veteran"))
            .alias("experience")
        )
        .select("gsis_id", "season", "experience")
    )


def adp_baseline(history: pl.DataFrame, window: int = BASELINE_WINDOW) -> pl.DataFrame:
    """Median ppg by positional ADP rank, smoothed over neighbouring ranks.

    Non-parametric on purpose. A log-log power law was tried first and its
    curvature error was large enough to matter: it left the median role ratio at
    0.85 in the early tiers and 1.2-1.4 in the late ones, so every bucket
    inherited a level bias that had nothing to do with the players. A rolling
    median over pooled seasons has no functional form to be wrong about.

    Returns ``position`` x ``pos_adp_rank`` -> ``baseline_ppg``.
    """
    return (
        history.sort("position", "pos_adp_rank")
        .with_columns(
            pl.col("actual_ppg")
            .rolling_median(window, center=True, min_samples=5)
            .over("position")
            .alias("smoothed")
        )
        .group_by("position", "pos_adp_rank")
        .agg(pl.col("smoothed").median().alias("baseline_ppg"))
        .drop_nulls("baseline_ppg")
        .sort("position", "pos_adp_rank")
    )


def baseline_ppg(board: pl.DataFrame, curve: pl.DataFrame) -> pl.DataFrame:
    """Look a board's ADP ranks up on the curve, holding the tail flat.

    Ranks past the deepest the history covers get the last measured value: the
    curve is flat down there anyway, and extrapolating a decline off the end
    would invent precision the data does not have.
    """
    return (
        board.sort("pos_adp_rank")
        .join_asof(
            curve.sort("pos_adp_rank"),
            on="pos_adp_rank",
            by="position",
            strategy="nearest",
        )
        .sort("position", "pos_adp_rank")
    )


def build_history(seasons: list[int], config: LeagueConfig) -> pl.DataFrame:
    """Player-seasons with ADP, actual and expected ppg, and their bucket.

    Left join from ADP, so a drafted player who never played keeps a row with
    zero games. Per-game scoring cannot describe that season, so ``residuals()``
    drops it — but it is counted, because the alternative is a late-round
    distribution built only on the late picks who earned a role.
    """
    adp = pl.concat([load_adp(season) for season in seasons])
    outcomes = season_outcomes(seasons, config)

    history = (
        adp.join(outcomes, on=["gsis_id", "season"], how="left")
        .join(_experience(seasons), on=["gsis_id", "season"], how="left")
        .with_columns(
            pl.col("adp")
            .rank("ordinal")
            .over("season", "position")
            .alias("pos_adp_rank"),
            pl.coalesce(pl.col("experience"), pl.lit("unknown")).alias("experience"),
        )
    )

    tier = pl.when(pl.col("adp") <= ADP_TIERS[0][1]).then(pl.lit(ADP_TIERS[0][0]))
    for name, cutoff in ADP_TIERS[1:]:
        tier = tier.when(pl.col("adp") <= cutoff).then(pl.lit(name))
    return history.with_columns(tier.otherwise(pl.lit("late")).alias("adp_tier"))


def played(history: pl.DataFrame) -> pl.DataFrame:
    """Player-seasons with enough games for a per-game number to mean something."""
    return history.filter(pl.col("games").fill_null(0) >= MIN_GAMES)


def no_show_rate(history: pl.DataFrame) -> pl.DataFrame:
    """Share of drafted players per bucket who never reached ``MIN_GAMES``.

    Kept beside the distributions rather than folded into them. A season that
    never happened is an availability outcome, and mixing it into a per-game
    distribution would make both numbers mean less.
    """
    return (
        history.with_columns(
            (pl.col("games").fill_null(0) < MIN_GAMES).alias("no_show")
        )
        .group_by("position", "experience", "adp_tier")
        .agg(
            pl.len().alias("drafted"),
            pl.col("no_show").mean().alias("no_show_rate"),
        )
        .sort("position", "adp_tier", "experience")
    )


def residuals(history: pl.DataFrame) -> pl.DataFrame:
    """Split each qualifying player-season into its role ratio and its luck delta."""
    qualifying = played(history)
    curve = adp_baseline(qualifying)
    return (
        baseline_ppg(qualifying, curve)
        .filter(pl.col("baseline_ppg") > 0)
        .with_columns(
            (pl.col("xfp_ppg") / pl.col("baseline_ppg")).alias("role_ratio"),
            (pl.col("actual_ppg") - pl.col("xfp_ppg")).alias("luck_delta"),
        )
    )


def bucket_distributions(resid: pl.DataFrame) -> pl.DataFrame:
    """Empirical role and luck distributions per position x experience x ADP tier."""
    return (
        resid.group_by("position", "experience", "adp_tier")
        .agg(
            pl.len().alias("n"),
            pl.col("role_ratio").quantile(0.1).alias("role_p10"),
            pl.col("role_ratio").median().alias("role_p50"),
            pl.col("role_ratio").quantile(0.9).alias("role_p90"),
            pl.col("luck_delta").std().alias("luck_sd"),
            pl.col("luck_delta").mean().alias("luck_mean"),
            pl.col("role_ratio").alias("role_sample"),
            pl.col("luck_delta").alias("luck_sample"),
        )
        .sort("position", "adp_tier", "experience")
    )


def _pool(
    resid: pl.DataFrame, position: str, experience: str, tier: str
) -> pl.DataFrame:
    """The tightest bucket with enough player-seasons, widening if it is thin.

    Bucket, then position x experience, then position. A wrong-but-populated
    distribution beats a right-but-empty one; the fallback used is reported.
    """
    for keys, label in (
        (
            (pl.col("experience") == experience) & (pl.col("adp_tier") == tier),
            "bucket",
        ),
        (pl.col("experience") == experience, "experience"),
        (pl.lit(True), "position"),
    ):
        pool = resid.filter((pl.col("position") == position) & keys)
        if pool.height >= MIN_BUCKET:
            return pool.with_columns(pl.lit(label).alias("pool_level"))
    return resid.filter(pl.col("position") == position).with_columns(
        pl.lit("position").alias("pool_level")
    )


def outcome_percentiles(
    board: pl.DataFrame, resid: pl.DataFrame, draws: int = DRAWS
) -> pl.DataFrame:
    """Attach ``floor`` / ``median`` / ``ceiling`` ppg to a board.

    Draws role and luck independently from the player's bucket and recombines:
    ``proj_ppg * role_ratio + luck_delta``. Independent because they are
    different mechanisms — a back can lose the job and still score three flukey
    touchdowns before he does.

    Deliberately reports the total, not the xFP percentiles: touchdown luck
    happens to the manager who rostered the player, so a floor built on xFP
    alone understates the range you live with.
    """
    rng = np.random.default_rng(SEED)
    rows = []
    for player in board.iter_rows(named=True):
        pool = _pool(
            resid,
            player["position"],
            player.get("experience", "unknown"),
            player.get("adp_tier", "late"),
        )
        role = rng.choice(pool["role_ratio"].to_numpy(), draws)
        luck = rng.choice(pool["luck_delta"].to_numpy(), draws)
        sim = player["proj_ppg"] * role + luck
        floor, median, ceiling = np.quantile(sim, [0.1, 0.5, 0.9])
        rows.append(
            {
                "gsis_id": player["gsis_id"],
                "floor": float(floor),
                "outcome_median": float(median),
                "ceiling": float(ceiling),
                "outcome_pool": pool["pool_level"][0],
            }
        )
    return board.join(pl.DataFrame(rows), on="gsis_id", how="left")


def attach_outcomes(
    board: pl.DataFrame, resid: pl.DataFrame, season: int
) -> pl.DataFrame:
    """Give a current board the bucket columns, then its outcome percentiles.

    The board has no ADP (that is #99), so the tier comes from ECR where
    FantasyPros ranks the player and from board rank where it does not. Both are
    ranks over the same draft, and the tier boundaries are three rounds wide, so
    the substitution only bites for players sitting on a boundary.
    """
    experience = _experience([season]).drop("season")
    tier = pl.when(pl.col("draft_rank") <= ADP_TIERS[0][1]).then(
        pl.lit(ADP_TIERS[0][0])
    )
    for name, cutoff in ADP_TIERS[1:]:
        tier = tier.when(pl.col("draft_rank") <= cutoff).then(pl.lit(name))

    bucketed = (
        board.join(experience, on="gsis_id", how="left")
        .with_columns(
            pl.coalesce(pl.col("ecr"), pl.col("overall_rank")).alias("draft_rank"),
            pl.coalesce(pl.col("experience"), pl.lit("unknown")).alias("experience"),
        )
        .with_columns(tier.otherwise(pl.lit("late")).alias("adp_tier"))
    )
    return outcome_percentiles(bucketed, resid).drop("draft_rank")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", type=int, nargs=2, default=[2019, 2025])
    parser.add_argument("--preset", default="ppr_12", choices=sorted(PRESETS))
    args = parser.parse_args()

    seasons = list(range(args.seasons[0], args.seasons[1] + 1))
    history = build_history(seasons, PRESETS[args.preset])
    resid = residuals(history)

    print(
        f"{history.height} drafted player-seasons {seasons[0]}-{seasons[-1]}, "
        f"{resid.height} with {MIN_GAMES}+ games\n"
    )
    with pl.Config(tbl_rows=60, tbl_cols=14):
        print(
            bucket_distributions(resid)
            .drop("role_sample", "luck_sample")
            .join(no_show_rate(history), on=["position", "experience", "adp_tier"])
        )


if __name__ == "__main__":
    main()
