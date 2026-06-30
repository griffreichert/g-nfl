"""Tests for L4 starting-QB player-grain features (#29).

The headline guard is anti-leakage: a QB's EWMA attached to a game must
reflect only his *prior* games, never the current one.
"""

import datetime as dt

import polars as pl

from g_nfl.ml.features.qb import (
    add_qb_context,
    add_qb_downgrade,
    qb_game_history,
    starters,
)


def _pbp(rows: list[dict]) -> pl.DataFrame:
    """Minimal dropback-level pbp. rows: game_id, posteam, qb, date,
    play_id, qb_epa, cpoe (all REG-season dropbacks)."""
    return pl.DataFrame(
        [
            {
                "season_type": "REG",
                "qb_dropback": 1,
                "game_id": r["game_id"],
                "posteam": r["posteam"],
                "passer_player_id": r["qb"],
                "game_date": r["date"],
                "play_id": r["play_id"],
                "qb_epa": r["qb_epa"],
                "cpoe": r["cpoe"],
            }
            for r in rows
        ]
    )


# QB "A" (KC): great week-1 game, then a bad week-2 game.
W1, W2 = dt.date(2023, 9, 10), dt.date(2023, 9, 17)
ROWS = [
    {
        "game_id": "g1",
        "posteam": "KC",
        "qb": "A",
        "date": W1,
        "play_id": 10,
        "qb_epa": 1.0,
        "cpoe": 10.0,
    },
    {
        "game_id": "g1",
        "posteam": "KC",
        "qb": "A",
        "date": W1,
        "play_id": 20,
        "qb_epa": 1.0,
        "cpoe": 10.0,
    },
    {
        "game_id": "g1",
        "posteam": "KC",
        "qb": "C",
        "date": W1,
        "play_id": 30,
        "qb_epa": -5.0,
        "cpoe": 0.0,
    },
    {
        "game_id": "g2",
        "posteam": "KC",
        "qb": "A",
        "date": W2,
        "play_id": 10,
        "qb_epa": -3.0,
        "cpoe": -20.0,
    },
]


def test_starter_is_most_dropbacks():
    # A threw 2, C threw 1 in g1 -> A starts
    s = starters(_pbp(ROWS)).filter(pl.col("game_id") == "g1")
    assert s.row(0, named=True)["passer_player_id"] == "A"


def test_history_lags_current_game():
    hist = qb_game_history(_pbp(ROWS), half_life=1000)
    a = {
        r["game_id"]: r
        for r in hist.filter(pl.col("passer_player_id") == "A").iter_rows(named=True)
    }
    # g1 is A's first game -> no prior state
    assert a["g1"]["qb_epa_ewm"] is None
    assert a["g1"]["qb_dropbacks"] is None  # filled to 0 only in add_qb_context
    # g2 sees only g1: positive EPA, 2 prior dropbacks, 1 prior game.
    # The bad g2 plays must NOT pull it down (leakage guard).
    assert a["g2"]["qb_epa_ewm"] > 0.5
    assert a["g2"]["qb_dropbacks"] == 2
    assert a["g2"]["qb_games"] == 1


def test_add_qb_context_attaches_and_cold_starts():
    matrix = pl.DataFrame(
        {
            "game_id": ["g1", "g2"],
            "home_team": ["KC", "KC"],
            "away_team": ["BUF", "BUF"],
        }
    )
    out = add_qb_context(matrix, _pbp(ROWS))
    for c in (
        "home_qb_epa_ewm",
        "home_qb_cpoe_ewm",
        "home_qb_dropbacks",
        "home_qb_games",
    ):
        assert c in out.columns
    g1 = out.filter(pl.col("game_id") == "g1").row(0, named=True)
    g2 = out.filter(pl.col("game_id") == "g2").row(0, named=True)
    # cold start: KC's QB has no prior game in g1 -> null EWMA, 0 volume
    assert g1["home_qb_epa_ewm"] is None
    assert g1["home_qb_dropbacks"] == 0
    # g2 carries g1's positive form
    assert g2["home_qb_epa_ewm"] > 0.5
    assert g2["home_qb_dropbacks"] == 2


# downgrade scenario: KC's good starter A (g1,g2), then backup C starts g3.
# C has prior history on BUF (a bad game) so his personal EWMA is non-null.
W3, W4 = dt.date(2023, 9, 24), dt.date(2023, 10, 1)
DOWN_ROWS = ROWS[:2] + [  # A's two good g1 plays, plus a good g2 start
    {
        "game_id": "g2",
        "posteam": "KC",
        "qb": "A",
        "date": W2,
        "play_id": 10,
        "qb_epa": 1.0,
        "cpoe": 10.0,
    },
    {
        "game_id": "gb",
        "posteam": "BUF",
        "qb": "C",
        "date": W1,
        "play_id": 10,
        "qb_epa": -2.0,
        "cpoe": -30.0,
    },
    {
        "game_id": "g3",
        "posteam": "KC",
        "qb": "C",
        "date": W3,
        "play_id": 10,
        "qb_epa": -2.0,
        "cpoe": -30.0,
    },
]


def test_downgrade_negative_for_backup():
    matrix = pl.DataFrame(
        {"game_id": ["g2", "g3"], "home_team": ["KC", "KC"], "away_team": ["X", "X"]}
    )
    out = add_qb_downgrade(matrix, _pbp(DOWN_ROWS), half_life=1000)
    g2 = out.filter(pl.col("game_id") == "g2").row(0, named=True)
    g3 = out.filter(pl.col("game_id") == "g3").row(0, named=True)
    # usual starter A back in g2 -> ~0
    assert abs(g2["home_qb_downgrade"]) < 0.2
    # backup C (career -2) starts g3 vs KC's ~+1 baseline -> strongly negative
    assert g3["home_qb_downgrade"] < -1.0
