"""The two queries the season/week calendar runs (#141).

Filtering ungraded rows moved out of `picks.calendar` and into
`graded_per_week`, so it is covered here instead.
"""

from g_nfl.utils.database import GameResultsDatabase, MarketLinesDatabase


class _Query:
    """A PostgREST builder that records its filters and replays fixed rows."""

    def __init__(self, rows):
        self._rows = rows
        self._limit = None
        self._desc = False

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, _column, desc=False):
        self._desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        self._rows = self._rows[start : end + 1]
        return self

    def execute(self):
        rows = (
            sorted(self._rows, key=lambda r: r.get("season", 0), reverse=True)
            if self._desc
            else self._rows
        )
        if self._limit is not None:
            rows = rows[: self._limit]
        return type("R", (), {"data": rows})()


class _Client:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _Query(list(self._rows))


def _lines(rows):
    db = MarketLinesDatabase.__new__(MarketLinesDatabase)
    db.client = _Client(rows)
    return db


def _results(rows):
    db = GameResultsDatabase.__new__(GameResultsDatabase)
    db.client = _Client(rows)
    return db


def test_latest_season_takes_the_top_row():
    assert (
        _lines([{"season": 2024}, {"season": 2026}, {"season": 2025}]).latest_season()
        == 2026
    )


def test_latest_season_is_none_on_an_empty_table():
    assert _lines([]).latest_season() is None


def test_graded_per_week_counts_by_week():
    rows = [
        {"week": 1, "result": 3.0},
        {"week": 1, "result": -7.0},
        {"week": 2, "result": 0.0},
    ]
    assert _results(rows).graded_per_week(2026) == {1: 2, 2: 1}


def test_graded_per_week_skips_an_ungraded_row():
    rows = [{"week": 1, "result": 3.0}, {"week": 1, "result": None}]
    assert _results(rows).graded_per_week(2026) == {1: 1}


def test_graded_per_week_is_empty_when_nothing_is_played():
    assert _results([{"week": 1, "result": None}]).graded_per_week(2026) == {}
