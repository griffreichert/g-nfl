"""ESPN season-total fantasy projections (issue #87).

Schema pinned in the issue's contract comment (shared with #88's ``score()``):
``gsis_id, espn_id, player_name, position, team, pass_yd, pass_td, ints,
rush_yd, rush_td, rec, rec_yd, rec_td, fum``.
"""

from __future__ import annotations

import json

import nflreadpy
import polars as pl
import requests

from g_nfl.utils.teams import standardize_teams

_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3"

# defaultPositionId -> position, confirmed against a live 2026 response.
# (Not espn-api's POSITION_MAP: that keys off eligibleSlots, a different id space.)
_POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE"}

# ESPN proTeamId -> team code; standardize_teams() maps ESPN's codes (WSH, LAR, ...)
# onto this repo's nflverse-style abbreviations.
_PRO_TEAMS = {
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",
    14: "LAR",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WSH",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}

# ESPN numeric stat id (as string) for each output column, season-total block.
# Confirmed against live 2026 data for a QB/RB/WR/TE sample, not guessed from
# espn-api's PLAYER_STATS_MAP alone: that map lists both "41" and "53" as
# receptions with an unresolved TODO, and the real payload only populates "53".
_STAT_IDS = {
    "pass_yd": "3",
    "pass_td": "4",
    "ints": "20",
    "rush_yd": "24",
    "rush_td": "25",
    "rec": "53",
    "rec_yd": "42",
    "rec_td": "43",
    "fum": "72",
}

_OUTPUT_COLUMNS = [
    "gsis_id",
    "espn_id",
    "player_name",
    "position",
    "team",
    "pass_yd",
    "pass_td",
    "ints",
    "rush_yd",
    "rush_td",
    "rec",
    "rec_yd",
    "rec_td",
    "fum",
]


def fetch_raw_projections(season: int, limit: int = 1500) -> dict:
    """Fetch ESPN's kona_player_info blob for ``season``. Network call, no parsing."""
    headers = {
        "User-Agent": "Mozilla/5.0",
        "x-fantasy-filter": json.dumps(
            {
                "players": {
                    "limit": limit,
                    "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
                }
            }
        ),
    }
    resp = requests.get(
        _URL.format(season=season),
        params={"view": "kona_player_info"},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def parse_projections(raw: dict, season: int) -> pl.DataFrame:
    """Parse a ``fetch_raw_projections`` payload into per-player stat lines.

    Pure and network-free, so it's testable against a saved fixture. Drops
    players outside QB/RB/WR/TE or without a season-total projection block.
    """
    rows = []
    for entry in raw["players"]:
        player = entry["player"]
        position = _POSITIONS.get(player["defaultPositionId"])
        team = _PRO_TEAMS.get(player["proTeamId"])
        if position is None or team is None:
            continue
        stats = next(
            (
                block["stats"]
                for block in player["stats"]
                if block.get("seasonId") == season
                and block.get("statSourceId") == 1
                and block.get("statSplitTypeId") == 0
            ),
            None,
        )
        if stats is None:
            continue
        rows.append(
            {
                "espn_id": player["id"],
                "player_name": player["fullName"],
                "position": position,
                "team": standardize_teams(team),
                **{col: stats.get(sid, 0.0) for col, sid in _STAT_IDS.items()},
            }
        )
    return pl.DataFrame(rows)


def fetch_espn_projections(season: int) -> pl.DataFrame:
    """Season-total ESPN projections joined to nflverse ``gsis_id``.

    Raises if the ``gsis_id`` match rate drops below 95%: a silent drop here
    becomes missing players on the board, the failure mode that matters.
    """
    stat_lines = parse_projections(fetch_raw_projections(season), season)

    ids = (
        nflreadpy.load_ff_playerids()
        .select("espn_id", "gsis_id")
        .drop_nulls("espn_id")
        .unique("espn_id")
    )
    joined = stat_lines.join(ids, on="espn_id", how="left")

    match_rate = joined["gsis_id"].is_not_null().mean()
    if match_rate < 0.95:
        unmatched = joined["gsis_id"].null_count()
        raise RuntimeError(
            f"gsis_id match rate {match_rate:.1%} below 95% threshold "
            f"({unmatched}/{joined.height} unmatched)"
        )

    return joined.select(_OUTPUT_COLUMNS)
