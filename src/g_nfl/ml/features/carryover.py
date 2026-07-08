"""L2 prior-season carryover: shrink thin early-season rates toward the
team's prior-season final rate, decaying as games accumulate.

Early in a season a team's season-to-date stats are noisy (1-2 games). Blending
toward last season's settled rate stabilises them; the weight on the prior
decays as the current season fills in. Augments the flat L1 ``{stat}_season``
cols with one ``{stat}_carry`` col per rate stat (try augment before replace).

#47: the blend weight also carries a ``continuity`` multiplier (default 1.0,
unchanged) so teams with a new QB / new coach / a heavy round-1 infusion keep
less of the prior-season rate — see ``team_discontinuity`` and
``continuity_from_discontinuity``.
"""

import polars as pl
import polars.selectors as cs

from g_nfl.utils.teams import standardize_teams


def carryover_blend(
    cur: pl.Expr,
    prior: pl.Expr,
    games: pl.Expr,
    k: float,
    continuity: float | pl.Expr = 1.0,
) -> pl.Expr:
    """Blend a current rate toward a prior rate.

    ``w = k / (k + games) * continuity`` is the weight on ``prior`` — high when
    ``games`` is small (``k`` pseudo-games of prior), decaying to ~0 as the
    season fills in. Missing ``prior`` (e.g. a relocated team with no prior row
    in the window) falls back to ``cur`` unchanged (w=0). ``continuity`` is a
    scalar or a per-row ``pl.Expr`` (#47: ``c ** disc_count``, see
    ``continuity_from_discontinuity``) — pure expr math either way.
    """
    w = (k / (k + games)) * continuity
    blended = w * prior + (1 - w) * cur
    return pl.when(prior.is_null()).then(cur).otherwise(blended)


def _primary_passer(pbp: pl.DataFrame) -> pl.DataFrame:
    """Each (team, season)'s primary passer within the given (already
    week-filtered if desired) REG pbp slice: most ``qb_dropback==1`` plays
    by a named passer."""
    counts = (
        pbp.filter(
            (pl.col("season_type") == "REG")
            & (pl.col("qb_dropback") == 1)
            & pl.col("passer_player_id").is_not_null()
        )
        .group_by("posteam", "season", "passer_player_id")
        .agg(n=pl.len())
    )
    return (
        counts.sort("n", descending=True)
        .group_by("posteam", "season", maintain_order=True)
        .agg(pl.col("passer_player_id").first())
        .rename({"posteam": "team", "passer_player_id": "primary_passer"})
    )


def _qb_change_signal(pbp: pl.DataFrame) -> pl.DataFrame:
    """1 if a team's weeks-1-3 primary passer differs from its prior
    season's full-season primary passer; 0 if the prior season isn't in
    the loaded ``pbp`` (e.g. earliest season in the window)."""
    early = _primary_passer(pbp.filter(pl.col("week") <= 3))
    prior = (
        _primary_passer(pbp)
        .with_columns((pl.col("season") + 1).alias("season"))
        .rename({"primary_passer": "prior_passer"})
    )
    return (
        early.join(prior, on=["team", "season"], how="left")
        .with_columns(
            qb_change=(
                pl.col("prior_passer").is_not_null()
                & (pl.col("primary_passer") != pl.col("prior_passer"))
            ).cast(pl.Int8)
        )
        .select("team", "season", "qb_change")
    )


def _unpivot_teams(schedule: pl.DataFrame, week: pl.Expr | None = None) -> pl.DataFrame:
    """REG schedule rows -> one row per team-game: team, season, week, coach."""
    reg = schedule.filter(pl.col("game_type") == "REG")
    if week is not None:
        reg = reg.filter(week)
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
    return pl.concat([home, away])


def _coach_change_signal(schedule: pl.DataFrame) -> pl.DataFrame:
    """1 if a team's week-1 coach differs from its own final-game coach
    of the prior season; 0 if the prior season isn't in the loaded
    ``schedule``."""
    cur = _unpivot_teams(schedule, pl.col("week") == 1).select(
        "team", "season", "coach"
    )
    prior = (
        _unpivot_teams(schedule)
        .sort("week")
        .group_by("team", "season", maintain_order=True)
        .agg(pl.col("coach").last())
        .with_columns((pl.col("season") + 1).alias("season"))
        .rename({"coach": "prior_coach"})
    )
    return (
        cur.join(prior, on=["team", "season"], how="left")
        .with_columns(
            coach_change=(
                pl.col("prior_coach").is_not_null()
                & (pl.col("coach") != pl.col("prior_coach"))
            ).cast(pl.Int8)
        )
        .select("team", "season", "coach_change")
    )


def _first_rounders_signal(draft: pl.DataFrame) -> pl.DataFrame:
    """Count of round-1 picks per (team, season). Historic abbrevs
    (OAK/SD/STL, ...) go through ``standardize_teams`` first."""
    return (
        draft.filter(pl.col("round") == 1)
        .with_columns(
            pl.col("team").map_elements(standardize_teams, return_dtype=pl.String)
        )
        .group_by("team", "season")
        .agg(first_rounders=pl.len())
    )


