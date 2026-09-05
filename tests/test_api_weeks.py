"""`GET /api/weeks`, and the week a page opens on (#61).

The board opened on `max_week`, the furthest week we hold lines for. That
matched the current week only while nobody had snapshotted ahead: the Friday
job pulling all 18 weeks would have opened everyone on week 18.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from g_nfl.api.main import app
from g_nfl.picks.calendar import SeasonWeeks


@pytest.fixture
def client():
    return TestClient(app)


def _weeks(client, available, current=3):
    snapshot = SeasonWeeks(weeks=available, current=current if available else None)
    with patch("g_nfl.api.main.season_weeks", lambda season: snapshot):
        r = client.get("/api/weeks", params={"season": 2026})
    assert r.status_code == 200
    return r.json()


def test_current_week_is_reported_separately_from_the_last_week_with_lines(client):
    body = _weeks(client, [1, 2, 3, 4, 5], current=3)
    assert body["current_week"] == 3
    assert body["max_week"] == 5
    assert body["weeks"] == [1, 2, 3, 4, 5]


def test_a_season_with_no_lines_reports_neither(client):
    """Nothing to open on, so the page falls back rather than inventing a week."""
    body = _weeks(client, [])
    assert body["current_week"] is None
    assert body["max_week"] is None
