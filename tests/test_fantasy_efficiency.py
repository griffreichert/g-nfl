"""Tests for g_nfl.fantasy.projections.efficiency (issue #34).

All tests are network-free; they build synthetic polars frames and
exercise the pure functions directly.
"""

import polars as pl

from g_nfl.fantasy.projections.efficiency import (
    DEFAULT_MIN_ROUTES,
    DEFAULT_Z_STRENGTH,
    EFFICIENCY_POSITIONS,
    Z_CLIP,
    _scored_efficiency,
    _scored_rates,
    apply_efficiency_adjustment,
    blend_efficiency,
    blend_rates,
    compute_efficiency,
    compute_routes_proxy,
)

# ---------------------------------------------------------------------------
# compute_routes_proxy
# ---------------------------------------------------------------------------


def _pass_plays(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={"game_id": pl.Utf8, "play_id": pl.Float64, "season": pl.Int32},
    )


def _participation(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={"game_id": pl.Utf8, "play_id": pl.Float64, "offense_players": pl.Utf8},
    )


def test_routes_proxy_counts_pass_plays_per_player():
    """Each player on offense for a pass play gets +1 route; non-pass plays
    in participation that aren't in pass_plays are excluded by the inner join.
    """
    pass_plays = _pass_plays(
        {"game_id": "G1", "play_id": 1.0, "season": 2023},
        {"game_id": "G1", "play_id": 2.0, "season": 2023},
    )
    participation = _participation(
        {"game_id": "G1", "play_id": 1.0, "offense_players": "WR1;WR2;QB1"},
        {"game_id": "G1", "play_id": 2.0, "offense_players": "WR1;TE1;QB1"},
        # run play, not in pass_plays -> dropped by inner join
        {"game_id": "G1", "play_id": 3.0, "offense_players": "WR1;WR2;QB1"},
    )
    routes = compute_routes_proxy(pass_plays, participation)
    counts = dict(zip(routes["player_id"], routes["routes_proxy"], strict=True))
    assert counts == {"WR1": 2, "WR2": 1, "TE1": 1, "QB1": 2}


def test_routes_proxy_grouped_by_season():
    pass_plays = _pass_plays(
        {"game_id": "G1", "play_id": 1.0, "season": 2022},
        {"game_id": "G2", "play_id": 1.0, "season": 2023},
    )
    participation = _participation(
        {"game_id": "G1", "play_id": 1.0, "offense_players": "WR1"},
        {"game_id": "G2", "play_id": 1.0, "offense_players": "WR1"},
    )
    routes = compute_routes_proxy(pass_plays, participation)
    seasons = dict(zip(routes["season"], routes["routes_proxy"], strict=True))
    assert seasons == {2022: 1, 2023: 1}


# ---------------------------------------------------------------------------
# compute_efficiency
# ---------------------------------------------------------------------------


def _routes(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={"player_id": pl.Utf8, "season": pl.Int32, "routes_proxy": pl.UInt32},
    )


def _stats(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "player_name": pl.Utf8,
            "position": pl.Utf8,
            "season": pl.Int32,
            "targets": pl.Int32,
            "receiving_yards": pl.Float64,
            "receiving_first_downs": pl.Int32,
        },
    )


def test_efficiency_rates_computed_correctly():
    routes = _routes({"player_id": "WR1", "season": 2023, "routes_proxy": 100})
    stats = _stats(
        {
            "player_id": "WR1",
            "player_name": "Star WR",
            "position": "WR",
            "season": 2023,
            "targets": 25,
            "receiving_yards": 250.0,
            "receiving_first_downs": 12,
        }
    )
    eff = compute_efficiency(routes, stats)
    row = eff.row(0, named=True)
    assert abs(row["tprr"] - 0.25) < 1e-9
    assert abs(row["yprr"] - 2.5) < 1e-9
    assert abs(row["fdrr"] - 0.12) < 1e-9


