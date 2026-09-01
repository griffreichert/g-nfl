"""Shaping a prospective pick for the guardrail predicates (#58).

The board asks about a side nobody has taken yet. It has to arrive at the rules
in the same shape as a row from `graded_rows`, or the live flag and the backtest
would be answering different questions.
"""

from g_nfl.api.schemas import GameLine
from g_nfl.picks.guardrails import build_rules, load_config
from g_nfl.picks.sides import candidate_side


def _game(pool=None, market=None):
    return GameLine(
        game_id="2026_01_CAR_GB",
        away_team="CAR",
        home_team="GB",
        pool_spread=pool,
        market_spread=market,
        market_total=None,
        is_mnf=False,
    )


def test_the_spread_is_flipped_for_the_home_side():
    game = _game(pool=6.5)
    assert candidate_side(game, "GB")["picked_spread"] == -6.5
    assert candidate_side(game, "CAR")["picked_spread"] == 6.5


def test_the_pool_line_wins_over_the_market_when_both_exist():
    """Picks grade against the pool spread, so the flag has to use it too."""
    side = candidate_side(_game(pool=3.0, market=6.5), "CAR")
    assert side["picked_spread"] == 3.0


def test_the_market_line_stands_in_before_friday():
    side = candidate_side(_game(pool=None, market=6.5), "CAR")
    assert side["picked_spread"] == 6.5


def test_the_gap_is_read_from_the_picked_side():
    # GB laying 3 in the pool and 4 on the market: taking GB lays a point less,
    # so the pool prices that side better and CAR worse.
    game = _game(pool=3.0, market=4.0)
    assert candidate_side(game, "GB")["gap_side"] == "better"
    assert candidate_side(game, "CAR")["gap_side"] == "worse"


def test_no_market_line_means_no_gap_rather_than_a_zero():
    side = candidate_side(_game(pool=3.0), "CAR")
    assert side["gap"] is None
    assert side["gap_side"] is None


def test_a_candidate_side_satisfies_every_rule_predicate():
    """Whatever the config holds, no rule may blow up on a live side."""
    side = candidate_side(_game(pool=9.5, market=9.0), "CAR")
    for rule in build_rules(load_config()):
        assert rule.matches(side) in (True, False)
