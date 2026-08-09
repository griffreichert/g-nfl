"""Tests for pick grading (#17): ATS and straight-up outcomes, pushes,
pending games, and standings aggregation."""

import pytest

from g_nfl.picks.grading import (
    WIN_PROFIT,
    grade_pick,
    picker_standings,
    resolve_lines,
)

# game: away DET @ home KC, spread +4 = KC favored by 4
GAME = "2023_01_DET_KC"


def _pick(team: str, pick_type: str = "regular", spread: float | None = 4.0) -> dict:
    return {
        "picker": "Griffin",
        "game_id": GAME,
        "team_picked": team,
        "pick_type": pick_type,
        "spread": spread,
        "season": 2023,
        "week": 1,
    }


class TestGradePickATS:
    def test_home_favorite_covers(self):
        # KC -4 wins by 7: KC pick wins, DET pick loses
        assert grade_pick(_pick("KC"), 7) == "win"
        assert grade_pick(_pick("DET"), 7) == "loss"

    def test_home_wins_but_fails_to_cover(self):
        # KC -4 wins by 3: dog DET covers
        assert grade_pick(_pick("KC"), 3) == "loss"
        assert grade_pick(_pick("DET"), 3) == "win"

    def test_push_lands_on_spread(self):
        assert grade_pick(_pick("KC"), 4) == "push"
        assert grade_pick(_pick("DET"), 4) == "push"

    def test_away_favorite(self):
        # spread -3.5 = away DET favored; DET wins by 40 -> covers
        assert grade_pick(_pick("DET", spread=-3.5), -40) == "win"
        assert grade_pick(_pick("KC", spread=-3.5), -40) == "loss"

    def test_pending_and_no_spread(self):
        assert grade_pick(_pick("KC"), None) == "pending"
        assert grade_pick(_pick("KC", spread=None), 7) == "no_spread"

    def test_mnf_and_best_bet_graded_ats(self):
        assert grade_pick(_pick("KC", pick_type="best_bet"), 7) == "win"
        assert grade_pick(_pick("DET", pick_type="mnf"), 3) == "win"


class TestGradePickStraightUp:
    def test_survivor_ignores_spread(self):
        # KC wins by 1: survivor KC survives even though it didn't cover
        assert grade_pick(_pick("KC", pick_type="survivor"), 1) == "win"
        assert grade_pick(_pick("KC", pick_type="survivor"), -1) == "loss"

    def test_underdog_needs_outright_win(self):
        # DET +4 loses by 1: covers ATS but underdog pool needs the win
        assert grade_pick(_pick("DET", pick_type="underdog"), 1) == "loss"
        assert grade_pick(_pick("DET", pick_type="underdog"), -6) == "win"

    def test_tie_is_push(self):
        assert grade_pick(_pick("KC", pick_type="survivor"), 0) == "push"


