"""Tests for L4 QB-change delta triggered by the injury report (#41).

Headline guards: the downgrade is 0 unless the usual starter is actually
listed Out/Doubtful (Questionable doesn't trigger), the backup lookup
falls back to a replacement-level constant when the team has no 2nd QB,
and nothing about a future week can leak backward.
"""

import datetime as dt

import polars as pl
import pytest

from g_nfl.ml.features import build_features
from g_nfl.ml.features.qb_change import (
    add_qb_change,
    apply_qb_adjustment,
    team_week_qb_change,
)


def _pbp(rows: list[dict]) -> pl.DataFrame:
    """Minimal dropback-level pbp. rows: game_id, posteam, qb, season,
    week, date, play_id, qb_epa (all REG-season dropbacks)."""
    return pl.DataFrame(
        [
            {
                "season_type": "REG",
                "qb_dropback": 1,
                "game_id": r["game_id"],
                "posteam": r["posteam"],
                "passer_player_id": r["qb"],
                "season": r["season"],
                "week": r["week"],
                "game_date": r["date"],
                "play_id": r["play_id"],
                "qb_epa": r["qb_epa"],
                "cpoe": 0.0,
            }
            for r in rows
        ]
    )


def _injuries(rows: list[tuple[str, int, str, str]]) -> pl.DataFrame:
    """(team, week, gsis_id, report_status) rows for 2023 REG."""
    return pl.DataFrame(
        {
            "season": [2023] * len(rows),
            "game_type": ["REG"] * len(rows),
            "team": [r[0] for r in rows],
            "week": [r[1] for r in rows],
            "gsis_id": [r[2] for r in rows],
            "report_status": [r[3] for r in rows],
        }
    )


W = [dt.date(2023, 9, 3 + 7 * i) for i in range(4)]  # weeks 1-4


def _game(team: str, week: int, qb: str, plays: list[float], play_start: int = 0):
    return [
        {
            "game_id": f"{team}_{week}",
            "posteam": team,
            "qb": qb,
            "season": 2023,
            "week": week,
            "date": W[week - 1],
            "play_id": play_start + i,
            "qb_epa": epa,
        }
        for i, epa in enumerate(plays)
    ]


# KC: A starts weeks 1-3 (steady +1 EPA), B mops up 1 dropback (-4.0) in
# week 2. Week 3 A is Questionable (no trigger). Week 4 A is Out -> B
# (the only other KC passer, career -4.0) is the projected starter.
KC_ROWS = (
    _game("KC", 1, "A", [1.0, 1.0])
    + _game("KC", 2, "A", [1.0, 1.0])
    + _game("KC", 2, "B", [-4.0], play_start=10)
    + _game("KC", 3, "A", [1.0, 1.0])
    + _game("KC", 4, "B", [-2.0])
)
# BUF: single QB D all season, never reported -> control (always 0).
BUF_ROWS = (
    _game("BUF", 1, "D", [0.5, 0.5])
    + _game("BUF", 2, "D", [0.5, 0.5])
    + _game("BUF", 3, "D", [0.5, 0.5])
    + _game("BUF", 4, "D", [0.5, 0.5])
)
# DEN: single QB E all season (no backup ever) -> cold-backup case when
# reported Out in week 4.
DEN_ROWS = (
    _game("DEN", 1, "E", [2.0, 2.0])
    + _game("DEN", 2, "E", [2.0, 2.0])
    + _game("DEN", 3, "E", [2.0, 2.0])
    + _game("DEN", 4, "E", [2.0])
)

PBP = _pbp(KC_ROWS + BUF_ROWS + DEN_ROWS)
INJ = _injuries(
    [
        ("KC", 3, "A", "Questionable"),
        ("KC", 4, "A", "Out"),
        ("DEN", 4, "E", "Out"),
    ]
)


@pytest.fixture(scope="module")
def out() -> pl.DataFrame:
    return team_week_qb_change(PBP, INJ, half_life=1000)


def _row(out: pl.DataFrame, team: str, week: int) -> dict:
    return out.filter(
        (pl.col("posteam") == team) & (pl.col("game_id") == f"{team}_{week}")
    ).row(0, named=True)


def test_questionable_does_not_trigger(out: pl.DataFrame):
    r = _row(out, "KC", 3)
    assert r["qb_out"] == 0
    assert r["qb_downgrade"] == 0.0


def test_out_triggers_known_backup_downgrade(out: pl.DataFrame):
    # A's career EWM entering week 4 is a flat 1.0 (all his plays are
    # +1.0); B's is -4.0 (his only prior play, week 2). Downgrade = 5.0.
    r = _row(out, "KC", 4)
    assert r["qb_out"] == 1
    assert r["qb_downgrade"] == pytest.approx(5.0)


def test_no_report_stays_zero(out: pl.DataFrame):
    for week in range(1, 5):
        r = _row(out, "BUF", week)
        assert r["qb_out"] == 0
        assert r["qb_downgrade"] == 0.0


def test_cold_backup_uses_replacement_level(out: pl.DataFrame):
    # DEN has never had a 2nd passer -> backup is null -> downgrade falls
    # back to E's EWM minus the leaguewide week-4 replacement level (25th
    # pct of that week's usual-starter EWMs: KC's A=1.0, BUF's D=0.5,
    # DEN's E=2.0), recomputed independently here with the same formula.
    replacement = pl.Series([1.0, 0.5, 2.0]).quantile(0.25)
    r = _row(out, "DEN", 4)
    assert r["qb_out"] == 1
    assert r["qb_downgrade"] == pytest.approx(2.0 - replacement)


