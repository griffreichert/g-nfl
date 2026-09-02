"""Turn the committed board artifact into a survivor `Board` (#72).

`survivor.py` is the algorithm and knows nothing about where numbers come
from. This is the seam: schedule and power ratings out of the checked-in
JSON (`picks/boards/`), a real market line laid over the top wherever one
exists, everything converted to win probability.

Stdlib only — it runs on the deployed API, which has no polars and no
route to nflverse.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

from g_nfl.picks.boards import board_path
from g_nfl.picks.survivor import Board, win_probability
from g_nfl.utils.config import SPREAD_STDEV

LAST_REG_WEEK = 18

# How a team is doubted, on a 0-4 scale the user sets by hand.
#
# Ratings say what a team is; neither of these does. Confidence is how wrong
# the rating might be *today* — a new coach, a new quarterback, a roster that
# turned over — and it does not decay. Fragility is how fast the rating goes
# stale: injuries accumulate, coordinators get fired, a bad team quits in
# December. So one is a level and the other a slope, in points of spread:
#
#     tau(team, h) = CONFIDENCE_STEP * conf + FRAGILITY_STEP * frag * h
#
# with `h` the weeks between now and the game. Both default to 0, which
# reproduces the board exactly as it was before anyone touched a slider.
#
# The steps are sized so a maxed slider changes a decision rather than a
# decimal. Confidence 4 is 5 points of doubt about the rating, which is
# most of the gap between a good team and an average one. Fragility 4 is
# 2.4 points a week, so a team you think could be unrecognisable by
# December is barely favoured in week 17 however good it looks today. A
# 4 on either is meant to be rare and loud.
CONFIDENCE_STEP = 1.25
FRAGILITY_STEP = 0.15

#: team -> (confidence 0-4, fragility 0-4)
Doubts = dict[str, tuple[float, float]]


def team_doubt(doubts: Doubts, team: str, horizon: int) -> float:
    """Points of extra spread uncertainty about one team in one week."""
    conf, frag = doubts.get(team, (0.0, 0.0))
    return CONFIDENCE_STEP * conf + FRAGILITY_STEP * frag * max(horizon, 0)


def game_stdev(doubts: Doubts, home: str, away: str, horizon: int) -> float:
    """Standard deviation of the margin, once both teams are doubted.

    Uncertainty about either side is uncertainty about the margin, and the
    two are independent, so they add in quadrature on top of the league
    baseline. The effect is to pull a win probability toward 50% — which
    is the point: doubt costs you most on the big favourite you were
    saving, and almost nothing on a coin flip you would never pick.
    """
    tau_sq = (
        team_doubt(doubts, home, horizon) ** 2 + team_doubt(doubts, away, horizon) ** 2
    )
    return math.sqrt(SPREAD_STDEV**2 + tau_sq)


@lru_cache(maxsize=4)
def load_artifact(season: int) -> dict[str, Any]:
    """The generated board for a season. Raises FileNotFoundError if it
    was never built — `scripts/build_survivor_board.py --season <year>`."""
    return json.loads(board_path(season).read_text())


def build_board(
    season: int,
    from_week: int,
    spent: list[str] | None = None,
    market_spreads: dict[str, float] | None = None,
    doubts: Doubts | None = None,
) -> tuple[Board, list[str], list[int]]:
    """Board, selectable teams and remaining weeks, from `from_week` on.

    `market_spreads` maps game_id to the home spread and wins over the
    artifact's model spread — the book is sharper than the ratings for
    any week it has actually priced. `spent` teams are dropped entirely;
    they can never be picked again. `doubts` widens the margin
    distribution per team (see `game_stdev`).
    """
    artifact = load_artifact(season)
    spent_set = set(spent or ())
    market = market_spreads or {}
    doubted = doubts or {}

    weeks = [w for w in range(from_week, LAST_REG_WEEK + 1)]
    teams = sorted(t for t in artifact["ratings"] if t not in spent_set)
    board = Board(teams, weeks)

    for game in artifact["games"]:
        week = game["week"]
        if week < from_week:
            continue
        spread = market.get(game["game_id"], game["model_spread"])
        priced = game["game_id"] in market
        stdev = game_stdev(doubted, game["home"], game["away"], week - from_week)
        for team, margin, opponent, home in (
            (game["home"], spread, game["away"], True),
            (game["away"], -spread, game["home"], False),
        ):
            if team in spent_set:
                continue
            board.add(
                team,
                week,
                win_probability(margin, stdev),
                {
                    "game_id": game["game_id"],
                    "opponent": opponent,
                    "home": home,
                    "spread": round(margin, 2),
                    "source": "market" if priced else "model",
                    # how much of this cell is doubt rather than the line
                    "stdev": round(stdev, 2),
                },
            )

    return board, teams, weeks


def cells(board: Board) -> list[dict[str, Any]]:
    """Every (team, week) on the board, flat, for the season matrix."""
    return [
        {"team": team, "week": week, "win_prob": prob, **board.game[(team, week)]}
        for (team, week), prob in sorted(board.prob.items())
    ]
