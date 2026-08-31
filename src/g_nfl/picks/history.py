"""Load the whole pick record, graded, for a range of seasons (#58).

Every guardrail fit and every backtest starts here, so the joins live in one
place. Two sources, deliberately:

- `pool_picks` — the workbooks. 2020-2023 are Team Reichert's own members,
  2025 is all sixteen Cville entries. 2024 is one week and is skipped by
  default.
- `picks` — what the app captured live, 2025 only, which is where the
  individual family members are for that season.

Lines resolve pool first, market close second, matching how the pool grades.
"""

from __future__ import annotations

from typing import Any

from g_nfl.picks.analytics import graded_rows
from g_nfl.picks.grading import resolve_lines
from g_nfl.utils.database import (
    GameResultsDatabase,
    MarketLinesDatabase,
    PicksDatabase,
    PoolPicksDatabase,
    PoolSpreadsDatabase,
)
from g_nfl.utils.web_app import normalize_game_id

#: 2024's workbook holds a single week, too thin to fit or score on.
DEFAULT_SEASONS = (2020, 2021, 2022, 2023, 2025)

#: The submitted entry, which is scored against its own members rather than
#: counted as one of them.
TEAM_PICKERS = frozenset({"Reichert", "TEAM"})


def _by_game(rows: list[dict], value: str = "spread") -> dict[str, float]:
    return {
        normalize_game_id(r["game_id"]): float(r[value])
        for r in rows
        if r.get(value) is not None
    }


def load_season(season: int, source: str = "pool") -> list[dict[str, Any]]:
    """Graded rows for one season.

    `source` is 'pool' for the workbooks or 'app' for what the site captured.
    """
    picks = (
        PoolPicksDatabase().get_picks(season)
        if source == "pool"
        else PicksDatabase().get_season_picks(season)
    )
    for p in picks:
        p["game_id"] = normalize_game_id(p["game_id"])
        p.setdefault("season", season)

    pool = _by_game(PoolSpreadsDatabase().get_pool_spreads(season))
    market = _by_game(MarketLinesDatabase().get_market_lines(season))
    results = {
        normalize_game_id(r["game_id"]): r["result"]
        for r in GameResultsDatabase().get_results(season)
        if r.get("result") is not None
    }

    return graded_rows(
        picks,
        results,
        resolve_lines(
            [{"game_id": g, "spread": s} for g, s in pool.items()],
            [{"game_id": g, "spread": s} for g, s in market.items()],
        ),
        pool_lines=pool,
        market_lines=market,
    )


def load_history(
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
    source: str = "pool",
    drop_team: bool = True,
) -> list[dict[str, Any]]:
    """Graded rows across seasons.

    `drop_team` removes the submitted entry, so a rule is fitted on what the
    members picked. The entry is what the backtest scores, and fitting on it
    would be scoring a rule against its own training data.
    """
    rows = [r for s in seasons for r in load_season(s, source)]
    if drop_team:
        rows = [r for r in rows if r["picker"] not in TEAM_PICKERS]
    return rows
