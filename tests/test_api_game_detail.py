"""GET /api/games/{game_id} (#71).

The endpoint stitches five tables together, so the cases worth pinning are
the joins and the degraded path: context comes from a script that runs
locally and will not have run for the week in progress.
"""

import pytest

import g_nfl.api.main as api


class _Ctx:
    def __init__(self, row):
        self.row = row

    def get_context(self, _gid):
        return self.row


class _Stats:
    def __init__(self, rows):
        self.rows = rows

    def get_team_stats(self, _season, teams):
        return [r for r in self.rows if r["team"] in teams]


class _Picks:
    def __init__(self, rows):
        self.rows = rows

    def get_picks(self, _season, _week):
        return self.rows


class _Results:
    def get_results(self, _season):
        return [
            {
                "game_id": "2025_12_PIT_CHI",
                "away_score": 28,
                "home_score": 31,
                "result": 3.0,
                "week": 12,
            }
        ]


class _Lines:
    """One fake per table so pool and market can differ, which is the only
    way to exercise the market fallback."""

    def __init__(self, rows):
        self.rows = rows

    def get_pool_spreads(self, _season):
        return self.rows

    def get_market_lines(self, _season):
        return self.rows


GID = "2025_12_PIT_CHI"


def _stat(team, week):
    return {
        "week": week,
        "team": team,
        "plays": 60,
        "off_epa_play": 0.05,
        "def_epa_play": -0.02,
        "off_success_rate": 0.45,
        "def_success_rate": 0.44,
        "off_explosive_rate": 0.1,
        "def_explosive_rate": 0.09,
        "off_pass_epa": 0.1,
        "off_rush_epa": 0.0,
    }


@pytest.fixture
def wired(monkeypatch):
    """Patch every table the endpoint touches; tests tweak what they need."""

    def _wire(context=None, stats=(), picks=(), lines=(), pool=None, market=None):
        monkeypatch.setattr(api, "GameContextDatabase", lambda: _Ctx(context))
        monkeypatch.setattr(api, "TeamWeekStatsDatabase", lambda: _Stats(list(stats)))
        monkeypatch.setattr(api, "PicksDatabase", lambda: _Picks(list(picks)))
        monkeypatch.setattr(api, "GameResultsDatabase", lambda: _Results())
        pool_rows = list(lines if pool is None else pool)
        market_rows = list(lines if market is None else market)
        monkeypatch.setattr(api, "PoolSpreadsDatabase", lambda: _Lines(pool_rows))
        monkeypatch.setattr(api, "MarketLinesDatabase", lambda: _Lines(market_rows))

    return _wire


def test_missing_context_still_returns_the_game(wired):
    """The push script runs weekly and lags the live week. A game with no
    context row must degrade to nulls, not 500."""
    wired(context=None)
    d = api.get_game_detail(GID)
    assert d.away_team == "PIT" and d.home_team == "CHI"
    assert d.stadium is None and d.temp is None
    assert d.injuries == []
    assert d.away_score == 28 and d.result == 3.0


def test_team_weeks_stop_at_the_week_being_viewed(wired):
    """Looking at week 12 must not leak week 13's EPA into the preview."""
    wired(stats=[_stat("PIT", w) for w in (11, 12, 13)] + [_stat("CHI", 12)])
    d = api.get_game_detail(GID)
    assert sorted({s.week for s in d.team_weeks}) == [11, 12]


def test_picks_are_graded_on_the_resolved_line_and_carry_their_notes(wired):
    lines = [{"game_id": GID, "spread": 2.5, "total": 45.5}]
    picks = [
        {
            "picker": "Ben",
            "game_id": GID,
            "team_picked": "CHI",
            "pick_type": "regular",
            "spread": None,
            "note": "Rodgers on short rest",
        },
        {
            "picker": "Harry",
            "game_id": GID,
            "team_picked": "PIT",
            "pick_type": "best_bet",
            "spread": None,
        },
    ]
    wired(picks=picks, lines=lines)
    d = api.get_game_detail(GID)
    got = {p.picker: p for p in d.picks}
    # home margin 3 beats a 2.5 line, so the home side covered
    assert got["Ben"].outcome == "win" and got["Ben"].note == "Rodgers on short rest"
    assert got["Harry"].outcome == "loss" and got["Harry"].note is None
    assert d.graded_line == 2.5


def test_test_picker_never_appears(wired):
    from g_nfl.utils.config import TEST_PICKER

    wired(
        picks=[
            {
                "picker": TEST_PICKER,
                "game_id": GID,
                "team_picked": "CHI",
                "pick_type": "regular",
                "spread": None,
            }
        ],
        lines=[{"game_id": GID, "spread": 2.5}],
    )
    assert api.get_game_detail(GID).picks == []


def test_malformed_game_id_is_a_400(wired):
    from fastapi import HTTPException

    wired()
    with pytest.raises(HTTPException) as e:
        api.get_game_detail("nonsense")
    assert e.value.status_code == 400


def test_graded_line_source_names_the_table_it_came_from(wired):
    """The client used to infer this from pool_spread being null, which
    quietly reimplements resolve_lines(). The API says it instead."""
    wired(lines=[{"game_id": GID, "spread": 2.5}])
    assert api.get_game_detail(GID).graded_line_source == "pool"


def test_market_is_the_fallback_when_no_pool_line_exists(wired):
    wired(pool=[], market=[{"game_id": GID, "spread": 1.5}])
    d = api.get_game_detail(GID)
    assert d.graded_line == 1.5
    assert d.graded_line_source == "market"
    assert d.pool_spread is None


def test_pool_wins_over_market_when_both_exist(wired):
    wired(
        pool=[{"game_id": GID, "spread": 2.5}],
        market=[{"game_id": GID, "spread": 1.5}],
    )
    d = api.get_game_detail(GID)
    assert d.graded_line == 2.5 and d.graded_line_source == "pool"
    assert d.market_spread == 1.5


def test_graded_line_source_is_null_when_no_line_resolves(wired):
    wired(lines=[])
    d = api.get_game_detail(GID)
    assert d.graded_line is None and d.graded_line_source is None
