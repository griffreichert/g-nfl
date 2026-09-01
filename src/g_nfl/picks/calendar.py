"""Which season and week the app is on, read from the database (#61).

`CUR_SEASON` and `CUR_WEEK` in `utils/config.py` are constants somebody has to
remember to bump, and nobody did: on 2026-08-31, nine days before the 2026
opener, they still read 2025 and week 12.

Deriving them from nflverse is not an option here. The deployed API has no
nflreadpy (see `GameResultsDatabase`), so this reads what is already in
Supabase: `market_lines` says which weeks exist, `game_results` says which have
been played.
"""

from __future__ import annotations

from g_nfl.utils.config import CUR_SEASON, CUR_WEEK
from g_nfl.utils.database import GameResultsDatabase, MarketLinesDatabase


def current_season(default: int = CUR_SEASON) -> int:
    """The latest season we hold lines for."""
    seasons = MarketLinesDatabase().seasons()
    return max(seasons) if seasons else default


def current_week(season: int, default: int = CUR_WEEK) -> int:
    """The first week of `season` with a game still to be played.

    Week 1 of a season nobody has played is 1, and a week rolls over as soon as
    its last game is graded. A season with every game played stays on its final
    week rather than running off the end.
    """
    weeks = MarketLinesDatabase().get_available_weeks(season)
    if not weeks:
        return default

    played: dict[int, int] = {}
    for row in GameResultsDatabase().get_results(season):
        if row.get("result") is not None:
            played[row["week"]] = played.get(row["week"], 0) + 1

    counts = MarketLinesDatabase().games_per_week(season)
    for week in sorted(weeks):
        if played.get(week, 0) < counts.get(week, 0):
            return week
    return max(weeks)
