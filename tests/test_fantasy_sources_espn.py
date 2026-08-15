"""Tests for g_nfl.fantasy.sources.espn (issue #87). Network-free."""

import json
from pathlib import Path

from g_nfl.fantasy.sources.espn import parse_projections

FIXTURE = Path(__file__).parent / "fixtures" / "espn_projections_sample.json"


def _raw() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parse_keeps_qb_rb_wr_te_only():
    """6 fixture entries in: a kicker and a no-projection player get dropped."""
    df = parse_projections(_raw(), season=2026)
    assert df.height == 4
    assert set(df["position"].to_list()) == {"QB", "RB", "WR", "TE"}


def test_parse_schema_matches_contract():
    df = parse_projections(_raw(), season=2026)
    assert df.columns == [
        "espn_id",
        "player_name",
        "position",
        "team",
        "pass_yd",
        "pass_td",
        "ints",
        "rush_yd",
        "rush_td",
        "rec",
        "rec_yd",
        "rec_td",
        "fum",
    ]


def test_parse_maps_known_player_stats():
    """Josh Allen's stat ids (3/4/20 passing, 24/25 rushing) against the live sample."""
    df = parse_projections(_raw(), season=2026)
    allen = df.filter(df["player_name"] == "Josh Allen").row(0, named=True)
    assert allen["position"] == "QB"
    assert allen["team"] == "BUF"
    assert abs(allen["pass_yd"] - 3944.731641) < 1e-6
    assert abs(allen["pass_td"] - 26.21513029) < 1e-6
    assert abs(allen["ints"] - 11.57956688) < 1e-6
    assert abs(allen["rush_yd"] - 579.4563035) < 1e-6
    assert abs(allen["rush_td"] - 12.42913135) < 1e-6


def test_parse_maps_receiving_stats_and_zero_fills_pass_stats():
    """Ja'Marr Chase has no passing stat block: pass_yd/pass_td/ints default to 0."""
    df = parse_projections(_raw(), season=2026)
    chase = df.filter(df["player_name"] == "Ja'Marr Chase").row(0, named=True)
    assert chase["position"] == "WR"
    assert chase["pass_yd"] == 0.0
    assert abs(chase["rec"] - 119.3167371) < 1e-6
    assert abs(chase["rec_yd"] - 1504.291771) < 1e-6
    assert abs(chase["rec_td"] - 10.70420364) < 1e-6
    assert abs(chase["fum"] - 0.941070256) < 1e-6