def test_first_game_no_prior_starter_is_zero(out: pl.DataFrame):
    # week 1 has no prior game -> usual_starter is null everywhere
    for team in ("KC", "BUF", "DEN"):
        r = _row(out, team, 1)
        assert r["qb_out"] == 0
        assert r["qb_downgrade"] == 0.0


def test_future_weeks_do_not_leak():
    """Perturb week-4 pbp EPA and mutate week-4 injury reports; weeks
    1-3 features must stay identical (own-week injury join is fine,
    lag on the EWMA is not up for negotiation)."""
    base = team_week_qb_change(PBP, INJ, half_life=1000)

    perturbed_pbp = PBP.with_columns(
        pl.when(pl.col("week") == 4)
        .then(pl.col("qb_epa") * 100 + 7)
        .otherwise(pl.col("qb_epa"))
        .alias("qb_epa")
    )
    perturbed_inj = pl.concat(
        [INJ, _injuries([("BUF", 4, "D", "Out")])], how="vertical_relaxed"
    )
    pert = team_week_qb_change(perturbed_pbp, perturbed_inj, half_life=1000)

    early = pl.col("game_id").str.contains("_1$|_2$|_3$")
    from polars.testing import assert_frame_equal

    assert_frame_equal(
        base.filter(early).sort("game_id", "posteam"),
        pert.filter(early).sort("game_id", "posteam"),
    )
    # sanity: week 4 actually did change
    assert not pert.filter(pl.col("game_id") == "BUF_4").equals(
        base.filter(pl.col("game_id") == "BUF_4")
    )


# ---- add_qb_change / build_features (real fixture: KC's Gabbert mop-up) ----


def test_add_qb_change_toggle_and_columns(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    # off by default: no qb_change columns at all
    base = build_features(pbp_sample, schedule_sample)
    assert not any(c.endswith(("qb_downgrade", "qb_out")) for c in base.columns)

    # KC's real backup B.Gabbert threw mop-up snaps in week 3 (2023
    # fixture); mark Mahomes Out in week 4 so he's the projected starter.
    inj = _injuries([("KC", 4, "00-0033873", "Out")])
    out = build_features(pbp_sample, schedule_sample, qb_change=inj)

    added = set(out.columns) - set(base.columns)
    assert added == {
        f"{side}_qb_{m}" for side in ("home", "away") for m in ("downgrade", "out")
    }

    kc_wk4 = out.filter(
        (pl.col("week") == 4)
        & ((pl.col("home_team") == "KC") | (pl.col("away_team") == "KC"))
    ).row(0, named=True)
    side = "home" if kc_wk4["home_team"] == "KC" else "away"
    other = "away" if side == "home" else "home"
    assert kc_wk4[f"{side}_qb_out"] == 1
    assert kc_wk4[f"{side}_qb_downgrade"] > 0  # Gabbert well below Mahomes
    assert kc_wk4[f"{other}_qb_out"] == 0  # opponent untouched
    assert kc_wk4[f"{other}_qb_downgrade"] == 0.0


def test_add_qb_change_matches_direct_call(
    pbp_sample: pl.DataFrame, schedule_sample: pl.DataFrame
):
    """add_qb_change's matrix attach == team_week_qb_change's raw output,
    joined by hand -- pins the join logic itself, not just the toggle."""
    inj = _injuries([("KC", 4, "00-0033873", "Out")])
    matrix = build_features(pbp_sample, schedule_sample)
    out = add_qb_change(matrix, pbp_sample, inj)
    direct = team_week_qb_change(pbp_sample, inj)

    kc_direct = direct.filter(
        (pl.col("posteam") == "KC") & (pl.col("game_id") == "2023_04_KC_NYJ")
    ).row(0, named=True)
    kc_row = out.filter(pl.col("game_id") == "2023_04_KC_NYJ").row(0, named=True)
    side = "home" if kc_row["home_team"] == "KC" else "away"
    assert kc_row[f"{side}_qb_downgrade"] == pytest.approx(kc_direct["qb_downgrade"])
    assert kc_row[f"{side}_qb_out"] == kc_direct["qb_out"]


# ---- apply_qb_adjustment ----


def test_apply_qb_adjustment_arithmetic_and_sign():
    # home downgrade positive -> pred decreases; away downgrade positive
    # -> pred increases; k=10 scales EPA/dropback units to points
    preds = pl.DataFrame(
        {
            "pred": [3.0, 3.0, 3.0],
            "home_qb_downgrade": [1.0, 0.0, 0.5],
            "away_qb_downgrade": [0.0, 1.0, 0.5],
        }
    )
    out = apply_qb_adjustment(preds, k=10.0)
    assert out["pred"].to_list() == pytest.approx([3.0 - 10.0, 3.0 + 10.0, 3.0])


def test_apply_qb_adjustment_treats_null_as_zero():
    preds = pl.DataFrame(
        {
            "pred": [3.0],
            "home_qb_downgrade": [None],
            "away_qb_downgrade": [None],
        },
        schema={
            "pred": pl.Float64,
            "home_qb_downgrade": pl.Float64,
            "away_qb_downgrade": pl.Float64,
        },
    )
    out = apply_qb_adjustment(preds, k=15.0)
    assert out["pred"].to_list() == pytest.approx([3.0])


def test_backtest_qb_adjust_k_requires_qb_change():
    from g_nfl.ml.evaluate import backtest

    with pytest.raises(ValueError, match="qb_change"):
        backtest([2023], qb_change=False, qb_adjust_k=10.0)
