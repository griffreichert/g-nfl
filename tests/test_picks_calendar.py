"""Deriving the current season and week from the database (#61).

These replaced `CUR_SEASON` and `CUR_WEEK`, two constants somebody had to
remember to bump. Nine days before the 2026 opener they still read 2025 and
week 12, which is what the app opened on.
"""

from unittest.mock import patch

from g_nfl.picks import calendar


class _Lines:
    def __init__(self, weeks, counts, seasons=(2026,)):
        self._weeks, self._counts, self._seasons = weeks, counts, seasons

    def get_available_weeks(self, season):
        return self._weeks

    def games_per_week(self, season):
        return self._counts

    def seasons(self):
        return list(self._seasons)


class _Results:
    def __init__(self, rows):
        self._rows = rows

    def get_results(self, season):
        return self._rows


def _week(weeks, counts, results, default=99):
    with (
        patch.object(calendar, "MarketLinesDatabase", lambda: _Lines(weeks, counts)),
        patch.object(calendar, "GameResultsDatabase", lambda: _Results(results)),
    ):
        return calendar.current_week(2026, default=default)


def test_a_season_nobody_has_played_is_on_week_one():
    assert _week([1, 2, 3], {1: 16, 2: 16, 3: 16}, []) == 1


def test_a_week_holds_until_its_last_game_is_graded():
    results = [{"week": 1, "result": 3.0}] * 15
    assert _week([1, 2], {1: 16, 2: 16}, results) == 1


def test_the_week_rolls_over_once_every_game_is_in():
    results = [{"week": 1, "result": 3.0}] * 16
    assert _week([1, 2], {1: 16, 2: 16}, results) == 2


def test_an_ungraded_row_does_not_count_as_played():
    results = [{"week": 1, "result": None}] * 16
    assert _week([1, 2], {1: 16, 2: 16}, results) == 1


def test_a_finished_season_stays_on_its_last_week():
    results = [{"week": 1, "result": 3.0}] * 16 + [{"week": 2, "result": 3.0}] * 16
    assert _week([1, 2], {1: 16, 2: 16}, results) == 2


def test_no_lines_at_all_falls_back_rather_than_guessing():
    assert _week([], {}, [], default=7) == 7


def test_the_season_is_the_latest_one_we_hold_lines_for():
    with patch.object(
        calendar, "MarketLinesDatabase", lambda: _Lines([], {}, (2024, 2026, 2025))
    ):
        assert calendar.current_season() == 2026
