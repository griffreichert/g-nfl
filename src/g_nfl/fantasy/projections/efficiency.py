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
"""

from __future__ import annotations

import nflreadpy as nfl
import polars as pl

EFFICIENCY_POSITIONS: set[str] = {"WR", "TE"}


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


if __name__ == "__main__":
    SEASONS = [2023]
    MIN_ROUTES = 200

    eff = load_efficiency(SEASONS)

    for pos in ("WR", "TE"):
        print(f"\n=== Top 10 {pos} by YPRR (min {MIN_ROUTES} routes, {SEASONS}) ===")
        print(
            eff.filter(
                (pl.col("position") == pos) & (pl.col("routes_proxy") >= MIN_ROUTES)
            )
            .sort("yprr", descending=True)
            .head(10)
        )
