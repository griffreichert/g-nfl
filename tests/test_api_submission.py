"""When a week was submitted (#131), and who may be signed in as (#129).

`submitted_at` is stamped server-side, so a late entry cannot be backdated by
editing a request.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from g_nfl.api.auth import authenticate
from g_nfl.api.main import app
from g_nfl.api.schemas import WeeksResponse


class _Picks:
    """Captures what save_picks was handed."""

    saves: list[dict] = []

    def save_picks(self, season, week, picks, picker):
        _Picks.saves.append(
            {"season": season, "week": week, "picker": picker, "picks": picks}
        )
        return len(picks)


@pytest.fixture
def client(monkeypatch):
    _Picks.saves = []
    monkeypatch.setenv("AUTH_SECRET", "x" * 40)
    monkeypatch.setenv("APP_PASSPHRASE", "open sesame")
    return TestClient(app)


def _auth(picker):
    return {"Authorization": f"Bearer {authenticate(picker, 'open sesame')}"}


def _body(picker, week=1):
    return {
        "season": 2026,
        "week": week,
        "picker": picker,
        "picks": [
            {
                "game_id": "2026_01_KC_BUF",
                "team_picked": "KC",
                "pick_type": "regular",
                "spread": -3.0,
                "note": None,
            }
        ],
    }


def _post(client, signed_in, picker, week=1):
    with patch("g_nfl.api.main.PicksDatabase", _Picks):
        r = client.post(
            "/api/picks", json=_body(picker, week), headers=_auth(signed_in)
        )
    assert r.status_code == 200, r.text
    return r.json()


def test_resubmitting_moves_the_timestamp_forward():
    """`submitted_at` is stamped inside save_picks, once per call."""
    from g_nfl.utils import database

    stamps = []

    class _Table:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return type("R", (), {"data": []})()

        def insert(self, rows):
            stamps.append(rows[0]["submitted_at"])
            return self

    class _Client:
        def table(self, name):
            return _Table()

    db = database.PicksDatabase.__new__(database.PicksDatabase)
    db.client = _Client()

    row = {"team_picked": "KC", "pick_type": "regular", "spread": -3.0, "note": None}
    db.save_picks(2026, 1, {"2026_01_KC_BUF": row}, "Griffin")
    db.save_picks(2026, 1, {"2026_01_KC_BUF": row}, "Griffin")

    assert len(stamps) == 2
    first, second = (datetime.fromisoformat(s) for s in stamps)
    assert second >= first
    # tz-aware, so a client in another zone reads it correctly
    assert first.tzinfo is not None


def test_the_signin_list_drops_team_and_test(client):
    """TEAM is an output and TEST is a scratch profile (#129)."""
    # The season, week and week list come from Supabase, which CI has no
    # credentials for. Only the picker list is under test here.
    with (
        patch("g_nfl.api.main.PicksDatabase", _Picks),
        patch("g_nfl.api.main.current_season", return_value=2026),
        patch("g_nfl.api.main.current_week", return_value=1),
        patch(
            "g_nfl.api.main.get_weeks",
            return_value=WeeksResponse(weeks=[1], max_week=1, current_week=1),
        ),
    ):
        r = client.get("/api/config")
    assert r.status_code == 200, r.text
    pickers = r.json()["pickers"]
    assert "TEAM" not in pickers
    assert "TEST" not in pickers
    assert "Griffin" in pickers


def test_test_can_still_get_a_token(client):
    """Dropping it from the list must not lock the save path out of testing."""
    r = client.post(
        "/api/auth/login", json={"picker": "TEST", "passphrase": "open sesame"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["picker"] == "TEST"
