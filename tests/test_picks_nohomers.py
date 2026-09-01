"""The mechanical entry (#58).

Its job is to be a benchmark with no judgement in it, so every test here is
about the rules being followed exactly, including where they are known to be
unimpressive.
"""

from dataclasses import dataclass

from g_nfl.picks import nohomers
from g_nfl.picks.guardrails import build_rules, load_config
from g_nfl.picks.guardrails import fit as fit_rules


@dataclass
class Game:
    game_id: str
    away_team: str
    home_team: str
    pool_spread: float | None
    market_spread: float | None = None
    is_mnf: bool = False


def _slate(spreads, mnf=None):
    """One game per entry: {'AAA@BBB': home spread}."""
    games = []
    for i, (matchup, spread) in enumerate(spreads.items()):
        away, home = matchup.split("@")
        games.append(
            Game(
                game_id=f"2026_01_{away}_{home}",
                away_team=away,
                home_team=home,
                pool_spread=spread,
                is_mnf=matchup == mnf,
            )
        )
        del i
    return games


NO_RULES = fit_rules([], load_config(), build_rules(load_config()))


def _by_slot(entry):
    return {p["pick_type"]: p["team_picked"] for p in entry}


def test_the_entry_takes_dogs_closest_line_first():
    games = _slate({"AAA@BBB": 1.0, "CCC@DDD": 6.0, "EEE@FFF": 3.0})
    entry = nohomers.build_entry(games, NO_RULES, spent=set())
    ats = [p for p in entry if p["pick_type"] in ("best_bet", "regular")]
    assert [p["team_picked"] for p in ats] == ["AAA", "EEE", "CCC"]


def test_the_best_bet_is_the_closest_line():
    """The double-points slot carries no information, so it gets the safest rule."""
    games = _slate({"AAA@BBB": 9.0, "CCC@DDD": 1.5})
    entry = nohomers.build_entry(games, NO_RULES, spent=set())
    assert _by_slot(entry)["best_bet"] == "CCC"


def test_it_never_uses_one_game_for_two_slots():
    games = _slate({f"A{i}@B{i}": 2.0 + i for i in range(8)})
    entry = nohomers.build_entry(games, NO_RULES, spent=set())
    ats = [p for p in entry if p["pick_type"] in ("best_bet", "regular", "mnf")]
    assert len({p["game_id"] for p in ats}) == len(ats)


def test_monday_is_claimed_before_the_regulars_take_its_game():
    games = _slate({"AAA@BBB": 1.0, "CCC@DDD": 7.0}, mnf="AAA@BBB")
    entry = nohomers.build_entry(games, NO_RULES, spent=set())
    slots = _by_slot(entry)
    # AAA is the closest dog, and it would have been the best bet on that rule
    assert slots["mnf"] == "AAA"
    assert slots["best_bet"] == "CCC"


def test_a_flagged_side_is_skipped_even_when_it_is_the_closest_dog():
    games = _slate({"AAA@BBB": -9.0, "CCC@DDD": 4.0})

    class _AlwaysFires:
        id, label, blurb, advisory = "test", "Test", "", False
        matches = staticmethod(lambda side: side["team"] == "BBB")

    class _Fit:
        rule, qualifies = _AlwaysFires(), True

    entry = nohomers.build_entry(games, [_Fit()], spent=set())
    ats = [p for p in entry if p["pick_type"] in ("best_bet", "regular", "mnf")]
    assert "BBB" not in [p["team_picked"] for p in ats]


def test_a_guardrail_does_not_touch_survivor_or_the_underdog():
    """Both pools pay on an outright win, so an ATS rule says nothing about them."""
    games = _slate({"AAA@BBB": -9.0, "CCC@DDD": 4.0})

    class _AlwaysFires:
        id, label, blurb, advisory = "test", "Test", "", False
        matches = staticmethod(lambda side: True)

    class _Fit:
        rule, qualifies = _AlwaysFires(), True

    entry = nohomers.build_entry(games, [_Fit()], spent=set())
    assert _by_slot(entry)["survivor"] == "AAA"
    assert not [p for p in entry if p["pick_type"] in ("best_bet", "regular")]


def test_an_advisory_rule_does_not_veto():
    """`pool_worse_than_market` reads the close, which does not exist yet."""
    games = _slate({"AAA@BBB": 2.0})

    class _Advisory:
        id, label, blurb, advisory = "advice", "Advice", "", True
        matches = staticmethod(lambda side: True)

    class _Fit:
        rule, qualifies = _Advisory(), True

    entry = nohomers.build_entry(games, [_Fit()], spent=set())
    assert _by_slot(entry)["best_bet"] == "AAA"


def test_the_underdog_comes_from_the_ev_band():
    games = _slate({"AAA@BBB": 14.0, "CCC@DDD": 8.0, "EEE@FFF": 2.0})
    entry = nohomers.build_entry(games, NO_RULES, spent=set())
    # 14 wins a fifth as often for the same expected points; 2 is below the band
    assert _by_slot(entry)["underdog"] == "CCC"


def test_no_dog_in_the_band_leaves_the_slot_empty():
    games = _slate({"AAA@BBB": 2.0})
    entry = nohomers.build_entry(games, NO_RULES, spent=set())
    assert "underdog" not in _by_slot(entry)


def test_survivor_skips_teams_already_spent():
    games = _slate({"AAA@BBB": 12.0, "CCC@DDD": 9.0})
    spent = nohomers.build_entry(games, NO_RULES, spent=set())
    assert _by_slot(spent)["survivor"] == "BBB"

    entry = nohomers.build_entry(games, NO_RULES, spent={"BBB"})
    assert _by_slot(entry)["survivor"] == "DDD"


def test_a_game_with_no_line_is_left_alone():
    games = _slate({"AAA@BBB": None, "CCC@DDD": 3.0})
    entry = nohomers.build_entry(games, NO_RULES, spent=set())
    assert {p["team_picked"] for p in entry} <= {"CCC", "DDD"}


def test_every_pick_records_the_spread_it_was_made_on():
    games = _slate({"AAA@BBB": 3.5})
    (pick, *_) = nohomers.build_entry(games, NO_RULES, spent=set())
    assert pick["team_picked"] == "AAA"
    assert pick["spread"] == 3.5