class TestPickerStandings:
    def _picks_and_results(self):
        games = {
            "2023_01_DET_KC": 7,  # KC -4 covers
            "2023_01_DAL_NYG": -40,  # away DAL -3.5 covers
            "2023_02_BUF_MIA": 0.0 + 2,  # see below
            "2023_02_ARI_SF": None,  # not played
        }
        picks = [
            # Griffin: week 1 win (KC), week 2 loss (MIA -3 wins by 2)
            {**_pick("KC"), "week": 1},
            {
                "picker": "Griffin",
                "game_id": "2023_02_BUF_MIA",
                "team_picked": "MIA",
                "pick_type": "best_bet",
                "spread": 3.0,
                "week": 2,
            },
            # Griffin survivor win - must NOT count toward ATS record
            {**_pick("KC", pick_type="survivor"), "week": 1},
            # Griffin pending pick
            {
                "picker": "Griffin",
                "game_id": "2023_02_ARI_SF",
                "team_picked": "SF",
                "pick_type": "regular",
                "spread": 15.0,
                "week": 2,
            },
            # Harry: one loss (DAL away favorite covers, Harry took NYG)
            {
                "picker": "Harry",
                "game_id": "2023_01_DAL_NYG",
                "team_picked": "NYG",
                "pick_type": "regular",
                "spread": -3.5,
                "week": 1,
            },
        ]
        return picks, {g: r for g, r in games.items()}

    def test_standings_records_and_units(self):
        picks, results = self._picks_and_results()
        standings = picker_standings(picks, results)

        griffin = next(s for s in standings if s["picker"] == "Griffin")
        # ATS record: KC win + MIA loss; survivor excluded; SF pending
        assert griffin["ats"]["wins"] == 1
        assert griffin["ats"]["losses"] == 1
        assert griffin["ats"]["pending"] == 1
        assert griffin["ats"]["win_pct"] == 0.5
        assert griffin["units"] == pytest.approx(WIN_PROFIT - 1, abs=1e-3)
        assert griffin["by_type"]["survivor"]["wins"] == 1
        assert griffin["by_type"]["best_bet"]["losses"] == 1

        harry = next(s for s in standings if s["picker"] == "Harry")
        assert harry["ats"]["losses"] == 1
        assert harry["units"] == -1.0

    def test_standings_sorted_by_units(self):
        picks, results = self._picks_and_results()
        standings = picker_standings(picks, results)
        units = [s["units"] for s in standings]
        assert units == sorted(units, reverse=True)

    def test_weekly_cumulative_trend(self):
        picks, results = self._picks_and_results()
        standings = picker_standings(picks, results)
        griffin = next(s for s in standings if s["picker"] == "Griffin")

        weekly = griffin["weekly"]
        assert [w["week"] for w in weekly] == [1, 2]
        assert weekly[0]["wins"] == 1
        assert weekly[0]["cum_units"] == pytest.approx(WIN_PROFIT, abs=1e-3)
        # week 2: MIA loss decided, SF pending
        assert weekly[1]["losses"] == 1
        assert weekly[1]["pending"] == 1
        assert weekly[1]["cum_units"] == pytest.approx(WIN_PROFIT - 1, abs=1e-3)
        assert weekly[1]["cum_win_pct"] == 0.5

    def test_no_spread_pick_reported_not_counted(self):
        picks = [_pick("KC", spread=None)]
        standings = picker_standings(picks, {GAME: 7})
        assert standings[0]["no_spread"] == 1
        assert standings[0]["ats"]["wins"] == 0


def test_resolve_lines_prefers_pool_and_falls_back_to_market():
    lines = resolve_lines(
        pool_rows=[{"game_id": "g1", "spread": 3.5}, {"game_id": "g3", "spread": None}],
        market_rows=[
            {"game_id": "g1", "spread": 7.0},
            {"game_id": "g2", "spread": 1.0},
            {"game_id": "g3", "spread": -2.0},
        ],
    )
    # pool wins where we have it, market fills the rest, a null pool row
    # does not blank out the market line behind it
    assert lines == {"g1": 3.5, "g2": 1.0, "g3": -2.0}


def test_pick_grades_on_the_resolved_line_not_the_stored_one():
    # Someone picked on Tuesday, before the Friday pool line existed, so the
    # row carries nothing. Grading off the row silently dropped this pick.
    pick = {
        "game_id": "2025_17_CAR_GB",
        "team_picked": "GB",
        "pick_type": "regular",
        "spread": None,
    }
    assert grade_pick(pick, result=10.0) == "no_spread"
    assert grade_pick(pick, result=10.0, line=3.5) == "win"
    assert grade_pick(pick, result=10.0, line=13.5) == "loss"
    assert grade_pick(pick, result=10.0, line=10.0) == "push"

    # A stale line on the row never beats the one we resolved for the game.
    stale = {**pick, "spread": 13.5}
    assert grade_pick(stale, result=10.0, line=3.5) == "win"


def test_standings_grade_against_supplied_lines():
    picks = [
        {
            "picker": "TEST",
            "game_id": "2025_17_CAR_GB",
            "team_picked": "GB",
            "pick_type": "regular",
            "spread": None,
            "week": 17,
        }
    ]
    results = {"2025_17_CAR_GB": 10.0}
    # no lines: ungradeable, exactly as before
    assert picker_standings(picks, results)[0]["no_spread"] == 1
    # with the pool line resolved, it grades
    graded = picker_standings(picks, results, {"2025_17_CAR_GB": 3.5})[0]
    assert graded["ats"]["wins"] == 1
    assert graded["no_spread"] == 0
