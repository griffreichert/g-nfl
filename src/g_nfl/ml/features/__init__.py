"""Feature engineering: play-level features, weekly team aggregates,
rolling windows, and the game-level training matrix.

Modules:
- plays: pbp filters + play-level features (havoc, explosive, ...)
- team_week: weekly offense/defense team aggregates
- windows: season-to-date + rolling windows with forward fill
- matrix: home/away join onto schedule with 1-week lag
- registry: named, versioned feature sets
"""

import numpy as np
import polars as pl

from g_nfl.ml.features.availability import add_availability
from g_nfl.ml.features.carryover import (
    continuity_from_discontinuity,
    team_discontinuity,
)
from g_nfl.ml.features.context import add_schedule_context
from g_nfl.ml.features.continuity import add_continuity
from g_nfl.ml.features.injuries import add_injuries
from g_nfl.ml.features.matrix import build_game_matrix
from g_nfl.ml.features.opponent import add_opponent_ratings, team_games_frame
from g_nfl.ml.features.plays import play_features
from g_nfl.ml.features.preseason import add_preseason, preseason_features
from g_nfl.ml.features.qb import add_qb_context
from g_nfl.ml.features.qb_change import add_qb_change
from g_nfl.ml.features.team_week import team_week_stats
from g_nfl.ml.features.windows import DEFAULT_ROLLING_WEEKS, add_windows
from g_nfl.ml.odds import add_ml_odds
from g_nfl.utils.config import DEFAULT_WIN_PROB


