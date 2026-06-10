"""Named feature sets, so models declare what they train on by name.

A feature set selects columns from the game matrix; the name gets
persisted with trained models (#10/#12) so predictions rebuild the
exact same inputs.
"""

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

FEATURE_SETS: dict[str, FeatureSet] = {fs.name: fs for fs in [V1_TEAM]}


def get_feature_set(name: str) -> FeatureSet:
    try:
        return FEATURE_SETS[name]
    except KeyError:
        raise KeyError(
            f"unknown feature set {name!r}; available: {sorted(FEATURE_SETS)}"
        ) from None
