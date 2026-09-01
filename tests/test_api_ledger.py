"""The ledger endpoint (#58)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from g_nfl.api.main import app

G1 = "2026_01_AAA_BBB"
G2 = "2026_01_CCC_DDD"


def _pick(picker, game_id, team, slot="regular"):
    return {
        "picker": picker,
        "season": 2026,
        "week": 1,
        "game_id": game_id,
        "team_picked": team,
        "pick_type": slot,
    }


def test_the_ledger_puts_team_next_to_the_entries_it_could_have_sent():
    picks = [
        _pick("TEAM", G1, "AAA"),
        _pick("Griffin", G1, "BBB"),
        _pick("Harry", G1, "BBB"),
    ]
    with (
        patch("g_nfl.api.main.PicksDatabase") as p,
        patch("g_nfl.api.main.PoolSpreadsDatabase") as pool,
        patch("g_nfl.api.main.MarketLinesDatabase") as market,
        patch("g_nfl.api.main.GameResultsDatabase") as results,
    ):
        p.return_value.get_season_picks.return_value = picks
        pool.return_value.get_pool_spreads.return_value = [
            {"game_id": G1, "spread": 0.0}
        ]
        market.return_value.get_market_lines.return_value = []
        results.return_value.get_results.return_value = [
            {"game_id": G1, "result": 7.0, "week": 1}
        ]
        r = TestClient(app).get("/api/ledger?season=2026")

    assert r.status_code == 200
    table = {e["entry"]: e for e in r.json()["standings"]}
    # home covered, so TEAM's away side lost and the majority's home side won
    assert table["TEAM"]["points"] == 0.0
    assert table["Majority"]["points"] == 1.0
    assert table["Majority"]["share"] == 1.0


def test_the_test_picker_never_reaches_the_ledger():
    with (
        patch("g_nfl.api.main.PicksDatabase") as p,
        patch("g_nfl.api.main.PoolSpreadsDatabase") as pool,
        patch("g_nfl.api.main.MarketLinesDatabase") as market,
        patch("g_nfl.api.main.GameResultsDatabase") as results,
    ):
        p.return_value.get_season_picks.return_value = [_pick("TEST", G1, "BBB")]
        pool.return_value.get_pool_spreads.return_value = [
            {"game_id": G1, "spread": 0.0}
        ]
        market.return_value.get_market_lines.return_value = []
        results.return_value.get_results.return_value = [
            {"game_id": G1, "result": 7.0, "week": 1}
        ]
        r = TestClient(app).get("/api/ledger?season=2026")

    assert [e["entry"] for e in r.json()["standings"]] == []


def test_an_ungraded_season_returns_an_empty_table_rather_than_failing():
    with (
        patch("g_nfl.api.main.PicksDatabase") as p,
        patch("g_nfl.api.main.PoolSpreadsDatabase") as pool,
        patch("g_nfl.api.main.MarketLinesDatabase") as market,
        patch("g_nfl.api.main.GameResultsDatabase") as results,
    ):
        p.return_value.get_season_picks.return_value = [_pick("Griffin", G2, "CCC")]
        pool.return_value.get_pool_spreads.return_value = []
        market.return_value.get_market_lines.return_value = []
        results.return_value.get_results.return_value = []
        r = TestClient(app).get("/api/ledger?season=2026")

    assert r.status_code == 200
    assert r.json()["standings"] == []
