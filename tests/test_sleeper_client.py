"""Tests for the Sleeper client (#19): no network — _get is stubbed."""

import json
import time

import pytest

from g_nfl.sleeper.client import SleeperClient

ROSTERS = [
    {"roster_id": 1, "owner_id": "u_griffin", "players": ["1234", "5678"]},
    {"roster_id": 2, "owner_id": "u_harry", "players": ["9999"]},
]

PLAYERS = {
    "1234": {"position": "RB", "active": True, "full_name": "Rostered Back"},
    "5678": {"position": "WR", "active": True, "full_name": "Rostered Wideout"},
    "9999": {"position": "QB", "active": True, "full_name": "Rostered QB"},
    "1111": {"position": "RB", "active": True, "full_name": "Free Agent Back"},
    "2222": {"position": "RB", "active": False, "full_name": "Retired Back"},
    "3333": {"position": "P", "active": True, "full_name": "Free Agent Punter"},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    c = SleeperClient(cache_dir=tmp_path)
    calls: list[str] = []

    def fake_get(path, **params):
        calls.append(path)
        if path == "/state/nfl":
            return {"season": "2026", "league_season": "2026", "week": 3}
        if "/leagues/nfl/" in path:
            return [
                {
                    "league_id": "L1",
                    "name": "Test League",
                    "season": path.rsplit("/", 1)[-1],
                }
            ]
        if path.startswith("/user/"):
            return {"user_id": "u_griffin", "username": "griffin"}
        if path.endswith("/rosters"):
            return ROSTERS
        if path == "/players/nfl":
            return PLAYERS
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(c, "_get", fake_get)
    c._calls = calls
    return c


def test_user_leagues_defaults_to_current_league_season(client):
    leagues = client.user_leagues("griffin")
    assert leagues[0]["league_id"] == "L1"
    assert leagues[0]["season"] == "2026"  # came from state()


def test_my_roster_matches_owner(client):
    roster = client.my_roster("L1", "griffin")
    assert roster["roster_id"] == 1


def test_my_roster_raises_for_non_member(client, monkeypatch):
    monkeypatch.setattr(
        client, "user", lambda u: {"user_id": "u_stranger", "username": u}
    )
    with pytest.raises(LookupError):
        client.my_roster("L1", "stranger")


def test_free_agents_excludes_rostered_inactive_and_offskill(client):
    fas = client.free_agents("L1")
    ids = {p["player_id"] for p in fas}
    # only the active skill-position unrostered player remains
    assert ids == {"1111"}
    assert fas[0]["full_name"] == "Free Agent Back"


def test_players_cached_on_disk(client, tmp_path):
    client.players()
    client.players()
    # second call served from cache: only one /players/nfl fetch
    assert client._calls.count("/players/nfl") == 1
    cache = tmp_path / "players_nfl.json"
    assert json.loads(cache.read_text())["1234"]["position"] == "RB"


def test_players_cache_expires(client, tmp_path):
    client.players()
    cache = tmp_path / "players_nfl.json"
    stale = time.time() - 25 * 3600
    import os

    os.utime(cache, (stale, stale))
    client.players()
    assert client._calls.count("/players/nfl") == 2


def test_trending_rejects_bad_kind(client):
    with pytest.raises(ValueError):
        client.trending("hold")
