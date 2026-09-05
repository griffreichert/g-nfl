"""ModelRunsDatabase: run identity and the submitted flag (#13).

`picks` carries no run_id, so `submitted` is the only link from gModel's
entry back to the numbers behind it. Two runs of a week claiming it makes
that link ambiguous, and the week's entry is whichever run wrote last.
"""

from g_nfl.utils.database import ModelRunsDatabase


class FakeTable:
    """Records updates with the filters they were narrowed by."""

    def __init__(self, log, existing):
        self.log = log
        self.existing = existing
        self._op = None
        self._values = None
        self._filters = {}

    def select(self, *_):
        self._op = "select"
        return self

    def update(self, values):
        self._op = "update"
        self._values = values
        return self

    def upsert(self, row, on_conflict=None):
        self._op = "upsert"
        self._values = row
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def execute(self):
        self.log.append((self._op, self._values, dict(self._filters)))
        return type("R", (), {"data": self.existing if self._op == "select" else []})


class FakeClient:
    def __init__(self, existing=()):
        self.log = []
        self.existing = list(existing)

    def table(self, _name):
        return FakeTable(self.log, self.existing)


def db(client: FakeClient) -> ModelRunsDatabase:
    """A ModelRunsDatabase talking to a fake, no Supabase at import."""
    handle = ModelRunsDatabase.__new__(ModelRunsDatabase)
    handle.client = client
    return handle


RUN = {
    "model": "gModel",
    "season": 2026,
    "week": 1,
    "fingerprint": "7c1f9e4b",
    "feature_set": "v5_early_adj",
}


def test_a_new_fingerprint_mints_a_run_id():
    client = FakeClient(existing=[])
    run_id = db(client).save_run(RUN)
    written = next(v for op, v, _ in client.log if op == "upsert")
    assert written["run_id"] == run_id
    assert len(run_id) == 36


def test_the_same_fingerprint_keeps_its_run_id():
    """A cron retry against unchanged inputs is not a second run."""
    client = FakeClient(existing=[{"run_id": "019283af-dead-beef"}])
    assert db(client).save_run(RUN) == "019283af-dead-beef"


def test_submitting_clears_the_weeks_other_runs():
    client = FakeClient()
    db(client).mark_submitted("019283af", 2026, 1, "gModel")

    cleared, claimed = [(op, v, f) for op, v, f in client.log if op == "update"]
    assert cleared[1] == {"submitted": False}
    assert cleared[2] == {"season": 2026, "week": 1, "model": "gModel"}
    assert claimed[1] == {"submitted": True}
    assert claimed[2] == {"run_id": "019283af"}


def test_the_clear_comes_before_the_claim():
    """Reversed, the run that just submitted would clear its own flag."""
    client = FakeClient()
    db(client).mark_submitted("019283af", 2026, 1, "gModel")
    values = [v for op, v, _ in client.log if op == "update"]
    assert values == [{"submitted": False}, {"submitted": True}]
