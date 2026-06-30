"""Tests for g_nfl.fantasy.projections.efficiency (issue #34).

All tests are network-free; they build synthetic polars frames and
exercise the pure functions directly.
"""

import polars as pl

from g_nfl.fantasy.projections.efficiency import (
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
