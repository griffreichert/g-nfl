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
from functools import lru_cache
from typing import Any

from g_nfl.picks.boards import board_path
from g_nfl.picks.survivor import Board, win_probability

LAST_REG_WEEK = 18


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
) -> tuple[Board, list[str], list[int]]:
    """Board, selectable teams and remaining weeks, from `from_week` on.

    `market_spreads` maps game_id to the home spread and wins over the
    artifact's model spread — the book is sharper than the ratings for
    any week it has actually priced. `spent` teams are dropped entirely;
    they can never be picked again.
    """
    artifact = load_artifact(season)
    spent_set = set(spent or ())
    market = market_spreads or {}

    weeks = [w for w in range(from_week, LAST_REG_WEEK + 1)]
    teams = sorted(t for t in artifact["ratings"] if t not in spent_set)
    board = Board(teams, weeks)

    for game in artifact["games"]:
        week = game["week"]
        if week < from_week:
            continue
        spread = market.get(game["game_id"], game["model_spread"])
        priced = game["game_id"] in market
        for team, margin, opponent, home in (
            (game["home"], spread, game["away"], True),
            (game["away"], -spread, game["home"], False),
        ):
            if team in spent_set:
                continue
            board.add(
                team,
                week,
                win_probability(margin),
                {
                    "game_id": game["game_id"],
                    "opponent": opponent,
                    "home": home,
                    "spread": round(margin, 2),
                    "source": "market" if priced else "model",
                },
            )

    return board, teams, weeks


def cells(board: Board) -> list[dict[str, Any]]:
    """Every (team, week) on the board, flat, for the season matrix."""
    return [
        {"team": team, "week": week, "win_prob": prob, **board.game[(team, week)]}
        for (team, week), prob in sorted(board.prob.items())
    ]