def test_efficiency_excludes_non_wr_te():
    routes = _routes(
        {"player_id": "RB1", "season": 2023, "routes_proxy": 100},
        {"player_id": "WR1", "season": 2023, "routes_proxy": 100},
    )
    stats = _stats(
        {
            "player_id": "RB1",
            "player_name": "Some RB",
            "position": "RB",
            "season": 2023,
            "targets": 50,
            "receiving_yards": 300.0,
            "receiving_first_downs": 15,
        },
        {
            "player_id": "WR1",
            "player_name": "Star WR",
            "position": "WR",
            "season": 2023,
            "targets": 25,
            "receiving_yards": 250.0,
            "receiving_first_downs": 12,
        },
    )
    eff = compute_efficiency(routes, stats)
    assert eff["position"].to_list() == ["WR"]


def test_efficiency_sorted_by_yprr_descending():
    routes = _routes(
        {"player_id": "WR1", "season": 2023, "routes_proxy": 100},
        {"player_id": "WR2", "season": 2023, "routes_proxy": 100},
    )
    stats = _stats(
        {
            "player_id": "WR1",
            "player_name": "Low YPRR",
            "position": "WR",
            "season": 2023,
            "targets": 20,
            "receiving_yards": 100.0,
            "receiving_first_downs": 5,
        },
        {
            "player_id": "WR2",
            "player_name": "High YPRR",
            "position": "WR",
            "season": 2023,
            "targets": 20,
            "receiving_yards": 300.0,
            "receiving_first_downs": 10,
        },
    )
    eff = compute_efficiency(routes, stats)
    assert eff["player_name"].to_list() == ["High YPRR", "Low YPRR"]


# ---------------------------------------------------------------------------
# _scored_efficiency / blend_efficiency / apply_efficiency_adjustment
# (the "z-score quality bump on top of season.py's proj_ppg" path)
# ---------------------------------------------------------------------------


def _raw_inputs(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "player_name": pl.Utf8,
            "position": pl.Utf8,
            "season": pl.Int32,
            "games": pl.Int32,
            "routes_proxy": pl.UInt32,
            "fantasy_points": pl.Float64,
            "fantasy_points_ppr": pl.Float64,
        },
    )


def test_scored_efficiency_pprr_rate():
    raw = _raw_inputs(
        {
            "player_id": "WR1",
            "player_name": "Star WR",
            "position": "WR",
            "season": 2023,
            "games": 16,
            "routes_proxy": 320,
            "fantasy_points": 160.0,
            "fantasy_points_ppr": 240.0,
        }
    )
    scored = _scored_efficiency(raw, "ppr")
    row = scored.row(0, named=True)
    assert abs(row["pprr"] - 240.0 / 320) < 1e-9


def test_scored_efficiency_drops_thin_route_sample():
    raw = _raw_inputs(
        {
            "player_id": "WR1",
            "player_name": "Thin Sample",
            "position": "WR",
            "season": 2023,
            "games": 2,
            "routes_proxy": 30,
            "fantasy_points": 10.0,
            "fantasy_points_ppr": 15.0,
        }
    )
    assert len(_scored_efficiency(raw, "ppr", min_routes=DEFAULT_MIN_ROUTES)) == 0
    assert len(_scored_efficiency(raw, "ppr", min_routes=0)) == 1


def _scored(*rows: dict) -> pl.DataFrame:
    """Synthetic already-scored frame (player_id, player_name, position,
    season, pprr) for blend_efficiency, skipping the routes_proxy/games math.
    """
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "player_name": pl.Utf8,
            "position": pl.Utf8,
            "season": pl.Int32,
            "pprr": pl.Float64,
        },
    )


