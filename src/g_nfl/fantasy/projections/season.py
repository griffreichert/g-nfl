"""Season-long fantasy projections (input layer for PAR draft board, issue #30).

Blends per-season PPG across N prior seasons with recency weights, renormalised
for players missing some seasons.  Output is one row per player ready for #31.
"""

from __future__ import annotations

import nflreadpy as nfl
import polars as pl

FANTASY_POSITIONS: set[str] = {"QB", "RB", "WR", "TE", "FB"}

# ponytail: FB is rare and scores like RB; collapse rather than add a position slot.
_FB_TO_RB: dict[str, str] = {"FB": "RB"}

DEFAULT_WEIGHTS: tuple[float, ...] = (0.6, 0.3, 0.1)
# ponytail: flat 17-game denominator — availability / injury modeling deferred to #31.
DEFAULT_GAMES: int = 17
# Drop player-seasons under this many games: a tiny sample (e.g. a 1-game backup)
# inflates per-game scoring and ranks like a starter. Whole-player drops out if all
# their seasons are thin.
DEFAULT_MIN_GAMES: int = 6

_SCORING_OPTIONS = {"standard", "ppr", "half"}


def load_player_seasons(seasons: list[int]) -> pl.DataFrame:
    """Load and normalize player season stats via nflreadpy.

    Filters to FANTASY_POSITIONS (drops null positions), maps FB -> RB,
    selects the columns needed downstream.
    """
    raw: pl.DataFrame = nfl.load_player_stats(seasons=seasons, summary_level="reg")

    return (
        raw.filter(pl.col("position").is_in(FANTASY_POSITIONS))
        .with_columns(pl.col("position").replace(_FB_TO_RB).alias("position"))
        .select(
            "player_id",
            "player_name",
            "position",
            "recent_team",
            "season",
            "games",
            "fantasy_points",
            "fantasy_points_ppr",
        )
    )


def _points_expr(scoring: str) -> pl.Expr:
    """Fantasy-points expression for the given scoring type."""
    if scoring not in _SCORING_OPTIONS:
        raise ValueError(f"scoring must be one of {_SCORING_OPTIONS}, got {scoring!r}")

    if scoring == "standard":
        return pl.col("fantasy_points")
    elif scoring == "ppr":
        return pl.col("fantasy_points_ppr")
    else:  # half
        return (pl.col("fantasy_points") + pl.col("fantasy_points_ppr")) / 2


def _scored_ppg(
    df: pl.DataFrame, scoring: str, min_games: int = DEFAULT_MIN_GAMES
) -> pl.DataFrame:
    """Add a ``ppg`` column (fantasy points per game) for the given scoring type.

    Player-seasons under ``min_games`` are dropped: a tiny sample inflates
    per-game scoring (a 1-game backup ranking like a starter). ``min_games=0``
    keeps everything with at least one game played.
    """
    pts = _points_expr(scoring)
    return (
        df.filter(pl.col("games") >= max(min_games, 1))
        .with_columns((pts / pl.col("games")).alias("ppg"))
        .filter(pl.col("ppg").is_not_null())
    )


