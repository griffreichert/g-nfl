"""Tests for #47 carryover continuity: per-team-season discontinuity
signals (new QB / new coach / round-1 infusion) that discount how much
prior-season rate a team keeps.

Headline guard: a team with more discontinuity should carry LESS of its
prior-season rate (blend sits closer to its current rate) than an
identical team with no discontinuity.
"""

import polars as pl
import pytest

from g_nfl.ml.features.carryover import (
    _first_rounders_signal,
    add_carryover,
    continuity_from_discontinuity,
    team_discontinuity,
)
from g_nfl.ml.features.windows import add_windows


def _pbp_row(team: str, season: int, week: int, qb: str) -> dict:
    return {
        "season_type": "REG",
        "qb_dropback": 1,
        "posteam": team,
        "passer_player_id": qb,
        "season": season,
        "week": week,
    }


def _schedule_row(season: int, week: int, home_coach: str, away_coach: str) -> dict:
    return {
        "game_type": "REG",
        "season": season,
        "week": week,
        "home_team": "KC",
        "away_team": "BUF",
        "home_coach": home_coach,
        "away_coach": away_coach,
    }


def _draft_row(team: str, season: int) -> dict:
    return {"season": season, "round": 1, "team": team}


# KC: new QB 2022->2023, new coach 2022->2023, 2 round-1 picks in 2023
# BUF: same QB, same coach, no round-1 picks -> disc_count 0 both seasons
PBP = pl.DataFrame(
    [
        _pbp_row("KC", 2022, 1, "qbA"),
        _pbp_row("KC", 2022, 2, "qbA"),
        _pbp_row("KC", 2023, 1, "qbB"),
        _pbp_row("BUF", 2022, 1, "qbX"),
        _pbp_row("BUF", 2022, 2, "qbX"),
        _pbp_row("BUF", 2023, 1, "qbX"),
    ]
)

SCHEDULE = pl.DataFrame(
    [
        _schedule_row(2022, 1, "CoachOldKC", "CoachB"),
        _schedule_row(2022, 2, "CoachOldKC", "CoachB"),  # 2022 final week for both
        _schedule_row(2023, 1, "CoachNewKC", "CoachB"),
    ]
)

DRAFT = pl.DataFrame([_draft_row("KC", 2023), _draft_row("KC", 2023)])


def test_team_discontinuity_counts_all_three_signals():
    out = team_discontinuity(PBP, SCHEDULE, DRAFT)
    rows = {
        (r["team"], r["season"]): r["disc_count"] for r in out.iter_rows(named=True)
    }
    assert rows[("KC", 2023)] == 4  # qb_change + coach_change + 2 first-rounders
    assert rows[("BUF", 2023)] == 0


def test_first_loaded_season_has_no_prior_qb_or_coach_signal():
    # 2022 is the earliest loaded season -> no 2021 to compare against, so
    # qb_change/coach_change must default to 0, not error or leak forward
    out = team_discontinuity(PBP, SCHEDULE, DRAFT)
    rows = {
        (r["team"], r["season"]): r["disc_count"] for r in out.iter_rows(named=True)
    }
    assert rows[("KC", 2022)] == 0
    assert rows[("BUF", 2022)] == 0


def test_first_rounders_standardizes_historic_team_abbrevs():
    # OAK is a historic abbrev for LV (#47 spec) -- must route through
    # standardize_teams before counting
    draft = pl.DataFrame([_draft_row("OAK", 2023)])
    out = _first_rounders_signal(draft)
    row = out.filter((pl.col("team") == "LV") & (pl.col("season") == 2023))
    assert row.height == 1
    assert row["first_rounders"][0] == 1


# ---- continuity wired into add_carryover ----


def _weekly(team: str, prior_rate: float, cur_rate: float) -> list[dict]:
    return [
        {"team": team, "season": 2022, "week": 1, "epa_mean": prior_rate},
        {"team": team, "season": 2023, "week": 1, "epa_mean": cur_rate},
    ]


def test_continuity_scalar_one_matches_default_behavior():
    weekly = pl.DataFrame(_weekly("AAA", 10.0, 2.0))
    schedule = pl.DataFrame({"season": [2022, 2023], "week": [1, 1]})
    baseline = add_windows(weekly, schedule, carryover_k=1.0)
    cont = pl.DataFrame(
        {"team": ["AAA", "AAA"], "season": [2022, 2023], "continuity": [1.0, 1.0]}
    )
    with_frame = add_windows(
        weekly, schedule, carryover_k=1.0, carryover_continuity=cont
    )
    assert with_frame["epa_mean_carry"].to_list() == pytest.approx(
        baseline["epa_mean_carry"].to_list()
    )


def test_discontinuity_team_carries_less_of_prior_rate():
    # identical cur/prior/games for both teams; only continuity differs
    weekly = pl.DataFrame(_weekly("HI", 10.0, 2.0) + _weekly("LO", 10.0, 2.0))
    schedule = pl.DataFrame({"season": [2022, 2023], "week": [1, 1]})
    cont = pl.DataFrame(
        {
            "team": ["HI", "LO"],
            "season": [2023, 2023],
            "continuity": [1.0, 0.25],  # LO = high discontinuity, e.g. c=0.5, d=2
        }
    )
    out = add_windows(weekly, schedule, carryover_k=1.0, carryover_continuity=cont)
    hi = out.filter((pl.col("team") == "HI") & (pl.col("season") == 2023))[
        "epa_mean_carry"
    ][0]
    lo = out.filter((pl.col("team") == "LO") & (pl.col("season") == 2023))[
        "epa_mean_carry"
    ][0]
    cur_rate = 2.0
    # lower continuity -> lower blend weight on prior -> closer to cur
    assert abs(lo - cur_rate) < abs(hi - cur_rate)


def test_continuity_from_discontinuity_c_one_is_flat_one():
    disc = pl.DataFrame(
        {"team": ["A", "B"], "season": [2023, 2023], "disc_count": [0, 4]}
    )
    out = continuity_from_discontinuity(disc, c=1.0)
    assert out["continuity"].to_list() == [1.0, 1.0]


def test_continuity_from_discontinuity_scales_with_disc_count():
    disc = pl.DataFrame(
        {"team": ["A", "B"], "season": [2023, 2023], "disc_count": [0, 2]}
    )
    out = continuity_from_discontinuity(disc, c=0.5)
    rows = {r["team"]: r["continuity"] for r in out.iter_rows(named=True)}
    assert rows["A"] == pytest.approx(1.0)
    assert rows["B"] == pytest.approx(0.25)


def test_add_carryover_accepts_continuity_dataframe_directly():
    """add_carryover itself (not just add_windows) joins a continuity
    frame and defaults missing team-seasons to 1.0."""
    rolled = pl.DataFrame(
        {
            "team": ["AAA", "AAA"],
            "season": [2022, 2023],
            "week": [1, 1],
            "epa_mean_season": [10.0, 2.0],
        }
    )
    cont = pl.DataFrame({"team": ["ZZZ"], "season": [2023], "continuity": [0.1]})
    out = add_carryover(rolled, k=1.0, continuity=cont)
    # AAA has no row in cont -> defaults to continuity=1.0 -> same as scalar default
    scalar_out = add_carryover(rolled, k=1.0, continuity=1.0)
    assert out["epa_mean_carry"].to_list() == pytest.approx(
        scalar_out["epa_mean_carry"].to_list()
    )
