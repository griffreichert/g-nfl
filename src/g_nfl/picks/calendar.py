"""Which season and week the app is on, read from the database (#61).

Deriving them from nflverse is not an option here: the deployed API has no
nflreadpy (see `GameResultsDatabase`), so this reads what is already in
Supabase. `market_lines` says which weeks exist, `game_results` says which have
been played.

Results are held for `TTL_SECONDS` (#141). Five endpoints call these, and
`/api/config` calls them three times over, which cost nine Supabase round trips
per page load.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from g_nfl.utils.config import CUR_SEASON, CUR_WEEK
from g_nfl.utils.database import GameResultsDatabase, MarketLinesDatabase

TTL_SECONDS = 60.0


@dataclass(frozen=True)
class SeasonWeeks:
    """The weeks a season holds lines for, and the first still to be played."""

    weeks: list[int]
    current: int | None


_cache: dict[Any, tuple[float, Any]] = {}


def clear_cache() -> None:
    _cache.clear()


def _cached(key: Any, build: Callable[[], Any]) -> Any:
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[0] < TTL_SECONDS:
        return hit[1]
    value = build()
    _cache[key] = (now, value)
    return value


def current_season(default: int = CUR_SEASON) -> int:
    """The latest season we hold lines for."""
    season = _cached("season", lambda: MarketLinesDatabase().latest_season())
    return season if season else default


def season_weeks(season: int) -> SeasonWeeks:
    """Every week of `season` with lines, and the first one still to be played.

    A week rolls over as soon as its last game is graded. A season with every
    game played stays on its final week rather than running off the end.
    """
    return _cached(("weeks", season), lambda: _build(season))


def _build(season: int) -> SeasonWeeks:
    counts = MarketLinesDatabase().games_per_week(season)
    if not counts:
        return SeasonWeeks([], None)
    played = GameResultsDatabase().graded_per_week(season)
    weeks = sorted(counts)
    for week in weeks:
        if played.get(week, 0) < counts[week]:
            return SeasonWeeks(weeks, week)
    return SeasonWeeks(weeks, max(weeks))


def current_week(season: int, default: int = CUR_WEEK) -> int:
    """The first week of `season` with a game still to be played."""
    return season_weeks(season).current or default
