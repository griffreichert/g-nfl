"""gModel against the room (plan item 5).

The sign of `model_edge` is the whole measurement: get it backwards and every
table reads inside out, so most of these pin the direction down.
"""

import pytest

from g_nfl.picks import model_room


def row(
    game_id="2025_01_AAA_BBB",
    picker="p1",
    team="BBB",
    opp="AAA",
    picked_home=True,
    line=-3.0,
    won=True,
    slot="regular",
    season=2025,
    week=1,
):
    """One graded pick, in the shape `analytics.graded_rows` hands back."""
    return {
        "picker": picker,
        "season": season,
        "week": week,
        "game_id": game_id,
        "slot": slot,
        "team": team,
        "opp": opp,
        "picked_home": picked_home,
        "line": line,
        "picked_spread": None if line is None else (-line if picked_home else line),
        "won": won,
    }


def test_the_model_liking_the_home_side_is_a_positive_edge_for_a_home_pick():
    """Home spread −3, model line −6: the model likes home by 3 more."""
    attached = model_room.attach_model([row(line=-3.0)], {"2025_01_AAA_BBB": -6.0})
    assert attached[0]["model_edge"] == pytest.approx(-3.0)


def test_the_edge_flips_with_the_side_taken():
    home, away = row(picked_home=True), row(team="AAA", opp="BBB", picked_home=False)
    preds = {"2025_01_AAA_BBB": 4.0}
    assert model_room.attach_model([home], preds)[0]["model_edge"] == pytest.approx(7.0)
    assert model_room.attach_model([away], preds)[0]["model_edge"] == pytest.approx(
        -7.0
    )


def test_a_game_the_model_never_predicted_is_dropped():
    assert model_room.attach_model([row()], {}) == []


def test_a_pick_with_no_line_is_dropped():
    assert model_room.attach_model([row(line=None)], {"2025_01_AAA_BBB": 3.0}) == []


@pytest.mark.parametrize(
    ("edge", "band"),
    [
        (0.5, "agrees <1"),
        (-0.5, "disagrees <1"),
        (1.0, "agrees <3"),
        (-6.9, "disagrees <7"),
        (7.0, "agrees 7+"),
        (-12.0, "disagrees 7+"),
    ],
)
def test_the_bands_are_signed_by_agreement_and_sized_by_the_gap(edge, band):
    assert model_room.edge_band(edge) == band


def test_the_control_band_drops_the_direction():
    assert model_room.edge_size(-6.9) == model_room.edge_size(6.9) == "<7"


def test_the_side_that_covered_is_read_off_a_losing_pick():
    winners = model_room.ats_winners([row(team="BBB", opp="AAA", won=False)])
    assert winners["2025_01_AAA_BBB"] == "AAA"


def test_the_model_takes_the_side_it_likes():
    attached = model_room.attach_model([row()], {"2025_01_AAA_BBB": -6.0})
    assert model_room.model_sides(attached)["2025_01_AAA_BBB"] == "AAA"


def _split_rows(votes_bbb, votes_aaa, won=True, pred=-9.0):
    rows = [
        row(picker=f"m{i}", team="BBB", opp="AAA", picked_home=True, won=won)
        for i in range(votes_bbb)
    ] + [
        row(picker=f"n{i}", team="AAA", opp="BBB", picked_home=False, won=not won)
        for i in range(votes_aaa)
    ]
    return model_room.attach_model(rows, {"2025_01_AAA_BBB": pred})


def test_an_even_split_is_a_tiebreak_the_model_can_settle():
    splits = model_room.even_splits(_split_rows(3, 3))
    assert len(splits) == 1
    assert splits[0]["model_side"] == "AAA"
    assert splits[0]["model_won"] is False


def test_a_lopsided_game_is_not_a_split():
    assert model_room.even_splits(_split_rows(4, 2)) == []


def test_two_people_disagreeing_is_not_the_room_splitting():
    assert model_room.even_splits(_split_rows(1, 1)) == []


def test_the_submitted_entry_does_not_vote_in_the_split():
    rows = _split_rows(3, 2) + model_room.attach_model(
        [row(picker="TEAM", team="AAA", opp="BBB", picked_home=False, won=False)],
        {"2025_01_AAA_BBB": -9.0},
    )
    assert model_room.even_splits(rows) == []


def test_the_veto_fires_only_on_a_side_the_model_dislikes_enough():
    rule = model_room.veto_rule(3.0)
    assert rule.matches({"model_edge": -3.0})
    assert not rule.matches({"model_edge": -2.9})
    assert not rule.matches({"model_edge": 8.0})


def test_the_veto_ignores_a_pick_the_model_has_no_view_on():
    """The rule runs beside four that read a row with no model columns."""
    assert not model_room.veto_rule(3.0).matches({"picked_spread": -9.0})


def test_the_model_votes_once_per_slot_on_its_own_side():
    attached = model_room.attach_model([row()], {"2025_01_AAA_BBB": -6.0})
    votes = model_room.model_votes(attached)
    assert {v["pick_type"] for v in votes} == {"best_bet", "regular", "mnf"}
    assert {v["team_picked"] for v in votes} == {"AAA"}


def test_the_majority_is_scored_on_a_side_no_member_took():
    """The only member took BBB and lost, so the model's AAA has no row."""
    rows = model_room.attach_model([row(won=False)], {"2025_01_AAA_BBB": -9.0})
    assert model_room.majority_points(rows, model_room.model_votes(rows)) == (1.0, 1.0)


def test_the_model_vote_can_move_the_majority():
    """A 2-2 room becomes 3-2 for the side the model likes, and it loses."""
    rows = _split_rows(2, 2, won=False, pred=0.0)
    members = [model_room.as_pick(r) for r in rows]
    assert model_room.majority_points(rows, members)[0] == 1.0
    assert (
        model_room.majority_points(rows, members + model_room.model_votes(rows))[0]
        == 0.0
    )
