"""Per-route receiving efficiency for WR/TE projections (issue #34).

Derives a routes-run *proxy* from nflreadpy participation data (free, no PFF/
FantasyPoints needed) and folds it into TPRR / YPRR / 1DRR efficiency rates.

The proxy is every offensive player on the field for a pass play
(`participation.offense_players`, joined against pbp pass attempts) — not true
charted routes. `participation.route` is a red herring: it charts the
*targeted receiver's* route type per play, not a per-player route-run flag.

Validated against PFF's 2023 published numbers:
- WR: accurate (CeeDee Lamb proxy TPRR 27.6% vs PFF ~27.4%, YPRR 2.67 vs ~2.59).
- TE: biased high ~10-15% for in-line/blocking TEs (Kittle, Njoku) — the proxy
  can't separate route-run snaps from pass-pro snaps. Cleaner for flex TEs.
- RB: unusable (CMC proxy 545 "routes" vs PFF's real ~350) — RBs spend most
  pass downs blocking. Scoped out; RB stays on the #30 PPG projection.

The ``apply_efficiency_adjustment`` / ``project_season_with_efficiency`` path
(z-score proj_ppg bump vs position peers) backtested mixed/negative on a
single 2022-23 -> 2024 holdout (TE top-12 +1 hit but worse MAE both
positions; WR unchanged hit-rate, worse MAE) — NOT promoted as trustworthy.
The #31 draft board uses ``blend_efficiency_rates`` instead: raw TPRR/YPRR/
1DRR as diagnostic columns, no automatic ppg adjustment.
"""

from __future__ import annotations

import nflreadpy as nfl
import polars as pl

from g_nfl.fantasy.projections.season import (
    DEFAULT_GAMES,
    DEFAULT_WEIGHTS,
    _points_expr,
    _recency_weighted,
    project_season,
)

EFFICIENCY_POSITIONS: set[str] = {"WR", "TE"}

# Drop player-seasons under this many routes: mirrors season.py's
# DEFAULT_MIN_GAMES floor — a tiny route sample makes pprr noisy.
DEFAULT_MIN_ROUTES: int = 50

# proj_ppg *= (1 + DEFAULT_Z_STRENGTH * pprr_z): a 1-std-dev efficiency edge
# over position peers is roughly an 8% ppg bump. ponytail: arbitrary starting
# point, tune via backtest before trusting it.
DEFAULT_Z_STRENGTH: float = 0.08

# Clip pprr_z before applying it — caps the swing from a small-sample outlier.
Z_CLIP: float = 2.5


def load_routes_pbp(seasons: list[int]) -> pl.DataFrame:
    """Pass-play rows (game_id, play_id, season) to drive the routes-run proxy."""
    pbp: pl.DataFrame = nfl.load_pbp(seasons=seasons)
    return pbp.filter(pl.col("pass_attempt") == 1).select(
        "game_id", "play_id", "season"
    )


def load_participation(seasons: list[int]) -> pl.DataFrame:
    """Participation rows needed for the routes-run proxy."""
    part: pl.DataFrame = nfl.load_participation(seasons=seasons)
    return part.select(
        pl.col("nflverse_game_id").alias("game_id"), "play_id", "offense_players"
    )


def compute_routes_proxy(
    pass_plays: pl.DataFrame, participation: pl.DataFrame
) -> pl.DataFrame:
    """Routes-run proxy per player per season.

    Counts every pass play a player was on the field for offense (per
    ``offense_players``), restricted to dropbacks via ``pass_plays``.
    """
    joined = pass_plays.join(participation, on=["game_id", "play_id"], how="inner")
    return (
        joined.with_columns(pl.col("offense_players").str.split(";"))
        .explode("offense_players")
        .rename({"offense_players": "player_id"})
        .group_by("player_id", "season")
        .agg(pl.len().alias("routes_proxy"))
    )


def compute_efficiency(
    routes: pl.DataFrame, player_stats: pl.DataFrame
) -> pl.DataFrame:
    """TPRR / YPRR / 1DRR per player-season, WR/TE only.

    ``player_stats`` needs: player_id, player_name, position, season, targets,
    receiving_yards, receiving_first_downs (load_player_stats reg-season cols).
    """
    return (
        routes.join(player_stats, on=["player_id", "season"], how="inner")
        .filter(pl.col("position").is_in(EFFICIENCY_POSITIONS))
        .with_columns(
            (pl.col("targets") / pl.col("routes_proxy")).alias("tprr"),
            (pl.col("receiving_yards") / pl.col("routes_proxy")).alias("yprr"),
            (pl.col("receiving_first_downs") / pl.col("routes_proxy")).alias("fdrr"),
        )
        .select(
            "player_id",
            "player_name",
            "position",
            "season",
            "routes_proxy",
            "tprr",
            "yprr",
            "fdrr",
        )
        .sort("yprr", descending=True)
    )


