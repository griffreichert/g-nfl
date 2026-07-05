"""Named feature sets, so models declare what they train on by name.

A feature set selects columns from the game matrix; the name gets
persisted with trained models (#10/#12) so predictions rebuild the
exact same inputs.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from g_nfl.ml.features.matrix import META_COLS


@dataclass(frozen=True)
class FeatureSet:
    name: str
    description: str
    selector: Callable[[pl.DataFrame], list[str]]

    def columns(self, matrix: pl.DataFrame) -> list[str]:
        """Feature column names this set selects from the game matrix."""
        return self.selector(matrix)


def _all_team_stat_cols(matrix: pl.DataFrame) -> list[str]:
    return [c for c in matrix.columns if c not in META_COLS]


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

FEATURE_SETS: dict[str, FeatureSet] = {
    fs.name: fs for fs in [V1_TEAM, V2_ADJ_ONLY, V2_ADJ_LEAN]
}


def get_feature_set(name: str) -> FeatureSet:
    try:
        return FEATURE_SETS[name]
    except KeyError:
        raise KeyError(
            f"unknown feature set {name!r}; available: {sorted(FEATURE_SETS)}"
        ) from None
