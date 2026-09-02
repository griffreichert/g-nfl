"""Preseason team features: what is knowable about a team before it has
played a snap of the current season.

The matrix lags in-season stats by a week, so a week-1 game joins to a
week-0 stats row that does not exist and every feature comes back null.
Measured on 2021-2025 walk-forward, that makes the week-1 prediction a
single constant (+1.24 for every game), so ``edge = pred - spread`` ranks
the slate by ``|spread|`` and the model's top pick is always the biggest
underdog. See `notes/modelling/early-weeks.md`.

Everything here is keyed on (team, season) and derived from *prior*
seasons plus facts settled before week 1 kicks off (the draft, the
week-1 coach, the week-1 starting QB, the week-1 roster). It is
therefore constant within a season and safe to join onto every week
without a lag.

Three families:

- **form** — prior-season rate stats and scoring, the team as it played
- **market** — prior-season mean closing-line strength, the market's
  settled view of the team, ``HFA`` removed
- **change** — what happened since: new coach, new QB, draft capital
  spent, and the share of last season's snaps still on the roster

The coach arrives only as a change flag. His career record, carried
across teams, was built and measured as nothing (MAE 2.2923 with it and
2.2958 without, n=2687), so it is not here -- see
`notes/modelling/early-weeks.md`. The QB is likewise a change flag only;
his portable quality is `features/qb.py`, keyed on ``passer_player_id``
and switched on with ``qb_ctx``, which is worth a great deal more.
"""

import polars as pl

from g_nfl.ml.features.plays import play_features
from g_nfl.ml.features.team_week import team_week_stats
from g_nfl.utils.config import HFA
from g_nfl.utils.teams import standardize_teams

# prior-season rate stats carried forward, offense and defense
FORM_STATS = [
    "epa_mean",
    "success_mean",
    "cpoe_mean",
    "pass_oe_mean",
    "sack_mean",
    "first_down_mean",
]

# round weights for draft capital, a coarse stand-in for a pick-value
# chart: round 1 is worth ~16x a round-7 pick, which is the right order
# of magnitude on every published curve. Deliberately blunt -- the
# feature is "how much did this team invest", not a trade calculator.
ROUND_VALUE = {1: 4.0, 2: 2.0, 3: 1.2, 4: 0.8, 5: 0.5, 6: 0.35, 7: 0.25}

PRESEASON_PREFIX = "pre_"


def _prior_season_form(pbp: pl.DataFrame) -> pl.DataFrame:
    """Per (team, season) mean of the prior season's rate stats.

    Aggregates the prior season's team-weeks, then stamps the row with
    ``season + 1`` so it joins onto the season it is a prior *for*.
    """
    weekly = team_week_stats(play_features(pbp))
    cols = [c for c in FORM_STATS if c in weekly.columns]
    cols += [f"{c}_def" for c in FORM_STATS if f"{c}_def" in weekly.columns]
    return (
        weekly.group_by("team", "season")
        .agg(pl.col(c).mean().alias(f"{PRESEASON_PREFIX}{c}") for c in cols)
        .with_columns(pl.col("season") + 1)
    )


def _unpivot_games(schedule: pl.DataFrame) -> pl.DataFrame:
    """REG games as one row per team-game, carrying the team's own
    score, its opponent's, and its side of the closing line.

    ``spread_line`` is the home margin, so ``home_str - away_str =
    spread_line - HFA`` and the away team's side is the negation,
    ``HFA - spread_line``.
    """
    reg = schedule.filter(pl.col("game_type") == "REG")
    home = reg.select(
        pl.col("home_team").alias("team"),
        "season",
        pl.col("home_score").alias("pts_for"),
        pl.col("away_score").alias("pts_against"),
        (pl.col("spread_line") - HFA).alias("mkt_str"),
    )
    away = reg.select(
        pl.col("away_team").alias("team"),
        "season",
        pl.col("away_score").alias("pts_for"),
        pl.col("home_score").alias("pts_against"),
        (HFA - pl.col("spread_line")).alias("mkt_str"),
    )
    return pl.concat([home, away])


