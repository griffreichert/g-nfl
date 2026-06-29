"""Tests for team-week injury aggregates (#18)."""

import polars as pl
import pytest

from g_nfl.ml.features.injuries import team_week_injuries


def _report(rows: list[tuple[str, int, str, str, str | None]]) -> pl.DataFrame:
    """(team, week, position, report_status, game_type) rows."""
    return pl.DataFrame(
        {
            "season": [2025] * len(rows),
            "game_type": [r[4] or "REG" for r in rows],
            "team": [r[0] for r in rows],
            "week": [r[1] for r in rows],
            "position": [r[2] for r in rows],
            "report_status": [r[3] for r in rows],
        }
    )


def test_counts_by_group_and_severity():
    report = _report(
        [
            ("KC", 1, "QB", "Out", None),
            ("KC", 1, "WR", "Questionable", None),
            ("KC", 1, "RB", "Doubtful", None),
            ("KC", 1, "T", "Out", None),
            ("KC", 1, "CB", "Out", None),
        ]
    )
    out = team_week_injuries(report)
    row = out.row(0, named=True)
    assert row["inj_qb_out"] == 1
    assert row["inj_skill_q"] == 2  # WR questionable + RB doubtful
    assert row["inj_skill_out"] == 0
    assert row["inj_ol_out"] == 1
    assert row["inj_def_out"] == 1
    # burden: Out=1.0, Doubtful=0.75, Questionable=0.5
    assert row["inj_qb_burden"] == 1.0
    assert row["inj_skill_burden"] == pytest.approx(1.25)


def test_listed_without_designation_ignored():
    # on the report with practice notes only -> not an absence signal
    report = _report([("BUF", 3, "WR", None, None)])
    out = team_week_injuries(report)
    assert out.is_empty()


def test_postseason_filtered_and_zero_fill():
    report = _report(
        [
            ("KC", 1, "QB", "Out", "POST"),
            ("BUF", 1, "K", "Questionable", None),
        ]
    )
    out = team_week_injuries(report)
    assert out.height == 1  # POST row dropped
    row = out.row(0, named=True)
    # kicker folds into def group; all other groups zero-filled
    assert row["inj_def_q"] == 1
    assert row["inj_qb_out"] == 0
    assert row["inj_qb_burden"] == 0.0


def test_one_row_per_team_week():
    report = _report(
        [
            ("KC", 1, "QB", "Out", None),
            ("KC", 2, "QB", "Out", None),
            ("BUF", 1, "WR", "Out", None),
        ]
    )
    out = team_week_injuries(report)
    assert out.height == 3
    assert out.select("team", "season", "week").unique().height == 3
