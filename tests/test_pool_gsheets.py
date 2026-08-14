"""The three workbook layouts all have to land on the same favourite.

A sign error here is silent and total — it flips every ATS grade in the
sample — so each layout gets a row whose favourite is unambiguous.
"""

from g_nfl.pool.gsheets import _parse_lines_block, _parse_visitor_home, season_week


def _lines_grid(pool_cell: str, market_cell: str) -> list[list[str]]:
    return [
        ["*Game*", "*Spread*", "", "*Moneyline*", "", "", "Pool Spread"],
        [
            "Green Bay Packers at New York Giants",
            market_cell,
            "",
            "",
            "",
            "",
            pool_cell,
        ],
    ]


def test_named_pool_cell_wins_over_the_market_column():
    # 2021 spelling: the pool cell names its own favourite
    (game,) = _parse_lines_block(_lines_grid("NYG -2.5", "GB -8"))
    assert (game["fav"], game["dog"], game["spread"]) == ("NYG", "GB", 2.5)


def test_bare_pool_magnitude_takes_the_favourite_from_the_market():
    # 2022 spelling: '8' is a magnitude, GB -8 says who it belongs to
    (game,) = _parse_lines_block(_lines_grid("8", "GB -8 (-110)"))
    assert (game["fav"], game["dog"], game["spread"]) == ("GB", "NYG", 8.0)


def test_a_pick_em_market_drops_the_row_rather_than_guessing():
    assert _parse_lines_block(_lines_grid("1.5", "PICK (-110)")) == []


def test_positive_visitor_home_pool_means_the_home_team_is_favoured():
    grid = [["Visitor", "Pool", "Home"], ["NYG", "3.5", "GB"], ["DAL", "-7", "WAS"]]
    giants, cowboys = _parse_visitor_home(grid)
    assert (giants["fav"], giants["dog"], giants["spread"]) == ("GB", "NYG", 3.5)
    assert (cowboys["fav"], cowboys["dog"], cowboys["spread"]) == ("DAL", "WAS", 7.0)


def test_unlabelled_pool_column_between_the_teams_is_still_found():
    # 2023 week 5 leaves the middle header blank
    grid = [["Visitor", "", "Home"], ["NYG", "3.5", "GB"]]
    (game,) = _parse_visitor_home(grid)
    assert game["fav"] == "GB"


def test_a_typo_team_is_dropped_not_guessed():
    assert _parse_visitor_home([["Visitor", "Pool", "Home"], ["ATL", "3", "MO"]]) == []


def test_the_stray_2024_tab_does_not_count_as_a_2023_week():
    assert season_week(2023, "2024/2025 Week 1") is None
    assert season_week(2024, "2024/2025 Week 1") == 1
    assert season_week(2023, "Wk 5") == 5
    assert season_week(2023, "Wild Card") == 19


def _picks_grid(bb_label: str = "BB") -> list[list[str]]:
    """A week tab in the 2022 shape: slot column, then picker/result pairs."""
    return [
        ["", "Ben"],
        ["Picks", "TEAM", "", "Notes", "Ben", "", "Chuck"],
        [bb_label, "NYJ", "2", "Russ out", "NYJ", "2", "ARI"],
        ["1", "NO", "0", "", "NO", "0", "PIT"],
        ["2", "ATL", "0", "", "ATL", "0", "NYJ"],
        ["3", "NYG", "1", "", "WAS", "1", "KC"],
        ["4", "SEA", "1", "", "SEA", "1", "CLE"],
        ["5", "KC", "1", "", "KC", "1", "LAC"],
        ["UD", "NYG", "1", "", "IND", "0", "PIT"],
        ["MNF", "NE", "0", "", "NE", "0", "CHI"],
        ["Week Score", "5.3", "", "", "5", "", "6"],
    ]


def test_picks_grid_reads_every_picker_column():
    from g_nfl.pool.gsheets import parse_picks_grid

    picks = parse_picks_grid(_picks_grid())
    assert {p["picker"] for p in picks} == {"Team", "Ben", "Chuck"}
    assert len([p for p in picks if p["picker"] == "Ben"]) == 8
    bb = next(p for p in picks if p["picker"] == "Chuck" and p["slot"] == "bb")
    assert (bb["team_picked"], bb["pick_type"]) == ("ARI", "best_bet")


def test_an_annotated_slot_label_still_counts():
    from g_nfl.pool.gsheets import parse_picks_grid

    # 2021 week 3 wrote "BB. Late dad change"
    picks = parse_picks_grid(_picks_grid("BB. Late dad change"))
    assert any(p["slot"] == "bb" for p in picks)


def test_a_result_grid_does_not_steal_the_slot_column():
    from g_nfl.pool.gsheets import parse_picks_grid

    # a second copy of the grid further right must not win the slot column
    grid = [row + [""] * (28 - len(row)) for row in _picks_grid()]
    for i, slot in enumerate(["BB", "1", "2", "3", "4", "5", "UD", "MNF"]):
        grid[i + 2][26] = slot
        grid[i + 2][27] = "GB"
    picks = parse_picks_grid(grid)
    assert {p["picker"] for p in picks} == {"Team", "Ben", "Chuck"}


def test_notes_and_consensus_columns_are_not_pickers():
    from g_nfl.pool.gsheets import parse_picks_grid

    picks = parse_picks_grid(_picks_grid())
    assert "Notes" not in {p["picker"] for p in picks}
