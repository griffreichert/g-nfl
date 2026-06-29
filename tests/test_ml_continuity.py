"""Tests for L4 O-line continuity features (#29).

Headline guard is anti-leakage: a team's continuity index for a game must
reflect only its *prior* games' lineup churn, never the current one.
"""

import polars as pl

from g_nfl.ml.features.continuity import _ol5, add_continuity, ol_continuity


def _snaps(rows: list[dict]) -> pl.DataFrame:
    """Minimal snap_counts. rows: game_id, team, week, player, snaps,
    pos (default OL 'G'). All REG season 2023."""
    return pl.DataFrame(
        [
            {
                "game_type": "REG",
                "season": 2023,
                "week": r["week"],
                "game_id": r["game_id"],
                "team": r["team"],
                "pfr_player_id": r["player"],
                "position": r.get("pos", "G"),
                "offense_snaps": r["snaps"],
            }
            for r in rows
        ]
    )


def _ol_game(game_id, team, week, players, snaps=60):
    """Five OL starters plus a non-OL (WR) that must be excluded."""
    return [
        {"game_id": game_id, "team": team, "week": week, "player": p, "snaps": snaps}
        for p in players
    ] + [
        {
            "game_id": game_id,
            "team": team,
            "week": week,
            "player": "wr1",
            "snaps": 60,
            "pos": "WR",
        }
    ]


# KC: stable line wk1->wk2 (all 5 retained), one swap wk2->wk3 (4 retained)
W1 = _ol_game("g1", "KC", 1, ["a", "b", "c", "d", "e"])
W2 = _ol_game("g2", "KC", 2, ["a", "b", "c", "d", "e"])
W3 = _ol_game("g3", "KC", 3, ["a", "b", "c", "d", "f"])
ROWS = W1 + W2 + W3


def test_ol5_excludes_non_linemen_and_caps_at_five():
    extra = ROWS + [
        {"game_id": "g1", "team": "KC", "week": 1, "player": "z", "snaps": 5}
    ]
    o = _ol5(_snaps(extra)).filter(pl.col("game_id") == "g1").row(0, named=True)
    assert set(o["ol5"]) == {"a", "b", "c", "d", "e"}  # 5 top OL, no WR, no z


def test_continuity_lags_current_game():
    c = {
        r["game_id"]: r["ol_continuity"]
        for r in ol_continuity(_snaps(ROWS)).iter_rows(named=True)
    }
    # g1: no prior game -> null
    assert c["g1"] is None
    # g2: entering it, only g1 played (no retention sample yet) -> still null
    assert c["g2"] is None
    # g3: entering it, sees the g1->g2 swap only (all 5 retained) = 5.0.
    # The g2->g3 swap (4 retained) must NOT be in g3's own feature (leak guard)
    assert c["g3"] == 5.0


def test_add_continuity_attaches_home_away():
    matrix = pl.DataFrame(
        {
            "game_id": ["g1", "g2", "g3"],
            "home_team": ["KC", "KC", "KC"],
            "away_team": ["X", "X", "X"],
        }
    )
    out = add_continuity(matrix, _snaps(ROWS))
    assert "home_ol_continuity" in out.columns
    assert "away_ol_continuity" in out.columns
    g3 = out.filter(pl.col("game_id") == "g3").row(0, named=True)
    assert g3["home_ol_continuity"] == 5.0
    assert g3["away_ol_continuity"] is None  # team X has no snaps -> null