def build_features(
    pbp: pl.DataFrame,
    schedule: pl.DataFrame,
    *,
    wp_filter: float = DEFAULT_WIN_PROB,
    rolling_weeks: int = DEFAULT_ROLLING_WEEKS,
    min_week: int | None = None,
    half_life: float | None = None,
    epa_splits: bool = False,
    carryover_k: float | None = None,
    carryover_c: float | None = None,
    draft: pl.DataFrame | None = None,
    injuries: pl.DataFrame | None = None,
    schedule_ctx: bool = False,
    qb_ctx: bool = False,
    qb_change: pl.DataFrame | None = None,
    snaps: pl.DataFrame | None = None,
    continuity: bool = False,
    ml_odds: bool = False,
    ml_margins: np.ndarray | None = None,
    availability: pl.DataFrame | None = None,
    players: pl.DataFrame | None = None,
    preseason: bool = False,
    rosters: pl.DataFrame | None = None,
    opp_adjust: bool = False,
    opp_lambda: float = 10.0,
    opp_prior_weight: float = 0.3,
) -> pl.DataFrame:
    """Full pipeline: raw pbp + schedule -> game-level training matrix.

    ``half_life`` set switches the windowing to L2 time decay (EWMA over
    games, rate cols only); None keeps the L1 flat rolling/season cols.
    ``epa_splits`` adds the L2 pass/rush/early-down EPA features.
    ``carryover_k`` (flat path) adds prior-season-carryover ``_carry`` rate
    cols (pseudo-games of prior; see `carryover.add_carryover`).
    ``carryover_c`` (#47) discounts that carryover per-team-season by
    discontinuity (new QB / new coach / round-1 infusion — see
    `carryover.team_discontinuity`); requires ``carryover_k`` set and
    ``draft`` passed (that season's round-1 picks), None keeps the flat
    continuity=1.0 baseline.
    ``injuries`` (L3) joins home/away team-week injury burden, no lag
    (see `injuries.add_injuries`); None leaves the matrix unchanged.
    ``schedule_ctx`` (L3) appends rest/day-of-week/division context, no lag
    (see `context.add_schedule_context`).
    ``qb_ctx`` (L4) attaches each team's starting-QB lagged EWMA/volume
    keyed on the player (see `qb.add_qb_context`); requires ``pbp`` to
    carry prior-season lookback to warm the EWMA.
    ``qb_change`` (L4) attaches the injury-report-triggered QB-change
    delta (see `qb_change.add_qb_change`); pass the raw player-level
    injuries DataFrame to turn it on (None leaves the matrix unchanged,
    same toggle convention as ``snaps``). Needs the same prior-season
    ``pbp`` lookback as ``qb_ctx`` to warm the EWMA.
    ``snaps`` is the raw snap-counts DataFrame, shared data for two
    independent L4 toggles: ``continuity`` (O-line lineup stability,
    `continuity.add_continuity`) and ``availability`` (below). Pass
    ``snaps`` whenever either is on.
    ``ml_odds`` (L4) attaches the moneyline-implied spread + its divergence
    from the posted line (see `odds.add_ml_odds`); market data, no lag.
    ``ml_margins`` calibrates the implied-spread margin distribution from a
    deep, strictly-prior reference (passed by the caller); None falls back to
    self-calibration on the matrix's own completed games.
    ``availability`` (L4, #39 lever 2) is the raw injuries DataFrame used as
    the toggle (same convention as ``qb_change`` — keeps it independent of
    the L3 ``injuries`` lever); attaches availability-weighted unit
    snap-value lost (see `availability.add_availability`); needs ``snaps``,
    ``injuries``, and ``players`` (the gsis_id/pfr_id crosswalk) all passed.
    ``preseason`` attaches the pre-week-1 team block (prior-season form,
    prior-season market rating, coach/QB change, draft capital, snap
    retention — see `preseason.preseason_features`), joined with no lag
    and constant within a season. Needs ``pbp``/``schedule`` to carry one
    prior season; ``draft`` adds the capital cols and ``snaps`` +
    ``rosters`` the retention col.
    ``opp_adjust`` (L4) attaches opponent-adjusted offense/defense ratings
    per stat (see `opponent.add_opponent_ratings`), fit strictly on weeks
    before the game plus the prior season; requires ``pbp`` to carry prior-
    season lookback to warm week-1 ratings (same mechanism as ``qb_ctx``).
    """
    if carryover_c is not None and carryover_k is None:
        raise ValueError("carryover_c requires carryover_k set")
    reg_schedule = schedule.filter(pl.col("game_type") == "REG")
    plays = play_features(pbp, wp_filter, epa_splits=epa_splits)
    weekly = team_week_stats(plays)
    carryover_continuity: float | pl.DataFrame = 1.0
    if carryover_c is not None:
        disc = team_discontinuity(pbp, reg_schedule, draft)
        carryover_continuity = continuity_from_discontinuity(disc, carryover_c)
    windowed = add_windows(
        weekly,
        reg_schedule,
        rolling_weeks,
        half_life=half_life,
        carryover_k=carryover_k,
        carryover_continuity=carryover_continuity,
    )
    matrix = build_game_matrix(
        windowed,
        reg_schedule,
        rolling_weeks,
        min_week=min_week,
        half_life=half_life,
        carryover_k=carryover_k,
    )
    if injuries is not None:
        matrix = add_injuries(matrix, injuries)
    if schedule_ctx:
        matrix = add_schedule_context(matrix, reg_schedule)
    if qb_ctx:
        matrix = add_qb_context(matrix, pbp, reg_schedule)
    if qb_change is not None:
        matrix = add_qb_change(matrix, pbp, qb_change)
    if continuity:
        matrix = add_continuity(matrix, snaps)
    if ml_odds:
        matrix = add_ml_odds(matrix, reg_schedule, margins=ml_margins)
    if availability is not None:
        matrix = add_availability(matrix, snaps, availability, players)
    if preseason:
        matrix = add_preseason(
            matrix,
            preseason_features(pbp, schedule, draft, snaps, rosters, players),
        )
    if opp_adjust:
        matrix = add_opponent_ratings(
            matrix, team_games_frame(plays), opp_lambda, opp_prior_weight
        )
    return matrix