def load_efficiency(seasons: list[int]) -> pl.DataFrame:
    """Orchestrate: load pbp + participation + player_stats, compute efficiency."""
    pass_plays = load_routes_pbp(seasons)
    participation = load_participation(seasons)
    routes = compute_routes_proxy(pass_plays, participation)

    stats: pl.DataFrame = nfl.load_player_stats(
        seasons=seasons, summary_level="reg"
    ).select(
        "player_id",
        "player_name",
        "position",
        "season",
        "targets",
        "receiving_yards",
        "receiving_first_downs",
    )
    return compute_efficiency(routes, stats)


# ---------------------------------------------------------------------------
# Augmenting season.py's PPG projection (issue #34, "augment" path)
#
# First cut multiplied a blended efficiency rate (pprr) back by a blended
# volume estimate (routes_per_game) derived from the *same* player's own
# route history. That's circular: pprr * routes_per_game = points / games =
# ppg exactly, per season, by construction — multiplying two separately
# blended averages back together doesn't add information, it just
# reconstructs ppg plus noise from the season-to-season covariance between
# efficiency and volume. Caught live (deltas were ~0.01-0.08 ppg, not signal).
#
# Fix: don't reconstruct volume at all. Compare each player's blended pprr to
# the WR/TE positional average (z-score) and use that as a quality bump/fade
# on top of the existing PPG blend's own volume assumption — additive
# correction, not reconstruction.
# ---------------------------------------------------------------------------


def load_efficiency_inputs(seasons: list[int]) -> pl.DataFrame:
    """Routes-proxy joined to player-season stats, WR/TE only, games > 0.

    Needs ``games`` + raw points columns, unlike the rate-only
    ``compute_efficiency``/``load_efficiency`` path above.
    """
    pass_plays = load_routes_pbp(seasons)
    participation = load_participation(seasons)
    routes = compute_routes_proxy(pass_plays, participation)

    stats: pl.DataFrame = nfl.load_player_stats(
        seasons=seasons, summary_level="reg"
    ).select(
        "player_id",
        "player_name",
        "position",
        "season",
        "games",
        "fantasy_points",
        "fantasy_points_ppr",
        "targets",
        "receiving_yards",
        "receiving_first_downs",
    )
    return (
        routes.join(stats, on=["player_id", "season"], how="inner")
        .filter(pl.col("position").is_in(EFFICIENCY_POSITIONS))
        .filter(pl.col("games") > 0)
    )


def _scored_efficiency(
    df: pl.DataFrame, scoring: str, min_routes: int = DEFAULT_MIN_ROUTES
) -> pl.DataFrame:
    """Add ``pprr`` (fantasy points per route run); drop thin route samples."""
    pts = _points_expr(scoring)
    return df.filter(pl.col("routes_proxy") >= min_routes).with_columns(
        (pts / pl.col("routes_proxy")).alias("pprr")
    )


def blend_efficiency(scored: pl.DataFrame, weights: tuple[float, ...]) -> pl.DataFrame:
    """Pure blending step — takes an already-scored frame (``_scored_efficiency``
    output), recency-blends ``pprr`` per player, and z-scores it against
    WR/TE position peers (``pprr_z``, clipped to +-``Z_CLIP``).
    """
    pprr_blend = _recency_weighted(scored, "pprr", weights)
    meta = scored.group_by("player_id").agg(
        pl.col("player_name").last(), pl.col("position").last()
    )

    mean_pos = pl.col("pprr_proj").mean().over("position")
    std_pos = pl.col("pprr_proj").std(ddof=0).over("position")
    z_expr = (
        pl.when(std_pos > 0)
        .then((pl.col("pprr_proj") - mean_pos) / std_pos)
        .otherwise(0.0)
        .clip(-Z_CLIP, Z_CLIP)
    )

    return (
        pprr_blend.join(meta, on="player_id", how="left")
        .rename({"blended_pprr": "pprr_proj"})
        .with_columns(z_expr.alias("pprr_z"))
        .select(
            "player_id", "player_name", "position", "n_seasons", "pprr_proj", "pprr_z"
        )
        .sort("pprr_z", descending=True)
    )


def project_efficiency(
    seasons: list[int],
    target_season: int,
    *,
    scoring: str = "ppr",
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
    min_routes: int = DEFAULT_MIN_ROUTES,
) -> pl.DataFrame:
    """Recency-blended efficiency projection, WR/TE only. See ``blend_efficiency``."""
    assert all(s < target_season for s in seasons), (
        f"All seasons must be < target_season={target_season}"
    )
    raw = load_efficiency_inputs(seasons)
    scored = _scored_efficiency(raw, scoring, min_routes)
    return blend_efficiency(scored, weights)


# ---------------------------------------------------------------------------
# Draft-board diagnostic columns (issue #34, "ship rates, hold the
# adjustment" — the z_strength backtest came back mixed/negative, see module
# docstring; TPRR/YPRR/1DRR are useful to eyeball on the board regardless).
# ---------------------------------------------------------------------------


def _scored_rates(
    df: pl.DataFrame, min_routes: int = DEFAULT_MIN_ROUTES
) -> pl.DataFrame:
    """Add raw TPRR/YPRR/1DRR; drop thin route samples."""
    return df.filter(pl.col("routes_proxy") >= min_routes).with_columns(
        (pl.col("targets") / pl.col("routes_proxy")).alias("tprr"),
        (pl.col("receiving_yards") / pl.col("routes_proxy")).alias("yprr"),
        (pl.col("receiving_first_downs") / pl.col("routes_proxy")).alias("fdrr"),
    )


