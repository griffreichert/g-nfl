"""Snapshot ingest for fantasy projections (issue #81). Network- and DB-free."""

from datetime import date

import polars as pl
import pytest

from g_nfl.fantasy.ingest import SOURCES, ingest, to_rows


class FakeDB:
    """Stands in for FantasyProjectionsDatabase without a Supabase client."""

    def __init__(self):
        self.saved: list[dict] = []

    def save_snapshot(self, rows: list[dict]) -> int:
        self.saved = rows
        return len(rows)


def _stat_lines() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gsis_id": ["00-0034796", None],
            "espn_id": [3139477, 1],
            "player_name": ["Lamar Jackson", "Nobody"],
            "position": ["QB", "WR"],
            "team": ["BAL", "SEA"],
            "pass_yd": [3800.0, 0.0],
            "pass_td": [30.0, 0.0],
            "ints": [8.0, 0.0],
            "rush_yd": [820.0, 0.0],
            "rush_td": [5.0, 0.0],
            "rec": [0.0, 40.0],
            "rec_yd": [0.0, 500.0],
            "rec_td": [0.0, 3.0],
            "fum": [4.0, 1.0],
        }
    )


def test_rows_carry_the_snapshot_key_and_drop_unjoinable_players():
    rows = to_rows(_stat_lines(), "espn", 2026, date(2026, 8, 17))

    assert len(rows) == 1  # the null gsis_id row is unjoinable downstream
    row = rows[0]
    assert row["snapshot_date"] == "2026-08-17"
    assert row["source"] == "espn"
    assert row["season"] == 2026
    assert row["player_id"] == "00-0034796"
    assert row["pass_yd"] == 3800.0
    assert "espn_id" not in row  # source-specific id has no column


def test_rushing_and_receiving_touchdowns_stay_separate():
    """#81's sketch had one `td`; scoring.py prices the two independently."""
    row = to_rows(_stat_lines(), "espn", 2026, date(2026, 8, 17))[0]
    assert row["rush_td"] == 5.0
    assert row["rec_td"] == 0.0


def test_ingest_writes_through_to_the_db(monkeypatch):
    monkeypatch.setitem(SOURCES, "fake", lambda season: _stat_lines())
    db = FakeDB()

    written = ingest(2026, "fake", date(2026, 8, 17), db=db)

    assert written == 1
    assert db.saved[0]["source"] == "fake"


def test_an_unknown_source_fails_before_the_network():
    with pytest.raises(ValueError, match="Unknown source"):
        ingest(2026, "nope", db=FakeDB())
