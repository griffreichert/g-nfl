"""`fetch_all` exists because PostgREST truncates at 1000 rows in silence.

A season of pool picks came back short with no error, so the failure mode
being tested is "looks fine, is wrong".
"""

from g_nfl.utils.database import PAGE_SIZE, fetch_all


class FakeQuery:
    """Minimal stand-in for a supabase query builder."""

    def __init__(self, rows, calls):
        self._rows = rows
        self._calls = calls
        self._ordered = False

    def order(self, column):
        self._ordered = column
        return self

    def range(self, start, end):
        self._start, self._end = start, end
        return self

    def execute(self):
        assert self._ordered, "paging without an order is not reproducible"
        self._calls.append((self._start, self._end))
        return type("R", (), {"data": self._rows[self._start : self._end + 1]})


def _fetch(n):
    rows = [{"id": i} for i in range(n)]
    calls: list[tuple[int, int]] = []
    return fetch_all(lambda: FakeQuery(rows, calls)), calls


def test_a_short_first_page_is_one_request():
    got, calls = _fetch(10)
    assert len(got) == 10
    assert len(calls) == 1


def test_more_than_a_page_keeps_going():
    got, calls = _fetch(2679)  # the pool_picks season that exposed this
    assert [r["id"] for r in got] == list(range(2679))
    assert len(calls) == 3


def test_an_exact_multiple_still_takes_a_final_empty_page():
    # otherwise the loop would stop one page early only when it got lucky
    got, calls = _fetch(PAGE_SIZE * 2)
    assert len(got) == PAGE_SIZE * 2
    assert len(calls) == 3


def test_no_rows_at_all():
    got, calls = _fetch(0)
    assert got == []
    assert len(calls) == 1
