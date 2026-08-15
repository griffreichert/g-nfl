"""PicksDatabase.save_picks: note plumbing and replace ordering (#70).

The ordering matters: save_picks replaces a picker's week, and if it
deleted before inserting, a failed insert would leave them with nothing.
"""

import pytest

from g_nfl.utils.database import PicksDatabase


class FakeTable:
    """Records calls and lets a test make the insert blow up."""

    def __init__(self, log, existing, insert_error=None):
        self.log = log
        self.existing = existing
        self.insert_error = insert_error
        self._op = None
        self._rows = None

    def select(self, *_):
        self._op = "select"
        return self

    def insert(self, rows):
        self._op = "insert"
        self._rows = rows
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, *_):
        return self

    def in_(self, _col, ids):
        self._ids = ids
        return self

    def execute(self):
        if self._op == "insert":
            if self.insert_error:
                self.log.append(("insert_failed", self._rows))
                raise self.insert_error
            self.log.append(("insert", self._rows))
            return type("R", (), {"data": self._rows})
        if self._op == "delete":
            self.log.append(("delete", self._ids))
            return type("R", (), {"data": []})
        self.log.append(("select", None))
        return type("R", (), {"data": self.existing})


class FakeClient:
    def __init__(self, existing=(), insert_error=None):
        self.log = []
        self.existing = list(existing)
        self.insert_error = insert_error

    def table(self, _name):
        return FakeTable(self.log, self.existing, self.insert_error)


def _db(client) -> PicksDatabase:
    db = PicksDatabase.__new__(PicksDatabase)
    db.client = client
    return db


PICKS = {
    "2025_01_DAL_PHI": {
        "team_picked": "PHI",
        "pick_type": "regular",
        "spread": -3.5,
        "note": "line moved off the injury news",
    },
    "survivor_2025_01_KC_LAC": {
        "team_picked": "KC",
        "pick_type": "survivor",
        "spread": -4.0,
    },
}


def test_note_is_persisted_and_absent_note_is_none():
    client = FakeClient()
    assert _db(client).save_picks(2025, 1, PICKS, "Griffin") == 2
    rows = dict(
        (r["game_id"], r) for _, payload in client.log if _ == "insert" for r in payload
    )
    assert rows["2025_01_DAL_PHI"]["note"] == "line moved off the injury news"
    assert rows["2025_01_KC_LAC"]["note"] is None
    assert rows["2025_01_KC_LAC"]["pick_type"] == "survivor"


def test_replace_inserts_before_deleting_stale_rows():
    client = FakeClient(existing=[{"id": 11}, {"id": 12}])
    _db(client).save_picks(2025, 1, PICKS, "Griffin")
    ops = [op for op, _ in client.log]
    assert ops == ["select", "insert", "delete"]
    assert client.log[-1][1] == [11, 12]


def test_failed_insert_leaves_existing_picks_alone():
    client = FakeClient(
        existing=[{"id": 11}], insert_error=RuntimeError("no note column")
    )
    with pytest.raises(RuntimeError):
        _db(client).save_picks(2025, 1, PICKS, "Griffin")
    assert "delete" not in [op for op, _ in client.log]
