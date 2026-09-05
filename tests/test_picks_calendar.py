"""Deriving the current season and week from the database (#61).

These replaced `CUR_SEASON` and `CUR_WEEK`, two constants somebody had to
remember to bump. Nine days before the 2026 opener they still read 2025 and
week 12, which is what the app opened on.
"""

from unittest.mock import patch

import pytest

from g_nfl.picks import calendar


class _Lines:
    def __init__(self, counts, latest=2026):
        self._counts, self._latest = counts, latest

    def games_per_week(self, season):
        return self._counts

    def latest_season(self):
        return self._latest


class _Results:
    def __init__(self, graded):
        self._graded = graded

    def graded_per_week(self, season):
        return self._graded


@pytest.fixture(autouse=True)
def _fresh_cache():
    calendar.clear_cache()
    yield
    calendar.clear_cache()


def _week(counts, graded, default=99):
    with (
        patch.object(calendar, "MarketLinesDatabase", lambda: _Lines(counts)),
        patch.object(calendar, "GameResultsDatabase", lambda: _Results(graded)),
    ):
        return calendar.current_week(2026, default=default)


def test_a_season_nobody_has_played_is_on_week_one():
    assert _week({1: 16, 2: 16, 3: 16}, {}) == 1


def test_a_week_holds_until_its_last_game_is_graded():
    assert _week({1: 16, 2: 16}, {1: 15}) == 1


def test_the_week_rolls_over_once_every_game_is_in():
    assert _week({1: 16, 2: 16}, {1: 16}) == 2


def test_a_week_with_nothing_graded_is_the_current_week():
    assert _week({1: 16, 2: 16}, {}) == 1


def test_a_finished_season_stays_on_its_last_week():
    assert _week({1: 16, 2: 16}, {1: 16, 2: 16}) == 2


def test_no_lines_at_all_falls_back_rather_than_guessing():
    assert _week({}, {}, default=7) == 7


def test_the_season_is_the_latest_one_we_hold_lines_for():
    with patch.object(calendar, "MarketLinesDatabase", lambda: _Lines({}, latest=2026)):
        assert calendar.current_season() == 2026


def test_a_second_call_inside_the_ttl_does_not_hit_the_database():
    calls = []

    class _Counting(_Lines):
        def latest_season(self):
            calls.append(1)
            return 2026

    with patch.object(calendar, "MarketLinesDatabase", lambda: _Counting({})):
        assert calendar.current_season() == 2026
        assert calendar.current_season() == 2026
    assert len(calls) == 1


def test_an_expired_entry_is_read_again():
    calls = []

    class _Counting(_Lines):
        def latest_season(self):
            calls.append(1)
            return 2026

    with patch.object(calendar, "MarketLinesDatabase", lambda: _Counting({})):
        calendar.current_season()
        with patch.object(calendar, "TTL_SECONDS", -1):
            calendar.current_season()
    assert len(calls) == 2