def test_blend_efficiency_zscore_vs_position_peers():
    """Three WRs, one TE. WR pprr values 0.4/0.5/0.6 -> mean 0.5, pop std
    sqrt(0.02/3); the TE alone in its position group gets z=0 (zero variance).
    """
    scored = _scored(
        {
            "player_id": "WR1",
            "player_name": "Low",
            "position": "WR",
            "season": 2023,
            "pprr": 0.4,
        },
        {
            "player_id": "WR2",
            "player_name": "Mid",
            "position": "WR",
            "season": 2023,
            "pprr": 0.5,
        },
        {
            "player_id": "WR3",
            "player_name": "High",
            "position": "WR",
            "season": 2023,
            "pprr": 0.6,
        },
        {
            "player_id": "TE1",
            "player_name": "Solo TE",
            "position": "TE",
            "season": 2023,
            "pprr": 0.3,
        },
    )
    blended = blend_efficiency(scored, (1.0,))
    rows = {r["player_id"]: r for r in blended.iter_rows(named=True)}
    assert abs(rows["WR2"]["pprr_z"] - 0.0) < 1e-9
    assert rows["WR3"]["pprr_z"] > 0
    assert rows["WR1"]["pprr_z"] < 0
    assert abs(rows["WR1"]["pprr_z"]) == abs(rows["WR3"]["pprr_z"])  # symmetric
    assert rows["TE1"]["pprr_z"] == 0.0  # single TE, zero variance in its group


def test_blend_efficiency_zscore_clipped():
    """An extreme outlier's z is capped at +-Z_CLIP, not left unbounded."""
    scored = _scored(
        *[
            {
                "player_id": f"WR{i}",
                "player_name": f"Avg{i}",
                "position": "WR",
                "season": 2023,
                "pprr": 0.5,
            }
            for i in range(20)
        ],
        {
            "player_id": "OUTLIER",
            "player_name": "Outlier",
            "position": "WR",
            "season": 2023,
            "pprr": 5.0,
        },
    )
    blended = blend_efficiency(scored, (1.0,))
    outlier_z = blended.filter(pl.col("player_id") == "OUTLIER").row(0, named=True)[
        "pprr_z"
    ]
    assert outlier_z == Z_CLIP


def _base(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "player_name": pl.Utf8,
            "position": pl.Utf8,
            "last_team": pl.Utf8,
            "n_seasons": pl.UInt32,
            "proj_ppg": pl.Float64,
            "proj_points": pl.Float64,
        },
    )


def _efficiency(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "player_name": pl.Utf8,
            "position": pl.Utf8,
            "n_seasons": pl.UInt32,
            "pprr_proj": pl.Float64,
            "pprr_z": pl.Float64,
        },
    )


def test_adjustment_scales_proj_ppg_by_z():
    base = _base(
        {
            "player_id": "WR1",
            "player_name": "Star WR",
            "position": "WR",
            "last_team": "KC",
            "n_seasons": 3,
            "proj_ppg": 10.0,
            "proj_points": 170.0,
        }
    )
    efficiency = _efficiency(
        {
            "player_id": "WR1",
            "player_name": "Star WR",
            "position": "WR",
            "n_seasons": 3,
            "pprr_proj": 0.05,
            "pprr_z": 2.0,
        }
    )
    adjusted = apply_efficiency_adjustment(base, efficiency, strength=0.08, games=17)
    row = adjusted.row(0, named=True)
    expected_ppg = 10.0 * (1 + 0.08 * 2.0)
    assert abs(row["proj_ppg"] - expected_ppg) < 1e-9
    assert abs(row["proj_points"] - expected_ppg * 17) < 1e-9


def test_adjustment_strength_zero_keeps_base():
    base = _base(
        {
            "player_id": "WR1",
            "player_name": "Star WR",
            "position": "WR",
            "last_team": "KC",
            "n_seasons": 3,
            "proj_ppg": 10.0,
            "proj_points": 170.0,
        }
    )
    efficiency = _efficiency(
        {
            "player_id": "WR1",
            "player_name": "Star WR",
            "position": "WR",
            "n_seasons": 3,
            "pprr_proj": 0.05,
            "pprr_z": 2.0,
        }
    )
    adjusted = apply_efficiency_adjustment(base, efficiency, strength=0.0, games=17)
    assert abs(adjusted.row(0, named=True)["proj_ppg"] - 10.0) < 1e-9


