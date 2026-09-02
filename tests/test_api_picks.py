"""`GET /api/picks` with and without a week (#124).

The board needs a season of picks to find voting blocs, and used to fetch it
one week at a time because `week` was required: eighteen HTTP requests on every
open of the page the room uses under time pressure on a Sunday.

The season path goes through `get_season_picks`, which pages past PostgREST's
1000-row cap. `get_picks` does not page, so the week path must keep using it
and the season path must never fall back to looping over weeks.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from g_nfl.api.main import app


def _pick(week, picker, team):
    return {
        "game_id": f"2026_{week:02d}_{team}",
        "team_picked": team,
        "pick_type": "regular",
        "spread": -3.0,
        "note": None,
        "picker": picker,
        "season": 2026,
        "week": week,
    }


SEASON = [
    _pick(1, "griff", "KC"),
    _pick(1, "TEAM", "BUF"),
    _pick(2, "griff", "SF"),
    _pick(3, "TEAM", "PHI"),
]


class _Picks:
    """Records which getter the endpoint reached for."""

    calls: list[str] = []

    def get_picks(self, season, week, picker=None):
        _Picks.calls.append("week")
        return [
            p
            for p in SEASON
            if p["week"] == week and (picker is None or p["picker"] == picker)
        ]

    def get_season_picks(self, season):
        _Picks.calls.append("season")
        return list(SEASON)


@pytest.fixture
def client():
    _Picks.calls = []
    return TestClient(app)


def _get(client, **params):
    with patch("g_nfl.api.main.PicksDatabase", _Picks):
        r = client.get("/api/picks", params={"season": 2026, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_week_returns_only_that_week(client):
    body = _get(client, week=1)
    assert {p["week"] for p in body} == {1}
    assert len(body) == 2


def test_no_week_returns_the_whole_season_in_one_call(client):
    body = _get(client)
    assert len(body) == len(SEASON)
    assert sorted({p["week"] for p in body}) == [1, 2, 3]
    # One paged query, not a loop over eighteen weeks.
    assert _Picks.calls == ["season"]


def test_the_season_still_filters_by_picker(client):
    body = _get(client, picker="TEAM")
    assert {p["picker"] for p in body} == {"TEAM"}
    assert sorted(p["week"] for p in body) == [1, 3]


def test_a_week_and_a_picker_narrow_together(client):
    body = _get(client, week=1, picker="griff")
    assert [p["team_picked"] for p in body] == ["KC"]
    assert _Picks.calls == ["week"]
