"""The gModel entry (#13).

The entry is a benchmark, so what matters is that the rules are followed
exactly: the slots it fills, the games it does not reuse, and the fact that
two runs on the same numbers are the same run.
"""

from dataclasses import dataclass

import polars as pl
import pytest

from g_nfl.picks import gmodel


@dataclass
class Game:
    game_id: str
    away_team: str
    home_team: str
    pool_spread: float | None
    market_spread: float | None = None
    is_mnf: bool = False


def slate(spreads: dict[str, float], mnf: str | None = None) -> list[Game]:
    """One game per entry: {'AAA@BBB': home pool spread}."""
    games = []
    for matchup, spread in spreads.items():
        away, home = matchup.split("@")
        games.append(
            Game(
                game_id=f"2026_01_{away}_{home}",
                away_team=away,
                home_team=home,
                pool_spread=spread,
                market_spread=spread,
                is_mnf=matchup == mnf,
            )
        )
    return games


def predictions(games: list[Game], preds: dict[str, float]) -> pl.DataFrame:
    """A predict_week frame: {'AAA@BBB': predicted home margin}."""
    return pl.DataFrame(
        [
            {
                "game_id": g.game_id,
                "season": 2026,
                "week": 1,
                "away_team": g.away_team,
                "home_team": g.home_team,
                "spread_line": g.market_spread,
                "pred": preds[f"{g.away_team}@{g.home_team}"],
            }
            for g in games
        ]
    )


@pytest.fixture
def board() -> list[dict]:
    """Eight games whose edges run from +8 down to +0.5, MNF last."""
    lines = {
        "AAA@BBB": 0.0,
        "CCC@DDD": 0.0,
        "EEE@FFF": 0.0,
        "GGG@HHH": 0.0,
        "III@JJJ": 0.0,
        "KKK@LLL": 0.0,
        "MMM@NNN": 0.0,
        "OOO@PPP": 3.0,
    }
    preds = {
        "AAA@BBB": 8.0,
        "CCC@DDD": -7.0,
        "EEE@FFF": 6.0,
        "GGG@HHH": -5.0,
        "III@JJJ": 4.0,
        "KKK@LLL": -3.0,
        "MMM@NNN": 2.0,
        "OOO@PPP": 3.5,
    }
    games = slate(lines, mnf="OOO@PPP")
    return gmodel.board_rows(predictions(games, preds), games)


def test_board_carries_every_game_not_just_the_picks(board):
    assert len(board) == 8


def test_edge_is_the_model_against_the_pool_line(board):
    row = next(r for r in board if r["game_id"] == "2026_01_OOO_PPP")
    assert row["pred_margin"] == 3.5
    assert row["pool_spread"] == 3.0
    assert row["edge"] == pytest.approx(0.5)
    assert row["line_source"] == "pool"


def test_market_line_stands_in_when_the_pool_line_is_missing():
    games = slate({"AAA@BBB": 0.0})
    games[0].pool_spread = None
    games[0].market_spread = -2.0
    rows = gmodel.board_rows(predictions(games, {"AAA@BBB": 1.0}), games)
    assert rows[0]["edge"] == pytest.approx(3.0)
    assert rows[0]["line_source"] == "market"


def test_a_game_with_no_line_still_gets_a_prediction():
    games = slate({"AAA@BBB": 0.0})
    games[0].pool_spread = None
    games[0].market_spread = None
    rows = gmodel.board_rows(predictions(games, {"AAA@BBB": 1.0}), games)
    assert rows[0]["pred_margin"] == 1.0
    assert rows[0]["edge"] is None
    assert rows[0]["line_source"] is None


def test_entry_fills_every_slot(board):
    entry = gmodel.build_entry(board, mnf_ids={"2026_01_OOO_PPP"}, spent=set())
    types = [p["pick_type"] for p in entry]
    assert types.count("best_bet") == 1
    assert types.count("regular") == gmodel.REGULARS
    assert types.count("mnf") == 1
    assert types.count("underdog") == 1
    assert types.count("survivor") == 1


def test_entry_never_picks_a_game_twice(board):
    entry = gmodel.build_entry(board, mnf_ids={"2026_01_OOO_PPP"}, spent=set())
    ats = [p for p in entry if p["pick_type"] in ("best_bet", "regular", "mnf")]
    assert len({p["game_id"] for p in ats}) == len(ats)


def test_best_bet_is_the_largest_edge(board):
    entry = gmodel.build_entry(board, mnf_ids={"2026_01_OOO_PPP"}, spent=set())
    best = next(p for p in entry if p["pick_type"] == "best_bet")
    assert best["game_id"] == "2026_01_AAA_BBB"
    assert best["team_picked"] == "BBB"


def test_mnf_comes_from_the_monday_game(board):
    entry = gmodel.build_entry(board, mnf_ids={"2026_01_OOO_PPP"}, spent=set())
    mnf = next(p for p in entry if p["pick_type"] == "mnf")
    assert mnf["game_id"] == "2026_01_OOO_PPP"