def test_adjustment_skips_players_without_efficiency_row():
    """A player below the routes floor (no efficiency row) keeps base proj_ppg."""
    base = _base(
        {
            "player_id": "WR2",
            "player_name": "Thin Sample WR",
            "position": "WR",
            "last_team": "NE",
            "n_seasons": 1,
            "proj_ppg": 5.0,
            "proj_points": 85.0,
        }
    )
    efficiency = _efficiency()  # empty: no rows for WR2
    adjusted = apply_efficiency_adjustment(base, efficiency, strength=0.08, games=17)
    assert abs(adjusted.row(0, named=True)["proj_ppg"] - 5.0) < 1e-9


def test_adjustment_skips_non_wr_te_positions():
    base = _base(
        {
            "player_id": "RB1",
            "player_name": "Some RB",
            "position": "RB",
            "last_team": "SF",
            "n_seasons": 3,
            "proj_ppg": 12.0,
            "proj_points": 204.0,
        }
    )
    # Hypothetical efficiency row present (shouldn't happen for RB in practice,
    # but the position guard must hold regardless).
    efficiency = _efficiency(
        {
            "player_id": "RB1",
            "player_name": "Some RB",
            "position": "RB",
            "n_seasons": 3,
            "pprr_proj": 0.2,
            "pprr_z": 2.0,
        }
    )
    adjusted = apply_efficiency_adjustment(base, efficiency, strength=0.08, games=17)
    assert abs(adjusted.row(0, named=True)["proj_ppg"] - 12.0) < 1e-9


def test_default_z_strength_is_eight_percent():
    assert DEFAULT_Z_STRENGTH == 0.08


def test_efficiency_positions_is_wr_te():
    assert EFFICIENCY_POSITIONS == {"WR", "TE"}


# ---------------------------------------------------------------------------
# _scored_rates / blend_rates (board diagnostic columns: tprr/yprr/fdrr)
# ---------------------------------------------------------------------------


def _routes_with_stats(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "player_id": pl.Utf8,
            "season": pl.Int32,
            "routes_proxy": pl.UInt32,
            "targets": pl.Int32,
            "receiving_yards": pl.Float64,
            "receiving_first_downs": pl.Int32,
        },
    )


def test_scored_rates_computes_tprr_yprr_fdrr():
    raw = _routes_with_stats(
        {
            "player_id": "WR1",
            "season": 2023,
            "routes_proxy": 100,
            "targets": 25,
            "receiving_yards": 250.0,
            "receiving_first_downs": 12,
        }
    )
    scored = _scored_rates(raw)
    row = scored.row(0, named=True)
    assert abs(row["tprr"] - 0.25) < 1e-9
    assert abs(row["yprr"] - 2.5) < 1e-9
    assert abs(row["fdrr"] - 0.12) < 1e-9


def test_scored_rates_drops_thin_route_sample():
    raw = _routes_with_stats(
        {
            "player_id": "WR1",
            "season": 2023,
            "routes_proxy": 30,
            "targets": 5,
            "receiving_yards": 40.0,
            "receiving_first_downs": 2,
        }
    )
    assert len(_scored_rates(raw, min_routes=DEFAULT_MIN_ROUTES)) == 0
    assert len(_scored_rates(raw, min_routes=0)) == 1


def test_blend_rates_recency_weighted():
    scored = _routes_with_stats(
        {
            "player_id": "WR1",
            "season": 2023,
            "routes_proxy": 100,
            "targets": 30,
            "receiving_yards": 300.0,
            "receiving_first_downs": 15,
        },
        {
            "player_id": "WR1",
            "season": 2022,
            "routes_proxy": 100,
            "targets": 20,
            "receiving_yards": 200.0,
            "receiving_first_downs": 10,
        },
    ).pipe(_scored_rates)
    blended = blend_rates(scored, (0.6, 0.4))
    row = blended.row(0, named=True)
    assert abs(row["tprr"] - (0.30 * 0.6 + 0.20 * 0.4)) < 1e-9
    assert abs(row["yprr"] - (3.0 * 0.6 + 2.0 * 0.4)) < 1e-9
    assert abs(row["fdrr"] - (0.15 * 0.6 + 0.10 * 0.4)) < 1e-9