def _prior_season_results(schedule: pl.DataFrame) -> pl.DataFrame:
    """Per (team, season) prior-season scoring, margin, pythagorean win
    rate, and mean market strength, stamped onto the following season.

    Pythagorean exponent 2.37 is the standard NFL fit. Games without a
    closing line drop out of ``pre_mkt_rating`` only, via ``mean``
    ignoring nulls, so a team with a few missing lines still gets a
    rating from the rest of its season.
    """
    return (
        _unpivot_games(schedule)
        .filter(pl.col("pts_for").is_not_null())
        .group_by("team", "season")
        .agg(
            pre_pts_for=pl.col("pts_for").mean(),
            pre_pts_against=pl.col("pts_against").mean(),
            pre_margin=(pl.col("pts_for") - pl.col("pts_against")).mean(),
            pre_mkt_rating=pl.col("mkt_str").mean(),
            _pf_total=pl.col("pts_for").sum(),
            _pa_total=pl.col("pts_against").sum(),
        )
        .with_columns(
            pre_pythag=pl.col("_pf_total").pow(2.37)
            / (pl.col("_pf_total").pow(2.37) + pl.col("_pa_total").pow(2.37))
        )
        .drop("_pf_total", "_pa_total")
        .with_columns(pl.col("season") + 1)
    )


def _week1_starters(schedule: pl.DataFrame) -> pl.DataFrame:
    """Each team's week-1 starting QB id and head coach for the season,
    from the week-1 schedule rows."""
    wk1 = schedule.filter((pl.col("game_type") == "REG") & (pl.col("week") == 1))
    home = wk1.select(
        pl.col("home_team").alias("team"),
        "season",
        pl.col("home_qb_id").alias("qb_id"),
        pl.col("home_coach").alias("coach"),
    )
    away = wk1.select(
        pl.col("away_team").alias("team"),
        "season",
        pl.col("away_qb_id").alias("qb_id"),
        pl.col("away_coach").alias("coach"),
    )
    return pl.concat([home, away])


def _prior_primary_qb(pbp: pl.DataFrame) -> pl.DataFrame:
    """Each (team, season)'s most-used passer, stamped onto the next
    season as ``prior_qb_id``."""
    return (
        pbp.filter(
            (pl.col("season_type") == "REG")
            & (pl.col("qb_dropback") == 1)
            & pl.col("passer_player_id").is_not_null()
        )
        .group_by("posteam", "season", "passer_player_id")
        .agg(n=pl.len())
        .sort("n", descending=True)
        .group_by("posteam", "season", maintain_order=True)
        .agg(pl.col("passer_player_id").first().alias("prior_qb_id"))
        .rename({"posteam": "team"})
        .with_columns(pl.col("season") + 1)
    )


def _prior_coach(schedule: pl.DataFrame) -> pl.DataFrame:
    """Each (team, season)'s final-game head coach, stamped onto the
    next season as ``prior_coach``."""
    reg = schedule.filter(pl.col("game_type") == "REG")
    home = reg.select(
        pl.col("home_team").alias("team"),
        "season",
        "week",
        pl.col("home_coach").alias("coach"),
    )
    away = reg.select(
        pl.col("away_team").alias("team"),
        "season",
        "week",
        pl.col("away_coach").alias("coach"),
    )
    return (
        pl.concat([home, away])
        .sort("week")
        .group_by("team", "season", maintain_order=True)
        .agg(pl.col("coach").last().alias("prior_coach"))
        .with_columns(pl.col("season") + 1)
    )


def _draft_capital(draft: pl.DataFrame) -> pl.DataFrame:
    """Per (team, season) draft investment: weighted round value, the
    count of round-1 picks, and the count inside the top 50 overall."""
    value = pl.col("round").replace_strict(ROUND_VALUE, default=0.0)
    return (
        draft.drop_nulls("team")
        .with_columns(
            pl.col("team").map_elements(standardize_teams, return_dtype=pl.String)
        )
        .group_by("team", "season")
        .agg(
            pre_draft_value=value.sum(),
            pre_first_rounders=(pl.col("round") == 1).sum(),
            pre_top50_picks=(pl.col("pick") <= 50).sum(),
        )
    )


