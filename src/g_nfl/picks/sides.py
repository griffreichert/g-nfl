"""One prospective pick, shaped the way the record is shaped (#58).

A side someone is thinking about and a side taken six seasons ago go through
the same predicates, so the live flag on the board and the backtest cannot end
up answering different questions. This is the adapter between a `GameLine` and
a row from :func:`g_nfl.picks.analytics.graded_rows`.
"""

from __future__ import annotations

from typing import Any, Protocol

from g_nfl.picks.analytics import from_picked, gap_side


class Game(Protocol):
    """What a candidate side needs to know about a game."""

    game_id: str
    away_team: str
    home_team: str
    pool_spread: float | None
    market_spread: float | None


def candidate_side(game: Game, team: str) -> dict[str, Any]:
    """`team`'s side of `game`, ready for the guardrail predicates.

    The line is the pool spread where we have one, since that is what the pool
    grades against, and the market close only while the Friday number is still
    to come.
    """
    picked_home = team == game.home_team
    line = game.pool_spread if game.pool_spread is not None else game.market_spread
    pool = from_picked(game.pool_spread, picked_home)
    market = from_picked(game.market_spread, picked_home)
    gap = None if pool is None or market is None else pool - market
    return {
        "game_id": game.game_id,
        "team": team,
        "picked_home": picked_home,
        "picked_spread": from_picked(line, picked_home),
        "gap": gap,
        "gap_side": None if gap is None else gap_side(gap),
        "won": False,  # unused by the predicates, present for shape
    }
