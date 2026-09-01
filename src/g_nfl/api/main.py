"""FastAPI backend for g-nfl picks app

Wraps the existing Supabase-backed database layer (g_nfl.utils.database)
as a REST API for the React frontend. No auth yet — `picker` is passed
explicitly and will be replaced by session identity when auth is added.
"""

import os
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from g_nfl.picks import ledger
from g_nfl.picks.analytics import graded_rows, summarize, team_appetite
from g_nfl.picks.calendar import current_season, current_week
from g_nfl.picks.grading import (
    BREAK_EVEN,
    grade_pick,
    picker_standings,
    resolve_lines,
)
from g_nfl.picks.guardrails import RuleFit
from g_nfl.picks.guardrails import fit as fit_guardrails
from g_nfl.picks.history import DEFAULT_SEASONS, load_history
from g_nfl.picks.sides import candidate_side
from g_nfl.utils.config import (
    PICKERS,
    TEAM_PICKER,
    TEST_PICKER,
)
from g_nfl.utils.database import (
    GameContextDatabase,
    GameResultsDatabase,
    MarketLinesDatabase,
    PicksDatabase,
    PoolSpreadsDatabase,
    TeamWeekStatsDatabase,
)
from g_nfl.utils.web_app import get_pool_spreads, normalize_game_id

from .auth import authenticate, require_picker
from .schemas import (
    AnalyticsResponse,
    AppConfig,
    GameDetail,
    GameLine,
    Guardrail,
    GuardrailsResponse,
    LedgerEntry,
    LedgerResponse,
    LedgerWeek,
    LoginRequest,
    LoginResponse,
    PickRecord,
    PoolSpreadUpdate,
    PoolSpreadUpdateResponse,
    SavePicksRequest,
    SavePicksResponse,
    SideFlag,
    StandingsResponse,
    WeeksResponse,
)

# bound once: FastAPI takes dependencies from argument defaults (ruff B008)
_PICKER = Depends(require_picker)

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
def get_config(picker: str | None = None):
    """Season, week and the survivor teams already spent.

    All three are derived. `CUR_SEASON` and `CUR_WEEK` were constants somebody
    had to remember to bump and nobody did: nine days before the 2026 opener
    they still read 2025 week 12. `SURVIVOR_USED_TEAMS` was one global list for
    the whole room, which is wrong on the pool's own rules, since the ban on
    reusing a team is per entry.
    """
    season = current_season()
    return AppConfig(
        pickers=PICKERS,
        cur_season=season,
        cur_week=current_week(season),
        survivor_used_teams=survivor_used(season, picker) if picker else [],
    )


def survivor_used(season: int, picker: str) -> list[str]:
    """Teams this picker has already spent in survivor this season."""
    return sorted(
        {
            p["team_picked"]
            for p in PicksDatabase().get_season_picks(season)
            if p["picker"] == picker and p.get("pick_type") == "survivor"
        }
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


@lru_cache(maxsize=1)
def _fitted_guardrails() -> tuple[RuleFit, ...]:
    """The rule fit, computed once per process.

    Reads five seasons of pool picks and their lines out of Supabase, which is
    far too slow to do per request and changes only when a season grades out.
    A deploy clears it, and that is often enough.
    """
    return tuple(fit_guardrails(load_history()))


def _guardrail(f) -> Guardrail:
    return Guardrail(
        id=f.rule.id,
        label=f.rule.label,
        blurb=f.rule.blurb,
        pct=f.shrunk_pct,
        base_pct=f.base,
        games=round(f.games, 1),
        picks=f.picks,
        units=f.units,
        bad_seasons=f.bad_seasons,
        seasons=len(f.by_season),
        advisory=f.rule.advisory,
        reason=f.reason,
    )


@app.get("/api/guardrails", response_model=GuardrailsResponse)
def get_guardrails(season: int | None = None, week: int | None = None):
    """The fitted vetoes, and which sides of this week's games trip them.

    Rules are fitted from the pick record on every call path through
    `_fitted_guardrails`, which caches: the fit reads six seasons out of
    Supabase and only changes when a season grades out.
    """
    season = season or current_season()
    fits = _fitted_guardrails()
    rules = [f for f in fits if f.qualifies]

    flags: list[SideFlag] = []
    if week is not None:
        for game in get_lines(season, week):
            for team in (game.away_team, game.home_team):
                side = candidate_side(game, team)
                tripped = [f.rule.id for f in rules if f.rule.matches(side)]
                if tripped:
                    flags.append(
                        SideFlag(game_id=game.game_id, team=team, rule_ids=tripped)
                    )

    return GuardrailsResponse(
        season=season,
        week=week,
        rules=[_guardrail(f) for f in rules],
        rejected=[_guardrail(f) for f in fits if not f.qualifies],
        flags=flags,
        fitted_on=list(DEFAULT_SEASONS),
    )


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
            # stored since #70 and never returned, so a saved reason vanished on
            # reload and the board asked for it again (#58)
            note=p.get("note"),
            picker=p["picker"],
            season=p["season"],
            week=p["week"],
        )
        for p in picks
    ]