def test_the_side_taken_is_the_one_the_model_likes(board):
    """A negative home edge means the away team, and vice versa."""
    entry = gmodel.build_entry(board, mnf_ids={"2026_01_OOO_PPP"}, spent=set())
    by_game = {r["game_id"]: r for r in board}
    for pick in entry:
        if pick["pick_type"] not in ("best_bet", "regular", "mnf"):
            continue
        row = by_game[pick["game_id"]]
        expected = row["home_team"] if row["edge"] > 0 else row["away_team"]
        assert pick["team_picked"] == expected


def test_survivor_does_not_spend_a_team_twice(board):
    entry = gmodel.build_entry(
        board, mnf_ids={"2026_01_OOO_PPP"}, spent={"BBB", "FFF", "PPP"}
    )
    survivor = next(p for p in entry if p["pick_type"] == "survivor")
    assert survivor["team_picked"] not in {"BBB", "FFF", "PPP"}


def test_underdog_maximises_win_probability_times_the_spread():
    """A 14-point dog wins too rarely to beat a live one getting 7."""
    games = slate({"AAA@BBB": 14.0, "CCC@DDD": 7.0})
    board = gmodel.board_rows(
        predictions(games, {"AAA@BBB": 14.0, "CCC@DDD": 7.0}), games
    )
    dog = gmodel.underdog(gmodel.sides(board))
    assert dog["team"] == "CCC"


def test_a_thin_slate_gives_a_short_entry():
    games = slate({"AAA@BBB": 0.0})
    board = gmodel.board_rows(predictions(games, {"AAA@BBB": 3.0}), games)
    entry = gmodel.build_entry(board, mnf_ids=set(), spent=set())
    assert [p["pick_type"] for p in entry] == ["best_bet", "survivor"]


def test_the_same_numbers_are_the_same_run(board):
    config = {"feature_set": "v5_early_adj", "git_sha": "abc123"}
    assert gmodel.fingerprint(config, board) == gmodel.fingerprint(config, board)


def test_a_moved_line_is_a_new_run(board):
    """Saturday's corrected line must not overwrite Wednesday's board."""
    config = {"feature_set": "v5_early_adj", "git_sha": "abc123"}
    moved = [{**r} for r in board]
    moved[0]["pool_spread"] = (moved[0]["pool_spread"] or 0) + 1.0
    assert gmodel.fingerprint(config, moved) != gmodel.fingerprint(config, board)


def test_a_changed_prediction_is_a_new_run(board):
    """A QB ruled out on Friday moves the features, so it moves the run."""
    config = {"feature_set": "v5_early_adj", "git_sha": "abc123"}
    repredicted = [{**r} for r in board]
    repredicted[0]["pred_margin"] += 2.5
    assert gmodel.fingerprint(config, repredicted) != gmodel.fingerprint(config, board)


def test_a_changed_config_is_a_new_run(board):
    base = {"feature_set": "v5_early_adj", "git_sha": "abc123"}
    assert gmodel.fingerprint(base, board) != gmodel.fingerprint(
        {**base, "git_sha": "def456"}, board
    )


def test_an_entry_on_a_fixed_slate_is_deterministic(board):
    """The issue's acceptance test: same board in, same entry out."""
    first = gmodel.build_entry(board, mnf_ids={"2026_01_OOO_PPP"}, spent=set())
    second = gmodel.build_entry(board, mnf_ids={"2026_01_OOO_PPP"}, spent=set())
    assert first == second


def test_the_table_sorts_by_the_market_not_the_pool():
    """The pool line is what grades, the market is what tells you anything."""
    games = slate({"AAA@BBB": 0.0, "CCC@DDD": 0.0})
    games[0].pool_spread, games[0].market_spread = 9.0, 1.0  # small market gap
    games[1].pool_spread, games[1].market_spread = 1.0, 9.0  # big market gap
    board = gmodel.board_rows(
        predictions(games, {"AAA@BBB": 2.0, "CCC@DDD": 2.0}), games
    )
    table = gmodel.format_board(2026, 1, board, entry=[])
    rows = [ln for ln in table.splitlines() if "@" in ln and "matchup" not in ln]
    assert rows[0].startswith("CCC @ DDD")


def test_every_slot_on_a_game_is_listed(board):
    """The best bet and the underdog are often the same side."""
    entry = gmodel.build_entry(board, mnf_ids={"2026_01_OOO_PPP"}, spent=set())
    table = gmodel.format_board(2026, 1, board, entry)
    line = next(ln for ln in table.splitlines() if ln.startswith("AAA @ BBB"))
    assert "BBB best_bet" in line


def test_a_game_with_no_line_still_prints():
    games = slate({"AAA@BBB": 0.0})
    games[0].pool_spread = None
    games[0].market_spread = None
    board = gmodel.board_rows(predictions(games, {"AAA@BBB": 3.0}), games)
    line = next(
        ln
        for ln in gmodel.format_board(2026, 1, board, []).splitlines()
        if ln.startswith("AAA @ BBB")
    )
    assert "--" in line
