"""Draft state persistence and what striking does to the board (issue #79)."""

import polars as pl

from g_nfl.fantasy.draft_state import load_drafted, save_drafted, toggle
from g_nfl.fantasy.projections.board import build_board


def test_state_survives_a_round_trip(tmp_path):
    """A refresh mid-draft must not lose picks, so this cannot live in memory."""
    path = tmp_path / "nested" / "draft_state.json"
    save_drafted({"00-0001", "00-0002"}, path)

    assert load_drafted(path) == {"00-0001", "00-0002"}


def test_missing_file_is_an_empty_draft(tmp_path):
    assert load_drafted(tmp_path / "absent.json") == set()


def test_toggle_adds_and_removes():
    assert toggle(set(), "a", is_drafted=True) == {"a"}
    assert toggle({"a", "b"}, "a", is_drafted=False) == {"b"}


def _pool() -> pl.DataFrame:
    """Twelve RBs and twelve WRs on a declining curve."""
    return pl.DataFrame(
        {
            "gsis_id": [f"rb{i}" for i in range(12)] + [f"wr{i}" for i in range(12)],
            "player_name": [f"RB {i}" for i in range(12)]
            + [f"WR {i}" for i in range(12)],
            "position": ["RB"] * 12 + ["WR"] * 12,
            "proj_ppg": [20.0 - i for i in range(12)] + [20.0 - i for i in range(12)],
        }
    )


def test_striking_a_run_of_backs_revalues_the_rest():
    """The reason strike recomputes rather than greying rows out.

    Take the top six RBs off the board and replacement level at RB drops to a
    worse player, so every surviving back gains against it. A board that ignored
    this would keep pricing RBs off a pool that no longer exists.

    Receivers gain too, and that is not a bug: with the backs gone the FLEX slot
    starts eating WRs, which pushes WR replacement deeper. Positional scarcity
    is coupled through the flex, which is precisely what a static board cannot
    show you.
    """
    roster = ["RB", "RB", "WR", "WR", "FLEX"]
    full = build_board(_pool(), teams=2, roster_positions=roster)

    survivors = _pool().filter(~pl.col("gsis_id").is_in([f"rb{i}" for i in range(6)]))
    after = build_board(survivors, teams=2, roster_positions=roster)

    def ppgar(board: pl.DataFrame, gsis_id: str) -> float:
        return board.filter(pl.col("gsis_id") == gsis_id)["ppgar"][0]

    assert ppgar(after, "rb6") > ppgar(full, "rb6")
    assert ppgar(after, "wr0") > ppgar(full, "wr0")
