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

# Confidence: how well a picker thinks a team's rating will hold up, on a
# 1-5 scale where 3 is no opinion and 5 is good.
#
# Ratings say what a team is. They do not say how long that stays true.
# A 5 is "this is what they are, all season" — the Rams. A 1 is a team
# you expect to stop resembling itself: an injury away, a coach on a hot
# seat, a bad roster that quits in December. 3 changes nothing.
#
# This started as two knobs, confidence and fragility, and collapsed to
# one on 2026-09-02. The reason: a flat term moves a team's probability
# equally in every week, so it changes *whether* you spend them, barely
# *when* — and when is the only question survivor asks. "The rating is
# wrong today" is a claim the ratings should answer, not a slider. So the
# surviving knob is the one that grows with distance.
#
#     tau(team, h) = (NEUTRAL - confidence) * (FLAT + SLOPE * h)
#
# with `h` the weeks between now and the game. Positive tau widens the
# margin distribution and pulls the win probability toward a coin flip;
# negative sharpens it. The flat part is small on purpose: doubt about
# December should barely touch this Sunday.
#
# Sizing: a 1 costs about five points of certainty by week 17, enough to
# move a team out of a week rather than nudge a decimal. Widening a
# distribution is a weak lever in the 60-80% band where survivor lives,
# so the slope has to be generous to mean anything at all.
NEUTRAL = 3
CONFIDENCE_FLAT = 0.5
CONFIDENCE_SLOPE = 0.35

# Conviction is damped against doubt, deliberately. Being wrong about a
# team has a real mechanism — they get hurt, they quit, the coach goes —
# while being right only means the line was already correct, and the line
# is the best estimate anyone has. So trust sharpens a game far less than
# suspicion blurs it.
CONVICTION_DAMPING = 0.35

#: However sure anyone claims to be, the margin is not this predictable.
MIN_STDEV_FRACTION = 0.7

#: team -> confidence, 1-5
Doubts = dict[str, float]


def team_doubt(doubts: Doubts, team: str, horizon: int) -> float:
    """Points of spread uncertainty this team adds, or removes.

    Negative above neutral: a team the picker trusts to still be itself
    in December is more predictable than the league baseline, not less.
    """
    conf = doubts.get(team, NEUTRAL)
    tau = (NEUTRAL - conf) * (CONFIDENCE_FLAT + CONFIDENCE_SLOPE * max(horizon, 0))
    return tau * CONVICTION_DAMPING if tau < 0 else tau


def game_stdev(doubts: Doubts, home: str, away: str, horizon: int) -> float:
    """Standard deviation of the margin, once both teams are judged.

    Uncertainty about either side is uncertainty about the margin, and the
    two are independent, so they meet in quadrature on top of the league
    baseline — signed, so conviction can sharpen a game as well as doubt
    blurring one. Widening pulls a win probability toward 50%, which is
    the point: doubt costs most on the big favourite you were saving and
    nothing on the coin flip you would never take.

    Floored at `MIN_STDEV_FRACTION` of the baseline. Nobody knows a game
    that well, and without a floor a wall of 5s would manufacture
    certainties the schedule cannot support.
    """
    signed = 0.0
    for team in (home, away):
        tau = team_doubt(doubts, team, horizon)
        signed += math.copysign(tau**2, tau)
    floor = (MIN_STDEV_FRACTION * SPREAD_STDEV) ** 2
    return math.sqrt(max(SPREAD_STDEV**2 + signed, floor))


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
                    # how much of this cell is judgement rather than the line
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
