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


class PoolSpreadUpdate(BaseModel):
    season: int
    week: int
    game_id: str
    spread: float


class PoolSpreadUpdateResponse(BaseModel):
    success: bool