def _snap_retention(
    snaps: pl.DataFrame,
    rosters: pl.DataFrame,
    players: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Share of a team's prior-season snaps played by players on its
    current week-1 roster.

    The roster is the week-1 one, settled before kickoff; the snaps are
    entirely last season's. A team that keeps everyone scores near 1.0,
    a gutted roster near 0. Teams with no prior-season snap rows (the
    earliest loaded season) get no row and land null after the join.

    Snap rows are keyed on ``pfr_player_id`` and 45% of weekly-roster
    rows carry no ``pfr_id``, so ``players`` (the id crosswalk) fills
    the gap through ``gsis_id``. Without it retention is understated by
    roughly a third across the board.
    """
    prior = (
        snaps.filter(pl.col("game_type") == "REG")
        .drop_nulls("team")
        .with_columns(
            pl.col("team").map_elements(standardize_teams, return_dtype=pl.String)
        )
        .group_by("team", "season", "pfr_player_id")
        .agg(
            snaps=pl.col("offense_snaps").fill_null(0).sum()
            + pl.col("defense_snaps").fill_null(0).sum()
        )
        .with_columns(pl.col("season") + 1)
    )
    roster = (
        rosters.filter(pl.col("week") == 1)
        .drop_nulls("team")
        .with_columns(
            pl.col("team").map_elements(standardize_teams, return_dtype=pl.String)
        )
    )
    if players is not None:
        crosswalk = players.select("gsis_id", crosswalk_pfr="pfr_id").drop_nulls()
        roster = roster.join(crosswalk, on="gsis_id", how="left").with_columns(
            pl.col("pfr_id").fill_null(pl.col("crosswalk_pfr"))
        )
    wk1_roster = roster.select("team", "season", "pfr_id").unique().drop_nulls("pfr_id")
    return (
        prior.join(
            wk1_roster.with_columns(retained=pl.lit(1)),
            left_on=["team", "season", "pfr_player_id"],
            right_on=["team", "season", "pfr_id"],
            how="left",
        )
        .group_by("team", "season")
        .agg(
            pre_snap_retention=(pl.col("snaps") * pl.col("retained").fill_null(0)).sum()
            / pl.col("snaps").sum()
        )
    )


def preseason_features(
    pbp: pl.DataFrame,
    schedule: pl.DataFrame,
    draft: pl.DataFrame | None = None,
    snaps: pl.DataFrame | None = None,
    rosters: pl.DataFrame | None = None,
    players: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """One row per (team, season) of everything knowable before week 1.

    ``pbp``/``schedule`` must carry at least one season before the ones
    being modelled, or every prior-season column comes back null.
    ``draft``, ``snaps`` and ``rosters`` are optional: each adds its own
    columns and is skipped when absent.
    """
    universe = (
        pl.concat(
            [
                schedule.select(pl.col("home_team").alias("team"), "season"),
                schedule.select(pl.col("away_team").alias("team"), "season"),
            ]
        )
        .unique()
        .filter(pl.col("team").is_not_null())
    )

    out = (
        universe.join(_prior_season_form(pbp), on=["team", "season"], how="left")
        .join(_prior_season_results(schedule), on=["team", "season"], how="left")
        .join(_week1_starters(schedule), on=["team", "season"], how="left")
        .join(_prior_primary_qb(pbp), on=["team", "season"], how="left")
        .join(_prior_coach(schedule), on=["team", "season"], how="left")
        .with_columns(
            pre_qb_change=(
                pl.col("prior_qb_id").is_not_null()
                & pl.col("qb_id").is_not_null()
                & (pl.col("qb_id") != pl.col("prior_qb_id"))
            ).cast(pl.Int8),
            pre_coach_change=(
                pl.col("prior_coach").is_not_null()
                & pl.col("coach").is_not_null()
                & (pl.col("coach") != pl.col("prior_coach"))
            ).cast(pl.Int8),
        )
        .drop("qb_id", "coach", "prior_qb_id", "prior_coach")
    )

    if draft is not None:
        out = out.join(_draft_capital(draft), on=["team", "season"], how="left")
    if snaps is not None and rosters is not None:
        out = out.join(
            _snap_retention(snaps, rosters, players), on=["team", "season"], how="left"
        )
    return out


def add_preseason(
    matrix: pl.DataFrame,
    preseason: pl.DataFrame,
) -> pl.DataFrame:
    """Join home/away preseason features onto the game matrix, plus a
    ``pre_diff_*`` column per numeric pair.

    No lag: these are constant within a season and settled before week
    1, so every week of the season sees the same values.
    """
    feature_cols = [c for c in preseason.columns if c not in ("team", "season")]
    home = preseason.select(
        pl.col("team").alias("home_team"),
        "season",
        *[pl.col(c).alias(f"home_{c}") for c in feature_cols],
    )
    away = preseason.select(
        pl.col("team").alias("away_team"),
        "season",
        *[pl.col(c).alias(f"away_{c}") for c in feature_cols],
    )
    joined = matrix.join(home, on=["home_team", "season"], how="left").join(
        away, on=["away_team", "season"], how="left"
    )
    return joined.with_columns(
        (pl.col(f"home_{c}") - pl.col(f"away_{c}")).alias(
            f"pre_diff_{c.removeprefix(PRESEASON_PREFIX)}"
        )
        for c in feature_cols
    )
