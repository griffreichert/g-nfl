"""Named feature sets, so models declare what they train on by name.

A feature set selects columns from the game matrix; the name gets
persisted with trained models (#10/#12) so predictions rebuild the
exact same inputs.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from g_nfl.ml.features.availability import AVAIL_COLS
from g_nfl.ml.features.matrix import META_COLS
from g_nfl.ml.features.preseason import PRESEASON_PREFIX
from g_nfl.ml.features.qb_change import QB_CHANGE_COLS

# qb_change cols ride the matrix for the additive prediction adjustment
# (qb_adjust_k) but are never training features: as tree inputs they are
# rare-nonzero soup that measurably *hurts* subset sharpness (#41).
# availability cols (#39 lever 2) are spec'd the same way from the start --
# an additive/prior correction, not tree soup -- so they ride the matrix as
# adjustment inputs only, same exclusion.
ADJUSTMENT_COLS = {
    f"{side}_{c}" for side in ("home", "away") for c in (*QB_CHANGE_COLS, *AVAIL_COLS)
}


@dataclass(frozen=True)
class FeatureSet:
    name: str
    description: str
    selector: Callable[[pl.DataFrame], list[str]]

    def columns(self, matrix: pl.DataFrame) -> list[str]:
        """Feature column names this set selects from the game matrix."""
        return self.selector(matrix)


def _is_preseason(col: str) -> bool:
    """Preseason block columns: `pre_diff_*` and the `home_`/`away_`-prefixed
    per-side ones (see `features.preseason`)."""
    return col.startswith(PRESEASON_PREFIX) or col.removeprefix("home_").removeprefix(
        "away_"
    ).startswith(PRESEASON_PREFIX)


def _is_opponent_adjusted(col: str) -> bool:
    """Opponent-adjustment output (`opponent.add_opponent_ratings`)."""
    return "_adj_" in col or col == "adj_rating_diff"


def _all_team_stat_cols(matrix: pl.DataFrame) -> list[str]:
    """Every in-season team column. Excludes the preseason block so that
    building the matrix with ``preseason=True`` does not silently change
    what ``v1_team`` means -- ``v3_early`` is the set that wants it.
    Excludes the opponent-adjustment block for the same reason: building
    with ``opp_adjust=True`` must not change what the other sets mean, and
    ``v5_early_adj`` takes only the one netted column it measured as
    better than the rest."""
    return [
        c
        for c in matrix.columns
        if c not in META_COLS
        and c not in ADJUSTMENT_COLS
        and not _is_preseason(c)
        and not _is_opponent_adjusted(c)
    ]


V1_TEAM = FeatureSet(
    name="v1_team",
    description=(
        "All home/away season-to-date and rolling team aggregates, "
        "as in notebooks/model/01 + 02."
    ),
    selector=_all_team_stat_cols,
)

# L2 finding (notes/modelling/l1-feature-importance.md): the full stat soup
# is flat and redundant. The lean core keeps just the rate stats that
# actually carry gain, both home/away, offense/defense, season + rolling.
_LEAN_STEMS = [
    "epa_mean",
    "success_mean",
    "cpoe_mean",
    "pass_oe_mean",
    "sack_mean",
    "first_down_mean",
]


def _adj_cols(matrix: pl.DataFrame) -> list[str]:
    """Opponent-adjustment columns (`opponent.add_opponent_ratings`):
    the 12 `_adj_` off/def rating cols plus `adj_rating_diff`."""
    cols = [c for c in matrix.columns if "_adj_" in c]
    if "adj_rating_diff" in matrix.columns:
        cols.append("adj_rating_diff")
    if not cols:
        raise ValueError(
            "no opponent-adjustment columns found in matrix; build it with "
            "opp_adjust=True (build_features/backtest) before using this "
            "feature set"
        )
    return cols


def _adj_lean_cols(matrix: pl.DataFrame) -> list[str]:
    """Adj cols plus a lean home/away, season/rolling, off/def core of the
    top rate stats from the L1 importance findings, in place of the full
    stat soup (`_LEAN_STEMS`)."""
    stem_pattern = re.compile(
        r"^(?:home|away)_(?:" + "|".join(re.escape(s) for s in _LEAN_STEMS) + r")"
        r"(?:_def)?_(?:season|last_\d+w)$"
    )
    lean = [c for c in matrix.columns if stem_pattern.match(c)]
    return _adj_cols(matrix) + lean


V2_ADJ_ONLY = FeatureSet(
    name="v2_adj_only",
    description="Just the opponent-adjusted off/def ratings (13 cols).",
    selector=_adj_cols,
)

V2_ADJ_LEAN = FeatureSet(
    name="v2_adj_lean",
    description=(
        "Opponent-adjusted ratings plus a lean core of top rate features "
        "(epa/success/cpoe/pass_oe/sack/first_down mean, season + rolling, "
        "off + def), replacing the full v1_team stat soup."
    ),
    selector=_adj_lean_cols,
)


def _early_cols(matrix: pl.DataFrame) -> list[str]:
    """In-season columns plus the preseason block plus ``week``.

    In week 1 every in-season column is null (the matrix lags a week and
    week 0 does not exist), so without the preseason block the model
    returns one constant for the whole slate -- see
    `notes/modelling/early-weeks.md`. Requires a matrix built with
    ``preseason=True``.
    """
    pre = [c for c in matrix.columns if _is_preseason(c)]
    if not pre:
        raise ValueError(
            "no preseason columns in matrix; build it with preseason=True "
            "(build_features/backtest) before using this feature set"
        )
    week = ["week"] if "week" in matrix.columns else []
    return _all_team_stat_cols(matrix) + pre + week


V3_EARLY = FeatureSet(
    name="v3_early",
    description=(
        "v1_team plus the preseason block (prior-season form and market "
        "rating, coach/QB change, draft capital, snap retention) and week. "
        "The early-regime set: weeks 1-4, where in-season stats are null or "
        "one game deep."
    ),
    selector=_early_cols,
)

# The four-week rolling window is noise, measured. Dropping the 132
# `_last_{n}w` columns from v3_early (422 -> 298 features) improves MAE
# against the close by 0.038 (t=+2.63, paired on 2687 games) and against
# the actual result by 0.029 (t=+1.91) -- the only prune all session to
# move the result metric at all. The gain is specific to this family: a
# same-size gain-ranked cut across all families was +0.012 (t=+0.8), and
# removing `_carry` instead *costs* 0.025 (t=-1.65). Weeks 2-4 carry it
# (+0.080, t=+2.66), which is where a four-week window is mostly padding
# from a one- or two-game season. See `notes/modelling/feature-space.md`.
_ROLLING_RE = re.compile(r"_last_\d+w$")


def _lean_early_cols(matrix: pl.DataFrame) -> list[str]:
    """`v3_early` without the rolling-window family."""
    return [c for c in _early_cols(matrix) if not _ROLLING_RE.search(c)]


V4_EARLY_LEAN = FeatureSet(
    name="v4_early_lean",
    description=(
        "v3_early minus the `_last_{n}w` rolling-window columns: "
        "season-to-date and prior-season carryover only, plus the "
        "preseason block, QB context and week."
    ),
    selector=_lean_early_cols,
)

# Opponent adjustment, as ONE netted column. `adj_rating_diff` is
# (home_off + away_def) - (away_off + home_def), which is the quantity that
# maps to a point spread, and handing the tree the pieces instead is worse:
# paired on 2687 games it beats the champion by 0.087 MAE against the close
# (t=+4.48), while all 13 ratings manage +0.071 and splitting into off/def
# diffs *costs* 0.041 (t=-2.56, weeks 2-4 worst at -0.116). Strength of
# schedule faced is redundant on top of it (-0.019) -- the ridge already
# conditions each rating on the opponents played.
#
# The off/def split is still worth knowing even though it does not ship:
# `epa_off_diff` carries 9.59% of gain against `epa_def_diff`'s 4.06%, so
# offence outweighs defence 2.4:1 in rating a team.
#
# Pays late, not early: weeks 9+ +0.112 (t=+3.98), week 1 +0.018 (t=0.24).
# In week 1 the ridge trains on the prior season alone, so it restates what
# the preseason block already carries. Buys nothing against the actual
# result (-0.001), same wall as everything else.
# See `notes/modelling/opponent-adjustment.md`.


def _early_adj_cols(matrix: pl.DataFrame) -> list[str]:
    """`v4_early_lean` plus the single netted opponent-adjustment column."""
    if "adj_rating_diff" not in matrix.columns:
        raise ValueError(
            "no adj_rating_diff in matrix; build it with opp_adjust=True "
            "(build_features/backtest) before using this feature set"
        )
    return _lean_early_cols(matrix) + ["adj_rating_diff"]


V5_EARLY_ADJ = FeatureSet(
    name="v5_early_adj",
    description=(
        "v4_early_lean plus adj_rating_diff, the netted opponent-adjusted "
        "off/def rating difference from the per-week ridge."
    ),
    selector=_early_adj_cols,
)

FEATURE_SETS: dict[str, FeatureSet] = {
    fs.name: fs
    for fs in [V1_TEAM, V2_ADJ_ONLY, V2_ADJ_LEAN, V3_EARLY, V4_EARLY_LEAN, V5_EARLY_ADJ]
}


def get_feature_set(name: str) -> FeatureSet:
    try:
        return FEATURE_SETS[name]
    except KeyError:
        raise KeyError(
            f"unknown feature set {name!r}; available: {sorted(FEATURE_SETS)}"
        ) from None
