"""L2 prior-season carryover: shrink thin early-season rates toward the
team's prior-season final rate, decaying as games accumulate.

Early in a season a team's season-to-date stats are noisy (1-2 games). Blending
toward last season's settled rate stabilises them; the weight on the prior
decays as the current season fills in. Augments the flat L1 ``{stat}_season``
cols with one ``{stat}_carry`` col per rate stat (try augment before replace).
"""

import polars as pl
import polars.selectors as cs


def carryover_blend(
    cur: pl.Expr, prior: pl.Expr, games: pl.Expr, k: float, continuity: float = 1.0
) -> pl.Expr:
    """Blend a current rate toward a prior rate.

    ``w = k / (k + games) * continuity`` is the weight on ``prior`` — high when
    ``games`` is small (``k`` pseudo-games of prior), decaying to ~0 as the
    season fills in. Missing ``prior`` (e.g. a relocated team with no prior row
    in the window) falls back to ``cur`` unchanged (w=0).
    """
    # ponytail: continuity is a flat 1.0 hook for future QB/coach signal (same
    # QB+coach -> keep more prior). Wire it at L3/L4 when that data exists; do
    # not build it now -- there is no QB/coach data at L2.
    w = (k / (k + games)) * continuity
    blended = w * prior + (1 - w) * cur
    return pl.when(prior.is_null()).then(cur).otherwise(blended)


def add_carryover(
    rolled: pl.DataFrame, k: float, continuity: float = 1.0
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

    carry = [
        carryover_blend(
            pl.col(f"{c}__rate"),
            pl.col(f"{c}__rate__prior"),
            pl.col("_games"),
            k,
            continuity,
        ).alias(c.removesuffix("_season") + "_carry")
        for c in rate_season
    ]
    return df.with_columns(carry).select(*rolled.columns, cs.ends_with("_carry"))
