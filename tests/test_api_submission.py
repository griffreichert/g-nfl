"""Who submitted a week, and when (#131), and who may be signed in as (#129).

`submitted_at` and `submitted_by` are stamped server-side from the token. The
client never sends either, so a late entry cannot be backdated by editing a
request, and a TEAM slate records the person who typed it rather than the word
TEAM.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from g_nfl.api.auth import authenticate
from g_nfl.api.main import app


class _Picks:
    """Captures what save_picks was handed."""

    saves: list[dict] = []

    def save_picks(self, season, week, picks, picker, submitted_by=None):
        _Picks.saves.append(
            {
                "season": season,
                "week": week,
                "picker": picker,
                "submitted_by": submitted_by,
                "picks": picks,
            }
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


def test_a_personal_slate_stamps_the_signed_in_picker(client):
    _post(client, "Griffin", "Griffin")
    save = _Picks.saves[-1]
    assert save["picker"] == "Griffin"
    assert save["submitted_by"] == "Griffin"


def test_team_records_the_person_who_submitted_it(client):
    """The row belongs to TEAM; the stamp says who was at the keyboard."""
    _post(client, "Harry", "TEAM")
    save = _Picks.saves[-1]
    assert save["picker"] == "TEAM"
    assert save["submitted_by"] == "Harry"


def test_the_body_cannot_claim_a_different_submitter(client):
    """Signed in as Griffin, submitting a body that names Harry."""
    _post(client, "Griffin", "Harry")
    save = _Picks.saves[-1]
    assert save["picker"] == "Griffin"
    assert save["submitted_by"] == "Griffin"


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
    db.save_picks(2026, 1, {"2026_01_KC_BUF": row}, "Griffin", submitted_by="Harry")
    db.save_picks(2026, 1, {"2026_01_KC_BUF": row}, "Griffin", submitted_by="Harry")

    assert len(stamps) == 2
    first, second = (datetime.fromisoformat(s) for s in stamps)
    assert second >= first
    # tz-aware, so a client in another zone reads it correctly
    assert first.tzinfo is not None


def test_the_signin_list_drops_team_and_test(client):
    """TEAM is an output and TEST is a scratch profile (#129)."""
    with patch("g_nfl.api.main.PicksDatabase", _Picks):
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