def team_discontinuity(
    pbp: pl.DataFrame, schedule: pl.DataFrame, draft: pl.DataFrame
) -> pl.DataFrame:
    """Per (team, season) discontinuity count (#47): ``qb_change`` (0/1,
    weeks 1-3 primary passer vs prior season's) + ``coach_change`` (0/1,
    week-1 coach vs prior season's final-game coach) + ``first_rounders``
    (count of round-1 picks that season).

    Signals use only weeks 1-3 pbp and the week-1 coach — both known
    pre-kickoff of week 1 — plus the current season's completed draft
    (known before week 1). Predictions start at ``min_week=4`` and the
    matrix lags stats 1 week, so this is leak-safe. Teams/seasons missing
    a prior-season row (earliest loaded season) get 0 for that signal,
    not an error — this frame is built from whatever ``pbp``/``schedule``
    the feature build already has, no extra fetch.
    """
    reg_schedule = schedule.filter(pl.col("game_type") == "REG")
    universe = pl.concat(
        [
            reg_schedule.select(pl.col("home_team").alias("team"), "season"),
            reg_schedule.select(pl.col("away_team").alias("team"), "season"),
        ]
    ).unique()
    return (
        universe.join(_qb_change_signal(pbp), on=["team", "season"], how="left")
        .join(_coach_change_signal(schedule), on=["team", "season"], how="left")
        .join(_first_rounders_signal(draft), on=["team", "season"], how="left")
        .with_columns(
            pl.col("qb_change").fill_null(0),
            pl.col("coach_change").fill_null(0),
            pl.col("first_rounders").fill_null(0),
        )
        .with_columns(
            disc_count=(
                pl.col("qb_change") + pl.col("coach_change") + pl.col("first_rounders")
            )
        )
        .select("team", "season", "disc_count")
    )


def continuity_from_discontinuity(disc: pl.DataFrame, c: float) -> pl.DataFrame:
    """``continuity = c ** disc_count`` per (team, season) — c=1.0
    reproduces the flat continuity=1.0 baseline exactly (1**anything=1)."""
    return disc.select("team", "season", continuity=pl.lit(c).pow(pl.col("disc_count")))


def add_carryover(
    rolled: pl.DataFrame, k: float, continuity: float | pl.DataFrame = 1.0
) -> pl.DataFrame:
    """Augment flat windowed rows with prior-season carryover rate cols.

    ``rolled`` is the per-team-week frame *before* grid expansion, carrying the
    L1 ``{stat}_season`` cumulative cols (see ``windows.add_windows``). For each
    rate (``*_mean``) season col we form a season-to-date per-game rate
    (``_season`` cumulative / games played to date), look up the team's
    prior-season *final* per-game rate, and blend the two via
    ``carryover_blend``. One ``{stat}_carry`` col per rate stat is appended;
    volume and other cols are untouched. The 1-week lag in `matrix` keeps this
    leak-safe, and the prior season is wholly in the past.

    ``continuity`` is either the flat scalar (default, unchanged behaviour)
    or a per-(team, season) DataFrame (cols ``team, season, continuity`` —
    see ``continuity_from_discontinuity``), left-joined onto ``rolled`` and
    used as a row expr; teams/seasons missing a row default to 1.0 (no
    discount).
    """
    rate_season = [c for c in rolled.columns if "_mean" in c and c.endswith("_season")]
    if not rate_season:
        return rolled

    df = rolled.sort("team", "season", "week").with_columns(
        pl.int_range(1, pl.len() + 1).over("team", "season").alias("_games")
    )
    df = df.with_columns(
        *[(pl.col(c) / pl.col("_games")).alias(f"{c}__rate") for c in rate_season]
    )

    # prior-season final rate = each team-season's last week's rate, mapped
    # forward one season
    rate_names = [f"{c}__rate" for c in rate_season]
    finals = (
        df.group_by("team", "season")
        .agg(*[pl.col(n).sort_by("week").last() for n in rate_names])
        .with_columns((pl.col("season") + 1).alias("season"))
        .rename({n: f"{n}__prior" for n in rate_names})
    )
    df = df.join(finals, on=["team", "season"], how="left")

    if isinstance(continuity, pl.DataFrame):
        df = df.join(continuity, on=["team", "season"], how="left").with_columns(
            pl.col("continuity").fill_null(1.0)
        )
        continuity_arg: float | pl.Expr = pl.col("continuity")
    else:
        continuity_arg = continuity

    carry = [
        carryover_blend(
            pl.col(f"{c}__rate"),
            pl.col(f"{c}__rate__prior"),
            pl.col("_games"),
            k,
            continuity_arg,
        ).alias(c.removesuffix("_season") + "_carry")
        for c in rate_season
    ]
    return df.with_columns(carry).select(*rolled.columns, cs.ends_with("_carry"))
