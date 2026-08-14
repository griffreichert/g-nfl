"""GET /api/analytics picks its source per season (#56).

Seasons before the app come from `pool_picks`. The trap being pinned here
is that the two tables use the same column name for opposite conventions:
`picks.spread` is the home-perspective game line, `pool_picks.spread` is
signed for the team picked. `grade_pick` silently falls back to the row's
spread when no line resolves, so passing the historical one through grades
every away pick backwards — and nothing errors.
"""

import pytest

import g_nfl.api.main as api


class _Table:
    def __init__(self, rows):
        self.rows = rows

    def get_season_picks(self, season):
        return [r for r in self.rows if r["season"] == season]

    def get_picks(self, season, week=None):
        return [r for r in self.rows if r["season"] == season]

    def get_pool_spreads(self, season, week=None):
        return [r for r in self.rows if r["season"] == season]

    def get_market_lines(self, season, week=None):
        return [r for r in self.rows if r["season"] == season]

    def get_results(self, season):
        return [r for r in self.rows if r["season"] == season]


def _pick(season, picker, team, week=1, gid="2022_01_GB_NYG"):
    # the workbook convention: signed for the team picked, so a home pick
    # and an away pick on one game carry opposite signs
    return {
        "season": season,
        "week": week,
        "picker": picker,
        "game_id": gid,
        "team_picked": team,
        "pick_type": "regular",
        "spread": 3.0 if team == "GB" else -3.0,
    }


@pytest.fixture
def wired(monkeypatch):
    """One game: NYG host GB, pool line NYG -3, NYG won by 7 (so NYG cover)."""

    def install(app_rows, pool_rows, spreads):
        monkeypatch.setattr(api, "PicksDatabase", lambda: _Table(app_rows))
        monkeypatch.setattr(api, "PoolPicksDatabase", lambda: _Table(pool_rows))
        monkeypatch.setattr(api, "PoolSpreadsDatabase", lambda: _Table(spreads))
        monkeypatch.setattr(api, "MarketLinesDatabase", lambda: _Table([]))
        monkeypatch.setattr(
            api,
            "GameResultsDatabase",
            lambda: _Table(
                [
                    {
                        "season": 2022,
                        "week": 1,
                        "game_id": "2022_01_GB_NYG",
                        "away_team": "GB",
                        "home_team": "NYG",
                        "result": 7,
                    }
                ]
            ),
        )

    return install


SPREAD_ROW = [{"season": 2022, "week": 1, "game_id": "2022_01_GB_NYG", "spread": -3.0}]


def test_a_season_the_app_never_saw_falls_back_to_pool_picks(wired):
    wired([], [_pick(2022, "Harry", "NYG")], SPREAD_ROW)
    assert api.get_analytics(2022).picks == 1


def test_the_app_wins_when_it_has_the_season(wired):
    wired([_pick(2022, "Griffin", "NYG")], [_pick(2022, "Harry", "NYG")], SPREAD_ROW)
    # one pick, and it is the app's picker
    assert api.get_analytics(2022).cuts is not None
    assert api.get_analytics(2022).picks == 1


def test_the_submitted_entry_is_excluded_under_both_spellings(wired):
    wired([], [_pick(2022, "Reichert", "NYG"), _pick(2022, "TEAM", "NYG")], SPREAD_ROW)
    with pytest.raises(api.HTTPException):
        api.get_analytics(2022)


def test_a_season_with_no_pool_line_grades_nothing_rather_than_guessing(wired):
    # no spreads at all: the row's own spread must not be used as a fallback
    wired([], [_pick(2022, "Harry", "GB")], [])
    with pytest.raises(api.HTTPException):
        api.get_analytics(2022)
