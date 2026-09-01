"""Pydantic schemas for the g-nfl API"""

from typing import Literal

from pydantic import BaseModel

PickType = Literal["regular", "best_bet", "survivor", "underdog", "mnf"]


class AppConfig(BaseModel):
    pickers: list[str]
    cur_season: int
    cur_week: int
    survivor_used_teams: list[str]


class WeeksResponse(BaseModel):
    weeks: list[int]
    max_week: int | None


class GameLine(BaseModel):
    game_id: str
    away_team: str
    home_team: str
    pool_spread: float | None
    market_spread: float | None
    market_total: float | None
    is_mnf: bool


class Pick(BaseModel):
    game_id: str
    team_picked: str
    pick_type: PickType
    spread: float | None = None
    # why this pick was made, captured at pick time (#70)
    note: str | None = None


class PickRecord(Pick):
    picker: str
    season: int
    week: int


class SavePicksRequest(BaseModel):
    # picker is an explicit field for now; replaced by session identity once auth lands
    season: int
    week: int
    picker: str
    picks: list[Pick]


class SavePicksResponse(BaseModel):
    saved: int


class Record(BaseModel):
    wins: int
    losses: int
    pushes: int
    pending: int
    win_pct: float | None


class WeeklyRecord(Record):
    week: int
    units: float
    cum_units: float
    cum_win_pct: float | None


class PickerStanding(BaseModel):
    picker: str
    ats: Record
    units: float
    by_type: dict[str, Record]
    no_spread: int
    weekly: list[WeeklyRecord]


class StandingsResponse(BaseModel):
    season: int
    break_even_pct: float
    graded_through_week: int | None
    standings: list[PickerStanding]


class PoolSpreadUpdate(BaseModel):
    season: int
    week: int
    game_id: str
    spread: float


class PoolSpreadUpdateResponse(BaseModel):
    success: bool


class CutRow(BaseModel):
    """One slice of the pick record. `pct` is per game; `pick_pct` is the
    naive per-pick rate, carried so the inflation stays visible."""

    key: str
    picks: int
    games: float
    pick_pct: float | None
    pct: float | None
    shrunk_pct: float | None
    units: float
    z: float | None


class Cut(BaseModel):
    name: str
    label: str
    note: str
    rows: list[CutRow]


class TeamAppetite(BaseModel):
    team: str
    available: int
    picked_games: int
    picks: int
    appetite: float | None
    votes_per_pick: float | None
    pct: float | None
    units: float


class AnalyticsResponse(BaseModel):
    season: int
    picks: int
    games: int
    votes_per_game: float
    base_pct: float
    break_even_pct: float
    cuts: list[Cut]
    teams: list[TeamAppetite]


class InjuryReport(BaseModel):
    team: str
    name: str
    position: str | None
    status: str | None
    practice: str | None


class TeamWeekStat(BaseModel):
    week: int
    team: str
    plays: int | None
    off_epa_play: float | None
    def_epa_play: float | None
    off_success_rate: float | None
    def_success_rate: float | None
    off_explosive_rate: float | None
    def_explosive_rate: float | None
    off_pass_epa: float | None
    off_rush_epa: float | None


class GamePick(BaseModel):
    """A pick the room made on this game, with whatever reasoning was
    written down at the time."""

    picker: str
    team_picked: str
    pick_type: PickType
    note: str | None = None
    outcome: str | None = None


class GameDetail(BaseModel):
    game_id: str
    season: int
    week: int
    away_team: str
    home_team: str
    # context is null until scripts/update_game_context.py has run for the week
    gameday: str | None = None
    gametime: str | None = None
    roof: str | None = None
    surface: str | None = None
    temp: int | None = None
    wind: int | None = None
    stadium: str | None = None
    div_game: bool | None = None
    away_rest: int | None = None
    home_rest: int | None = None
    away_qb: str | None = None
    home_qb: str | None = None
    away_coach: str | None = None
    home_coach: str | None = None
    referee: str | None = None
    injuries: list[InjuryReport] = []
    pool_spread: float | None = None
    market_spread: float | None = None
    market_total: float | None = None
    away_score: int | None = None
    home_score: int | None = None
    result: float | None = None
    graded_line: float | None = None
    # which table graded_line came from. Returned rather than inferred from
    # pool_spread being null, so the client cannot drift from resolve_lines().
    graded_line_source: Literal["pool", "market"] | None = None
    team_weeks: list[TeamWeekStat] = []
    picks: list[GamePick] = []


class Guardrail(BaseModel):
    """One fitted veto rule, as the board renders it (#58)."""

    id: str
    label: str
    blurb: str
    #: shrunk hit rate for sides this rule matches
    pct: float
    #: the field's own rate over the same sample, for comparison
    base_pct: float
    games: float
    picks: int
    units: float
    bad_seasons: int
    seasons: int
    #: reads data unavailable at pick time, so it advises and never vetoes
    advisory: bool
    reason: str


class SideFlag(BaseModel):
    """A side of a game that trips at least one guardrail."""

    game_id: str
    team: str
    rule_ids: list[str]


class GuardrailsResponse(BaseModel):
    season: int
    week: int | None
    #: rules that cleared the bar, in the order the board shows them
    rules: list[Guardrail]
    #: rules that were fitted and rejected, kept so the room can see why
    rejected: list[Guardrail]
    flags: list[SideFlag]
    fitted_on: list[int]


class LoginRequest(BaseModel):
    picker: str
    pin: str


class LoginResponse(BaseModel):
    #: empty on /api/auth/me, which only confirms an existing token
    token: str
    picker: str


class LedgerWeek(BaseModel):
    week: int
    entry: str
    points: float
    available: float
    running: float
    #: which member "Best member" was following that week, else None
    leader: str | None = None


class LedgerEntry(BaseModel):
    entry: str
    points: float
    available: float
    weeks: int
    share: float | None


class LedgerResponse(BaseModel):
    season: int
    weeks: list[LedgerWeek]
    standings: list[LedgerEntry]
