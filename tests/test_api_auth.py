"""PIN login and the impersonation hole it closes (#60).

`POST /api/picks` used to take the picker from the request body, so anyone
could submit as anyone and the ledger recorded fiction.
"""

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from g_nfl.api import auth
from g_nfl.api.main import app

# One salt/hash pair, generated once so the 600k-iteration PBKDF2 runs twice
# in this module rather than once per test.
PIN = "1234"
HASH = auth.hash_pin(PIN)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "test-secret-long-enough-for-hs256-x")
    monkeypatch.setenv("PICKER_PINS", json.dumps({"Griffin": HASH}))


@pytest.fixture
def client(env):
    return TestClient(app)


def test_the_right_pin_returns_a_token(client):
    r = client.post("/api/auth/login", json={"picker": "Griffin", "pin": PIN})
    assert r.status_code == 200
    assert auth.read_token(r.json()["token"]) == "Griffin"


def test_the_wrong_pin_is_refused(client):
    r = client.post("/api/auth/login", json={"picker": "Griffin", "pin": "9999"})
    assert r.status_code == 401


def test_an_unknown_picker_gets_the_same_error_as_a_wrong_pin(client):
    """The response must not confirm who is in the pool."""
    unknown = client.post("/api/auth/login", json={"picker": "Mallory", "pin": PIN})
    wrong = client.post("/api/auth/login", json={"picker": "Griffin", "pin": "9999"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_saving_picks_without_a_token_is_refused(client):
    r = client.post(
        "/api/picks",
        json={"season": 2026, "week": 1, "picker": "Griffin", "picks": []},
    )
    assert r.status_code == 401


def test_the_body_cannot_name_a_different_picker(client):
    """Harry's token saves as Harry however the body is addressed."""
    token = auth.authenticate("Griffin", PIN)
    saved = {}

    def _save(season, week, picks, picker):
        saved["picker"] = picker
        return 0

    with patch("g_nfl.api.main.PicksDatabase") as db:
        db.return_value.save_picks = _save
        r = client.post(
            "/api/picks",
            json={"season": 2026, "week": 1, "picker": "Hunter", "picks": []},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    assert saved["picker"] == "Griffin"


def test_team_may_be_written_by_any_signed_in_picker(client):
    """TEAM is the entry the room submits together off the board."""
    token = auth.authenticate("Griffin", PIN)
    saved = {}

    def _save(season, week, picks, picker):
        saved["picker"] = picker
        return 0

    with patch("g_nfl.api.main.PicksDatabase") as db:
        db.return_value.save_picks = _save
        r = client.post(
            "/api/picks",
            json={"season": 2026, "week": 1, "picker": "TEAM", "picks": []},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    assert saved["picker"] == "TEAM"


def test_team_still_needs_a_session(client):
    r = client.post(
        "/api/picks",
        json={"season": 2026, "week": 1, "picker": "TEAM", "picks": []},
    )
    assert r.status_code == 401


def test_a_tampered_token_is_refused(client):
    token = auth.authenticate("Griffin", PIN)
    head, payload, sig = token.split(".")
    with pytest.raises(HTTPException) as e:
        auth.read_token(f"{head}.{payload}.{sig[:-2]}xx")
    assert e.value.status_code == 401


def test_a_token_signed_with_another_secret_is_refused(client, monkeypatch):
    token = auth.authenticate("Griffin", PIN)
    monkeypatch.setenv("AUTH_SECRET", "a-different-secret-also-long-enough")
    with pytest.raises(HTTPException) as e:
        auth.read_token(token)
    assert e.value.status_code == 401


def test_no_pins_configured_means_nobody_gets_in(client, monkeypatch):
    monkeypatch.delenv("PICKER_PINS")
    r = client.post("/api/auth/login", json={"picker": "Griffin", "pin": PIN})
    assert r.status_code == 401


def test_a_malformed_pins_variable_fails_closed(client, monkeypatch):
    monkeypatch.setenv("PICKER_PINS", "{not json")
    r = client.post("/api/auth/login", json={"picker": "Griffin", "pin": PIN})
    assert r.status_code == 401


def test_a_short_secret_is_refused_rather_than_warned_about(client, monkeypatch):
    """A guessable signing key is worse than no auth, because it looks like auth."""
    monkeypatch.setenv("AUTH_SECRET", "short")
    r = client.post("/api/auth/login", json={"picker": "Griffin", "pin": PIN})
    assert r.status_code == 503


def test_pool_spreads_need_a_session_too(client):
    """Every ATS pick grades against these numbers."""
    r = client.put(
        "/api/pool-spreads",
        json={"season": 2026, "week": 1, "game_id": "2026_01_NE_SEA", "spread": -3.5},
    )
    assert r.status_code == 401
