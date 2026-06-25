"""FastAPI backend for g-nfl picks app

Wraps the existing Supabase-backed database layer (g_nfl.utils.database)
as a REST API for the React frontend. No auth yet — `picker` is passed
explicitly and will be replaced by session identity when auth is added.
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from g_nfl import CUR_SEASON, CUR_WEEK
from g_nfl.picks.grading import BREAK_EVEN, picker_standings
from g_nfl.utils.config import PICKERS, SURVIVOR_USED_TEAMS
from g_nfl.utils.database import (
    GameResultsDatabase,
    MarketLinesDatabase,
    PicksDatabase,
    PoolSpreadsDatabase,
)
from g_nfl.utils.web_app import get_pool_spreads, normalize_game_id

from .schemas import (
    AppConfig,
    GameLine,
    PickRecord,
    PoolSpreadUpdate,
    PoolSpreadUpdateResponse,
    SavePicksRequest,
    SavePicksResponse,
    StandingsResponse,
    WeeksResponse,
)

app = FastAPI(title="g-nfl API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config", response_model=AppConfig)
def get_config():
    return AppConfig(
        pickers=PICKERS,
        cur_season=CUR_SEASON,
        cur_week=CUR_WEEK,
        survivor_used_teams=SURVIVOR_USED_TEAMS,
    )


@app.get("/api/weeks", response_model=WeeksResponse)
def get_weeks(season: int):
    db = MarketLinesDatabase()
    weeks = db.get_available_weeks(season)
    return WeeksResponse(weeks=weeks, max_week=max(weeks) if weeks else None)


@app.get("/api/lines", response_model=list[GameLine])
def get_lines(season: int, week: int):
    """Combined market lines + pool spreads for a week.

    The last game in market-lines order is the MNF game (matches the
    Streamlit app's convention).
    """
    market_db = MarketLinesDatabase()
    market_lines = market_db.get_market_lines(season, week)
    if not market_lines:
        raise HTTPException(404, f"No market data for season {season} week {week}")

    pool_spreads = {
        normalize_game_id(gid): spread
        for gid, spread in get_pool_spreads(season, week).items()
    }

    games = []
    for i, line in enumerate(market_lines):
        game_id = normalize_game_id(line["game_id"])
        parts = game_id.split("_")
        if len(parts) < 4:
            continue
        games.append(
            GameLine(
                game_id=game_id,
                away_team=parts[2],
                home_team=parts[3],
                pool_spread=pool_spreads.get(game_id),
                market_spread=line.get("spread"),
                market_total=line.get("total"),
                is_mnf=i == len(market_lines) - 1,
            )
        )
    return games


@app.get("/api/picks", response_model=list[PickRecord])
def get_picks(season: int, week: int, picker: str | None = None):
    db = PicksDatabase()
    picks = db.get_picks(season, week, picker)
    return [
        PickRecord(
            game_id=p["game_id"],
            team_picked=p["team_picked"],
            pick_type=p.get("pick_type", "regular"),
            spread=p.get("spread"),
            picker=p["picker"],
            season=p["season"],
            week=p["week"],
        )
        for p in picks
    ]


@app.post("/api/picks", response_model=SavePicksResponse)
def save_picks(req: SavePicksRequest):
    if req.picker not in PICKERS:
        raise HTTPException(400, f"Unknown picker: {req.picker}")

    best_bets = sum(1 for p in req.picks if p.pick_type == "best_bet")
    if best_bets > 1:
        raise HTTPException(400, "Only one best bet allowed per week")
    regular = sum(1 for p in req.picks if p.pick_type in ("regular", "best_bet"))
    if regular > 6:
        raise HTTPException(400, "Maximum 6 regular/best bet picks")
    for pick_type in ("survivor", "underdog", "mnf"):
        if sum(1 for p in req.picks if p.pick_type == pick_type) > 1:
            raise HTTPException(400, f"Only one {pick_type} pick allowed per week")

    # PicksDatabase.save_picks expects a dict keyed by game_id, with special
    # picks (survivor/underdog/mnf) prefixed so they can coexist with a
    # regular pick on the same game.
    picks_dict = {}
    for p in req.picks:
        key = (
            f"{p.pick_type}_{p.game_id}"
            if p.pick_type in ("survivor", "underdog", "mnf")
            else p.game_id
        )
        picks_dict[key] = {
            "team_picked": p.team_picked,
            "pick_type": p.pick_type,
            "spread": p.spread,
        }

    db = PicksDatabase()
    try:
        saved = db.save_picks(req.season, req.week, picks_dict, req.picker)
    except Exception as e:
        raise HTTPException(500, f"Failed to save picks: {e}") from e
    return SavePicksResponse(saved=saved)


@app.get("/api/standings", response_model=StandingsResponse)
def get_standings(season: int):
    """Picker performance for a season: ATS records, units at -110,
    per-pick-type breakdowns, and weekly cumulative trend.

    Grades picks against the game_results table (populated locally by
    scripts/update_results.py); games without a result are pending.
    """
    picks = PicksDatabase().get_season_picks(season)
    if not picks:
        raise HTTPException(404, f"No picks for season {season}")
    for p in picks:
        p["game_id"] = normalize_game_id(p["game_id"])

    result_rows = GameResultsDatabase().get_results(season)
    results = {
        normalize_game_id(r["game_id"]): r["result"]
        for r in result_rows
        if r["result"] is not None
    }
    graded_weeks = [r["week"] for r in result_rows if r["result"] is not None]
    return StandingsResponse(
        season=season,
        break_even_pct=BREAK_EVEN,
        graded_through_week=max(graded_weeks) if graded_weeks else None,
        standings=picker_standings(picks, results),
    )


@app.put("/api/pool-spreads", response_model=PoolSpreadUpdateResponse)
def update_pool_spread(req: PoolSpreadUpdate):
    db = PoolSpreadsDatabase()
    success = db.update_pool_spread(
        req.season, req.week, normalize_game_id(req.game_id), req.spread
    )
    if not success:
        raise HTTPException(500, "Failed to update pool spread")
    return PoolSpreadUpdateResponse(success=True)