def blend_rates(scored: pl.DataFrame, weights: tuple[float, ...]) -> pl.DataFrame:
    """Pure blending step — takes an already-scored frame (``_scored_rates``
    output) and recency-blends ``tprr``/``yprr``/``fdrr`` per player.
    """
    tprr = _recency_weighted(scored, "tprr", weights).select(
        "player_id", pl.col("blended_tprr").alias("tprr")
    )
    yprr = _recency_weighted(scored, "yprr", weights).select(
        "player_id", pl.col("blended_yprr").alias("yprr")
    )
    fdrr = _recency_weighted(scored, "fdrr", weights).select(
        "player_id", pl.col("blended_fdrr").alias("fdrr")
    )
    return tprr.join(yprr, on="player_id", how="left").join(
        fdrr, on="player_id", how="left"
    )


def blend_efficiency_rates(
    seasons: list[int],
    target_season: int,
    *,
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
    min_routes: int = DEFAULT_MIN_ROUTES,
) -> pl.DataFrame:
    """Recency-blended TPRR / YPRR / 1DRR per player, WR/TE only.

    Diagnostic only — does not touch proj_ppg. For the #31 board to display
    alongside the PPG-only ranking (see ``board.attach_efficiency_rates``).
    """
    assert all(s < target_season for s in seasons), (
        f"All seasons must be < target_season={target_season}"
    )
    raw = load_efficiency_inputs(seasons)
    scored = _scored_rates(raw, min_routes)
    return blend_rates(scored, weights)


def apply_efficiency_adjustment(
    base: pl.DataFrame,
    efficiency: pl.DataFrame,
    strength: float = DEFAULT_Z_STRENGTH,
    games: int = DEFAULT_GAMES,
) -> pl.DataFrame:
    """Scale WR/TE ``proj_ppg`` by ``(1 + strength * pprr_z)`` — a quality
    bump/fade relative to position peers, layered on the existing PPG blend's
    volume assumption (not a reconstruction of it; see module docstring).
    Players without an efficiency row (e.g. below ``DEFAULT_MIN_ROUTES``) or
    outside WR/TE keep their base ``proj_ppg`` unchanged.
    """
    eff = efficiency.select("player_id", "pprr_z")
    merged = base.join(eff, on="player_id", how="left")

    has_z = pl.col("pprr_z").is_not_null() & pl.col("position").is_in(
        EFFICIENCY_POSITIONS
    )
    adjusted_ppg = (
        pl.when(has_z)
        .then(pl.col("proj_ppg") * (1 + strength * pl.col("pprr_z")))
        .otherwise(pl.col("proj_ppg"))
    )

    return (
        merged.with_columns(adjusted_ppg.alias("proj_ppg"))
        .with_columns((pl.col("proj_ppg") * games).alias("proj_points"))
        .select(base.columns)
        .sort("proj_points", descending=True)
    )


def project_season_with_efficiency(
    seasons: list[int],
    target_season: int,
    *,
    scoring: str = "ppr",
    weights: tuple[float, ...] = DEFAULT_WEIGHTS,
    games: int = DEFAULT_GAMES,
    min_routes: int = DEFAULT_MIN_ROUTES,
    z_strength: float = DEFAULT_Z_STRENGTH,
) -> pl.DataFrame:
    """``project_season`` adjusted by WR/TE route efficiency vs position peers.

    QB/RB are passed through from ``project_season`` unchanged. See
    ``apply_efficiency_adjustment`` for the adjustment mechanics.
    """
    base = project_season(
        seasons, target_season, scoring=scoring, weights=weights, games=games
    )
    efficiency = project_efficiency(
        seasons, target_season, scoring=scoring, weights=weights, min_routes=min_routes
    )
    return apply_efficiency_adjustment(
        base, efficiency, strength=z_strength, games=games
    )


if __name__ == "__main__":
    TARGET = 2025
    SEASONS = [2022, 2023, 2024]

    base = project_season(SEASONS, TARGET)
    adjusted = project_season_with_efficiency(SEASONS, TARGET)

    print(
        f"=== WR/TE proj_ppg: PPG-only vs efficiency-adjusted (z_strength={DEFAULT_Z_STRENGTH}) ==="
    )
    compare = (
        base.select(
            "player_id", "player_name", "position", pl.col("proj_ppg").alias("ppg_only")
        )
        .join(
            adjusted.select("player_id", pl.col("proj_ppg").alias("ppg_adjusted")),
            on="player_id",
        )
        .filter(pl.col("position").is_in(EFFICIENCY_POSITIONS))
        .with_columns((pl.col("ppg_adjusted") - pl.col("ppg_only")).alias("delta"))
        .sort("ppg_adjusted", descending=True)
    )
    print(compare.head(20))
    print("\n=== Biggest fades (most negative delta) ===")
    print(compare.sort("delta").head(10))