def _recency_weighted(
    df: pl.DataFrame, value_col: str, weights: tuple[float, ...]
) -> pl.DataFrame:
    """Recency-weighted blend of ``value_col`` across each player's seasons.

    Sorts each player's seasons descending (most recent first), zips with
    ``weights`` in order, renormalises over seasons the player actually has.
    Returns one row per player: ``player_id``, ``blended_{value_col}``, ``n_seasons``.
    """
    # Rank each season per player by recency (1 = most recent)
    ranked = df.with_columns(
        pl.col("season")
        .rank(method="ordinal", descending=True)
        .over("player_id")
        .alias("_rank")
    )

    # Attach raw weight by rank index (rank 1 -> weights[0], etc.)
    # Ranks beyond len(weights) get weight 0 and will be excluded.
    max_rank = len(weights)
    weight_map = pl.DataFrame(
        {"_rank": list(range(1, max_rank + 1)), "_w": list(weights)},
        schema={"_rank": pl.Int32, "_w": pl.Float64},
    )

    joined = ranked.join(weight_map, on="_rank", how="left").with_columns(
        pl.col("_w").fill_null(0.0)
    )

    # Per-player: sum weights over present seasons (for renormalisation)
    player_wsum = joined.group_by("player_id").agg(pl.col("_w").sum().alias("_wsum"))

    blended_col = f"blended_{value_col}"
    return (
        joined.join(player_wsum, on="player_id", how="left")
        .with_columns(
            # renormalised contribution of each season row
            (pl.col(value_col) * pl.col("_w") / pl.col("_wsum")).alias("_contrib")
        )
        .group_by("player_id")
        .agg(
            pl.col("_contrib").sum().alias(blended_col),
            pl.col("season").count().alias("n_seasons"),
        )
    )


def blend_projections(
    df: pl.DataFrame,
    target_season: int,
    weights: tuple[float, ...],
    games: int,
) -> pl.DataFrame:
    """Pure blending step — takes an already-loaded frame with a ``ppg`` column.

    ``df`` must contain: player_id, player_name, position, recent_team, season, ppg.
    Seasons in ``df`` must all be < ``target_season``.
    """
    blended = _recency_weighted(df, "ppg", weights)
    meta = df.group_by("player_id").agg(
        pl.col("player_name").last(),
        pl.col("position").last(),
        # most recent team
        pl.col("recent_team").sort_by(pl.col("season")).last().alias("last_team"),
    )

    return (
        blended.join(meta, on="player_id", how="left")
        .rename({"blended_ppg": "proj_ppg"})
        .with_columns((pl.col("proj_ppg") * games).alias("proj_points"))
        .select(
            "player_id",
            "player_name",
            "position",
            "last_team",
            "n_seasons",
            "proj_ppg",
            "proj_points",
        )
        .sort("proj_points", descending=True)
    )


def project_season(
    seasons: list[int],
    target_season: int,
    *,
    scoring: str = "ppr",
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
    games: int = DEFAULT_GAMES,
    min_games: int = DEFAULT_MIN_GAMES,
) -> pl.DataFrame:
    """Project fantasy points for ``target_season`` from ``seasons`` of history.

    Args:
        seasons: Historical seasons to load; should be the N seasons immediately
            before ``target_season`` (length should equal len(weights), but extra
            seasons are allowed — weights renormalise).
        target_season: The season being projected (used only for the assertion).
        scoring: One of "standard", "ppr", "half".
        weights: Recency weights; index 0 = most recent prior season.
        games: Games to project over (flat; availability modeling deferred to #31).
        min_games: Drop player-seasons under this many games (tiny-sample filter).

    Returns:
        One row per player, sorted by proj_points descending.
    """
    assert all(s < target_season for s in seasons), (
        f"All seasons must be < target_season={target_season}"
    )

    raw = load_player_seasons(seasons)
    scored = _scored_ppg(raw, scoring, min_games)
    return blend_projections(scored, target_season, weights, games)


if __name__ == "__main__":
    TARGET = 2025
    SEASONS = [2022, 2023, 2024]

    print(f"Projecting {TARGET} from {SEASONS} (PPR, weights={DEFAULT_WEIGHTS})\n")

    proj = project_season(SEASONS, TARGET)

    print("=== Top 10 overall ===")
    print(
        proj.head(10).select(
            "player_name",
            "position",
            "last_team",
            "n_seasons",
            "proj_ppg",
            "proj_points",
        )
    )

    print("\n=== Top 5 per position ===")
    for pos in ["QB", "RB", "WR", "TE"]:
        top5 = proj.filter(pl.col("position") == pos).head(5)
        print(f"\n-- {pos} --")
        print(
            top5.select(
                "player_name", "last_team", "n_seasons", "proj_ppg", "proj_points"
            )
        )
