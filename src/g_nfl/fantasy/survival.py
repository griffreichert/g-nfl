"""Will he last until your next pick? (issue #99, split from #92c)

Replaces the board-order proxy in ``next_turn_outlook``. That proxy assumed the
next N picks take the next N players *on this board*, which assumes the room
drafts off this board — flattering, and wrong in exactly the place it matters,
since the players this board likes more than the market are the ones it claims
will not survive.

The model is deliberately plain: a player's draft position is normal around his
ADP, with the spread read off ``minPick``/``maxPick``, and survival is the tail
above your next pick. Resist making it fancy before it is useful.

**QB carries a measured caveat.** MyFantasyLeague pools superflex rooms into one
ADP feed and ignores every filter parameter tried (``IS_SF``, ``IS_SUPERFLEX``),
so quarterbacks come back far too early for a 1QB league: Josh Allen's 2026 ADP
is 2.8 against an ECR of 25.9. For QBs the consensus pick therefore comes from
FantasyPros ECR, which is published 1QB PPR and ships its own ``sd``.
"""

from __future__ import annotations

import math

import polars as pl

# Range of a normal covering roughly four standard deviations, used to turn
# MFL's min/max picks into a spread.
RANGE_TO_SD = 4.0

# No player is a certainty, and a zero spread would make survival a step
# function at his ADP.
MIN_PICK_SD = 1.5

# A player is "expected to be there" above this survival probability. Half is
# the honest reading of a coin-flip threshold: better than not.
SURVIVAL_THRESHOLD = 0.5


def consensus_pick(board: pl.DataFrame, adp: pl.DataFrame) -> pl.DataFrame:
    """Attach ``pick_mu`` and ``pick_sd``: where the room takes a player.

    ADP for skill positions, ECR for quarterbacks (see the module docstring for
    why). Players in neither source get no estimate and fall back to board order
    downstream.
    """
    joined = board.join(
        adp.select("gsis_id", "adp", "adp_min", "adp_max"), on="gsis_id", how="left"
    )
    is_qb = pl.col("position") == "QB"
    return joined.with_columns(
        pl.when(is_qb).then(pl.col("ecr")).otherwise(pl.col("adp")).alias("pick_mu"),
        pl.when(is_qb)
        .then(pl.col("sd"))
        .otherwise((pl.col("adp_max") - pl.col("adp_min")) / RANGE_TO_SD)
        .clip(lower_bound=MIN_PICK_SD)
        .alias("pick_sd"),
    ).drop("adp", "adp_min", "adp_max")


def survival(board: pl.DataFrame, pick: int) -> pl.DataFrame:
    """Attach ``p_available``: the chance a player is still there at ``pick``.

    ``1 - Phi((pick - mu) / sd)``, so a player whose ADP sits well before your
    pick is unlikely to last and one whose ADP is well after it almost certainly
    will. Players with no consensus estimate get a null, not a guess.
    """
    z = (pl.lit(float(pick)) - pl.col("pick_mu")) / pl.col("pick_sd")
    normal_cdf = 0.5 * (
        1 + (z / math.sqrt(2)).map_batches(_erf, return_dtype=pl.Float64)
    )
    return board.with_columns(
        pl.when(pl.col("pick_mu").is_null())
        .then(None)
        .otherwise((1 - normal_cdf).clip(0.0, 1.0))
        .alias("p_available")
    )


def _erf(s: pl.Series) -> pl.Series:
    """``math.erf`` over a series; polars has no erf expression."""
    return pl.Series([None if v is None else math.erf(v) for v in s], dtype=pl.Float64)


def best_expected_available(
    board: pl.DataFrame, pick: int, threshold: float = SURVIVAL_THRESHOLD
) -> pl.DataFrame:
    """Top player per position more likely than not to reach ``pick``.

    Falls back to board order for anyone the sources do not cover, which is the
    deep end of the board where the old proxy was least wrong anyway.
    """
    survivors = survival(board, pick).filter(
        pl.col("p_available").is_null() | (pl.col("p_available") >= threshold)
    )
    return (
        survivors.sort("ppgar", descending=True)
        .group_by("position", maintain_order=True)
        .first()
    )