@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Swap a PIN for a token. The token is the only thing that names a picker."""
    if req.picker not in PICKERS:
        # same error as a wrong PIN, so this does not enumerate the room
        raise HTTPException(401, "Wrong picker or PIN")
    return LoginResponse(token=authenticate(req.picker, req.pin), picker=req.picker)


@app.get("/api/auth/me", response_model=LoginResponse)
def whoami(picker: str = _PICKER):
    """Whether a stored token is still good, and who it belongs to."""
    return LoginResponse(token="", picker=picker)


@app.post("/api/picks", response_model=SavePicksResponse)
def save_picks(req: SavePicksRequest, picker: str = _PICKER):
    """Save a picker's week.

    `picker` comes from the signed token and the one in the body is ignored.
    Until #60 this endpoint trusted the body, so anyone could submit as anyone,
    which made the ledger worthless as a record of who said what.

    TEAM is the one exception. It is the entry the room submits together off
    the board, so any signed-in picker may write it, and nobody may write it
    while signed out.
    """
    if req.picker == TEAM_PICKER:
        picker = TEAM_PICKER

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
            "note": p.note,
        }

    db = PicksDatabase()
    try:
        saved = db.save_picks(req.season, req.week, picks_dict, picker)
    except Exception as e:
        raise HTTPException(500, f"Failed to save picks: {e}") from e
    return SavePicksResponse(saved=saved)


@app.get("/api/ledger", response_model=LedgerResponse)
def get_ledger(season: int | None = None):
    """TEAM against the entries it could have submitted instead.

    Two independent sources say the weekly call costs about 1.5 points of hit
    rate against its own members (notes/pick-behaviour.md). This is that
    comparison run live, in pool points, so a losing process shows up in week 8
    rather than in April.
    """
    season = season or current_season()
    picks = PicksDatabase().get_season_picks(season)
    picks = [p for p in picks if p["picker"] != TEST_PICKER]
    for p in picks:
        p["game_id"] = normalize_game_id(p["game_id"])

    def _normalized(rows: list[dict]) -> list[dict]:
        return [{**r, "game_id": normalize_game_id(r["game_id"])} for r in rows]

    lines = resolve_lines(
        _normalized(PoolSpreadsDatabase().get_pool_spreads(season)),
        _normalized(MarketLinesDatabase().get_market_lines(season)),
    )
    results = {
        normalize_game_id(r["game_id"]): r["result"]
        for r in GameResultsDatabase().get_results(season)
        if r.get("result") is not None
    }

    weeks = ledger.weekly(picks, results, lines)
    return LedgerResponse(
        season=season,
        weeks=[LedgerWeek(**w) for w in weeks],
        standings=[LedgerEntry(**e) for e in ledger.standings(weeks)],
    )


@app.get("/api/standings", response_model=StandingsResponse)
def get_standings(season: int):
    """Picker performance for a season: ATS records, units at -110,
    per-pick-type breakdowns, and weekly cumulative trend.

    Grades picks against the game_results table (populated locally by
    scripts/update_results.py); games without a result are pending.

    The line each pick grades against is resolved here from the lines
    tables — pool where we have one, market otherwise — not read off the
    pick row. People pick before the Friday pool line is posted, so the
    row cannot carry the line it will be graded on.
    """
    picks = [
        p
        for p in PicksDatabase().get_season_picks(season)
        if p["picker"] != TEST_PICKER
    ]
    # An empty season is the normal state of week 1, not an error. Returning
    # 404 here put "Failed to load" on the Standings page on opening day.
    if not picks:
        return StandingsResponse(
            season=season,
            break_even_pct=BREAK_EVEN,
            graded_through_week=None,
            standings=[],
        )
    for p in picks:
        p["game_id"] = normalize_game_id(p["game_id"])

    # game_ids are normalized on both sides or the join silently misses
    def _normalized(rows: list[dict]) -> list[dict]:
        return [{**r, "game_id": normalize_game_id(r["game_id"])} for r in rows]

    lines = resolve_lines(
        _normalized(PoolSpreadsDatabase().get_pool_spreads(season)),
        _normalized(MarketLinesDatabase().get_market_lines(season)),
    )

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
        standings=picker_standings(picks, results, lines),
    )


@app.put("/api/pool-spreads", response_model=PoolSpreadUpdateResponse)
def update_pool_spread(req: PoolSpreadUpdate, picker: str = _PICKER):
    """Enter a pool line. Signed in only: every ATS pick grades against these."""
    db = PoolSpreadsDatabase()
    success = db.update_pool_spread(
        req.season, req.week, normalize_game_id(req.game_id), req.spread
    )
    if not success:
        raise HTTPException(500, "Failed to update pool spread")
    return PoolSpreadUpdateResponse(success=True)


# Each cut carries the reason it is on the page. Three of these used to be
# terms in the board's rating and are kept here precisely because they turned
# out to be worth nothing — a reader should be able to see that for themselves.
_CUTS = [
    (
        "band",
        "Line size",
        "The only cut with signal left after clustering. Everything is under break-even; "
        "close lines are the least bad, not good.",
    ),
    (
        "band_venue",
        "Line size and venue",
        "The sharpest cell in the record: a home side laying or getting 3-7. The league "
        "covered 44.6% there, so this is our side selection.",
    ),
    ("venue", "Home or road", "Collapses onto the base rate once shrunk. No signal."),
    ("slot", "Slot", "Best bets look worse than regulars, but not beyond noise."),
    (
        "contested",
        "Split or unanimous",
        "The board was built on the idea that agreement is a negative. Per game and shrunk, "
        "it is worth nothing either way.",
    ),
    ("picker", "Picker", "Nobody in the room clears break-even over one season."),
]


def _cut_key(name: str):
    def band(r):
        if r["line"] is None:
            return None
        a = abs(r["line"])
        return "0-3" if a <= 3 else "3-7" if a <= 7 else "7+"

    venue = lambda r: "home" if r["picked_home"] else "road"  # noqa: E731
    return {
        "band": band,
        "venue": venue,
        "slot": lambda r: r["slot"],
        "picker": lambda r: r["picker"],
        "contested": lambda r: "split" if r["contested"] else "unanimous",
        "band_venue": lambda r: None if band(r) is None else f"{band(r)} {venue(r)}",
    }[name]


@app.get("/api/analytics", response_model=AnalyticsResponse)
def get_analytics(season: int):
    """Cuts of our own pick record, computed per game rather than per pick.

    The room puts about three votes on every game, so a per-pick rate
    counts one game three times. Everything here collapses votes to games
    first and then shrinks each cell toward the field's own rate by
    sample size. See g_nfl.picks.analytics and notes/pick-analytics.md.
    """
    picks = [
        {**p, "game_id": normalize_game_id(p["game_id"])}
        for p in PicksDatabase().get_season_picks(season)
        # TEAM is the room's own average; counting it double-counts everyone
        if p["picker"] not in (TEST_PICKER, "TEAM")
    ]
    # Same as Standings: nothing picked yet is a state, not a failure.
    if not picks:
        return AnalyticsResponse(
            season=season,
            picks=0,
            games=0,
            votes_per_game=0.0,
            base_pct=BREAK_EVEN,
            break_even_pct=BREAK_EVEN,
            cuts=[],
            teams=[],
        )

    def _normalized(rows: list[dict]) -> list[dict]:
        return [{**r, "game_id": normalize_game_id(r["game_id"])} for r in rows]

    lines = resolve_lines(
        _normalized(PoolSpreadsDatabase().get_pool_spreads(season)),
        _normalized(MarketLinesDatabase().get_market_lines(season)),
    )
    result_rows = GameResultsDatabase().get_results(season)
    results = {
        normalize_game_id(r["game_id"]): r["result"]
        for r in result_rows
        if r["result"] is not None
    }

    rows = graded_rows(picks, results, lines)
    if not rows:
        raise HTTPException(404, f"No graded picks for season {season}")

    sides: dict[str, set] = {}
    for r in rows:
        sides.setdefault(r["game_id"], set()).add(r["team"])
    for r in rows:
        r["contested"] = len(sides[r["game_id"]]) > 1

    games = len({r["game_id"] for r in rows})
    base = summarize(rows, lambda r: "all")[0]["pct"]
    # Appetite is a share of the chances we *had*. Results run through the
    # playoffs while the pool stops at week 17, so counting every graded game
    # hands the January teams a bigger denominator than the room could ever
    # have picked into and understates appetite exactly where it matters.
    picked_weeks = {r["week"] for r in rows}
    schedule = [
        (normalize_game_id(r["game_id"]), r["away_team"], r["home_team"])
        for r in result_rows
        if r["result"] is not None
        and int(normalize_game_id(r["game_id"]).split("_")[1]) in picked_weeks
    ]

    return AnalyticsResponse(
        season=season,
        picks=len(rows),
        games=games,
        votes_per_game=round(len(rows) / games, 2),
        base_pct=base,
        break_even_pct=BREAK_EVEN,
        cuts=[
            {
                "name": name,
                "label": label,
                "note": note,
                "rows": [
                    {**c, "key": str(c["key"])}
                    for c in summarize(rows, _cut_key(name), base=base)
                ],
            }
            for name, label, note in _CUTS
        ],
        teams=team_appetite(rows, schedule, len({r["picker"] for r in rows})),
    )


@app.get("/api/games/{game_id}", response_model=GameDetail)
def get_game_detail(game_id: str):
    """Everything known about one game: line, result, weather, rest, QBs,
    injuries, both teams' season of EPA, and what the room picked and why.

    Context and EPA come from tables pushed by
    scripts/update_game_context.py — the deployed API cannot reach
    nflverse. A game whose week has not been pushed yet still returns,
    with the context fields null; the page is expected to cope.
    """
    gid = normalize_game_id(game_id)
    parts = gid.split("_")
    if len(parts) != 4:
        raise HTTPException(400, f"Malformed game_id: {game_id}")
    season, week, away, home = int(parts[0]), int(parts[1]), parts[2], parts[3]

    ctx = GameContextDatabase().get_context(gid) or {}

    def _normalized(rows: list[dict]) -> list[dict]:
        return [{**r, "game_id": normalize_game_id(r["game_id"])} for r in rows]

    pool_rows = _normalized(PoolSpreadsDatabase().get_pool_spreads(season))
    market_rows = _normalized(MarketLinesDatabase().get_market_lines(season))
    graded_line = resolve_lines(pool_rows, market_rows).get(gid)
    pool = next((r["spread"] for r in pool_rows if r["game_id"] == gid), None)
    market = next((r for r in market_rows if r["game_id"] == gid), {})
    # resolve_lines prefers pool; report which one it landed on rather than
    # leaving the client to reimplement that rule
    source = None if graded_line is None else ("pool" if pool is not None else "market")

    results = {
        normalize_game_id(r["game_id"]): r
        for r in GameResultsDatabase().get_results(season)
    }
    res = results.get(gid, {})
    margin = res.get("result")

    picks = [
        p
        for p in PicksDatabase().get_picks(season, week)
        if normalize_game_id(p["game_id"]) == gid and p["picker"] != TEST_PICKER
    ]

    stats = [
        s
        for s in TeamWeekStatsDatabase().get_team_stats(season, [away, home])
        if s["week"] <= week
    ]
    stats.sort(key=lambda s: (s["team"], s["week"]))

    return GameDetail(
        game_id=gid,
        season=season,
        week=week,
        away_team=away,
        home_team=home,
        injuries=ctx.pop("injuries", None) or [],
        pool_spread=pool,
        market_spread=market.get("spread"),
        market_total=market.get("total"),
        away_score=res.get("away_score"),
        home_score=res.get("home_score"),
        result=margin,
        graded_line=graded_line,
        graded_line_source=source,
        team_weeks=stats,
        picks=[
            {
                "picker": p["picker"],
                "team_picked": p["team_picked"],
                "pick_type": p.get("pick_type", "regular"),
                "note": p.get("note"),
                "outcome": grade_pick(p, margin, graded_line),
            }
            for p in picks
        ],
        **{
            k: ctx[k]
            for k in (
                "gameday",
                "gametime",
                "roof",
                "surface",
                "temp",
                "wind",
                "stadium",
                "div_game",
                "away_rest",
                "home_rest",
                "away_qb",
                "home_qb",
                "away_coach",
                "home_coach",
                "referee",
            )
            if k in ctx
        },
    )
