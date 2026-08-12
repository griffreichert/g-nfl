"""Pull pool spreads out of the older Google picks-pool workbooks.

The Cville standings workbook (`pool.parser`) only covers 2025. Earlier
seasons live in Google Sheets under Drive's `NFL` folder, in three
different layouts:

- **2021** (`Picks Pool '21`): a lines block whose `Pool Spread` cell
  names the team, e.g. ``LAR -2.5``.
- **2022** (`Picks Pool '22`): same block, but `Pool Spread` is a bare
  magnitude — the favourite has to come from the market `*Spread*`
  column, so rows priced ``PICK`` are unrecoverable and get dropped.
- **2023 / 2024** (`Picks Pool 2023`, despite the name): a tidy
  ``Visitor | Pool | Home`` block, signed positive when the home team is
  favoured.

Every layout is normalised to (favourite, magnitude) and only then joined
to the nflverse schedule, which is what decides home and away. The sheets
disagree about whether the first team named is home — 2021 writes
``X at Y`` and 2022 writes ``X vs. Y`` under a "First Team is home" note —
so their word order is never trusted.

Output: one row per game, `pool_spread` on the home perspective (positive
= home favoured), matching nflverse `spread_line`.
"""

from __future__ import annotations

import json
import re
import time
from functools import lru_cache

import polars as pl

from g_nfl.utils.connections import load_service_account
from g_nfl.utils.paths import PROJECT_DIR
from g_nfl.utils.teams import nfl_teams, standardize_teams

POOL_DIR = PROJECT_DIR / "data" / "pool"

# workbook key + layout, per season
WORKBOOKS = {
    2021: ("19P1OiGwPXx8VZXbpdjaSpmIH33NHjkAXgPuLLXkHQaM", "named_team"),
    2022: ("1sMOlK0JKbdgbLYbAP0uk3vM_PPhZFDcWvqqcpUHo5TU", "market_sign"),
    2023: ("1m5WeK_Fhs7tjQ0MphvRVoqcmvWXFfEOqb64kNEK8reI", "visitor_home"),
    2024: ("1m5WeK_Fhs7tjQ0MphvRVoqcmvWXFfEOqb64kNEK8reI", "visitor_home"),
}

WEEK_TAB_RE = re.compile(r"^(?:Wk|Week)\s+(\d+)$", re.I)
PLAYOFF_TABS = {
    "wild card": 19,
    "divisional": 20,
    "championship": 21,
    "conference": 21,
    "super bowl": 22,
    "superbowl": 22,
}
# the 2023 workbook carries one stray 2024 tab
SEASON_TABS = {2024: {"2024/2025 Week 1": 1}}

# workbooks with picks but no pool line of their own
PICKS_ONLY_WORKBOOKS = {
    2019: ("1kenJJya6v9om4Y7RDTYwBLogrwJgK7M_Zm7qjUNZbR8", "legacy"),
    2020: ("1F7Tg1yLJ8DokUsPUye3CLBMKjOf-6_hI6NSaB5ZF8To", "legacy"),
}

SPREAD_RE = re.compile(r"^([A-Z]{2,3})\s*([+-]?\d+(?:\.\d+)?)")

# every alias standardize_teams knows, but returning None instead of raising
TEAM_ALIASES = {
    "ARZ": "ARI",
    "AZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "JAG": "JAX",
    "JAC": "JAX",
    "LAR": "LA",
    "PHL": "PHI",
    "WSH": "WAS",
    "WFT": "WAS",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LA",
    "GNB": "GB",
    "KAN": "KC",
    "LVR": "LV",
    "NOR": "NO",
    "NWE": "NE",
    "SDG": "LAC",
    "SFO": "SF",
    "TAM": "TB",
}


@lru_cache(maxsize=1)
def _nick_map() -> dict[str, str]:
    """Team nickname (lower-case) -> abbreviation, plus retired names."""
    import nflreadpy as nfl

    teams = nfl.load_teams()
    nicks = {
        row["team_nick"].lower(): standardize_teams(row["team_abbr"])
        for row in teams.iter_rows(named=True)
    }
    nicks.update({"football team": "WAS", "redskins": "WAS", "raiders": "LV"})
    return nicks


def _teams_in(text: str) -> list[str]:
    """Abbreviations for every team named in a game string, in order.

    Matches on nickname so city ambiguity (New York, Los Angeles) and the
    workbooks' typos ("Cleveland Brown") do not matter.
    """
    low = text.lower()
    hits = [(low.find(nick), abbr) for nick, abbr in _nick_map().items() if nick in low]
    return [abbr for _, abbr in sorted(hits) if _ >= 0]


def _tab_week(title: str) -> int | None:
    if m := WEEK_TAB_RE.match(title.strip()):
        return int(m.group(1))
    return PLAYOFF_TABS.get(title.strip().lower())


def season_week(season: int, title: str) -> int | None:
    """The week a tab belongs to, or None if it belongs to another season.

    The 2023 workbook holds one stray `2024/2025 Week 1` tab, so a tab
    title alone does not identify the season.
    """
    if season in SEASON_TABS:
        return SEASON_TABS[season].get(title)
    strays = {t for tabs in SEASON_TABS.values() for t in tabs}
    return None if title in strays else _tab_week(title)


def _num(cell: str) -> float | None:
    try:
        return float(str(cell).strip())
    except ValueError:
        return None


def _abbr(text: str) -> str | None:
    """Team abbreviation, or None when the cell is a typo we cannot resolve.

    The workbooks are hand-typed: 2023 week 18 has ``MO`` where ``NO``
    belongs. Guessing would silently invent a game, so those rows are
    dropped and counted instead.
    """
    raw = text.strip().upper()
    if not raw:
        return None
    team = TEAM_ALIASES.get(raw, raw)
    return team if team in nfl_teams else None


def _header_index(row: list[str]) -> dict[str, int]:
    """Column name -> first index, tolerant of the sheets' `*Game *` styling."""
    lookup: dict[str, int] = {}
    for i, cell in enumerate(row):
        name = cell.strip().strip("*").strip().lower()
        if name and name not in lookup:
            lookup[name] = i
    return lookup


def _parse_lines_block(rows: list[list[str]]) -> list[dict]:
    """Extract (fav, dog, spread) from a 2021/2022 lines block."""
    header = next(
        (i for i, r in enumerate(rows) if any(c.strip() == "Pool Spread" for c in r)),
        None,
    )
    if header is None:
        return []
    cols = _header_index(rows[header])
    if not {"game", "spread", "pool spread"} <= cols.keys():
        return []
    pool_col, game_col, mkt_col = cols["pool spread"], cols["game"], cols["spread"]

    out = []
    for r in rows[header + 1 :]:
        if len(r) <= pool_col or not r[game_col].strip():
            break
        teams = _teams_in(r[game_col])
        if len(teams) != 2:
            continue
        pool = r[pool_col].strip()
        if not pool:
            continue

        # 2022 mixes both spellings: week 4 names the team ("CIN -3.5"),
        # week 5 gives a bare magnitude. Try the named form, then fall back.
        m = SPREAD_RE.match(pool.upper())
        named = _abbr(m.group(1)) if m else None
        if named is not None and named in teams:
            val = float(m.group(2))
            spread = abs(val)
        else:
            spread = _num(pool)
            m = (
                SPREAD_RE.match(r[mkt_col].strip().upper())
                if len(r) > mkt_col
                else None
            )
            named = _abbr(m.group(1)) if m else None
            # 'PICK' prices no favourite, so the pool side is unrecoverable
            if spread is None or named is None or named not in teams:
                continue
            val = float(m.group(2))

        fav = named if val < 0 else next(t for t in teams if t != named)
        dog = next(t for t in teams if t != fav)
        out.append({"fav": fav, "dog": dog, "spread": abs(spread)})
    return out


def _parse_visitor_home(rows: list[list[str]]) -> list[dict]:
    """Extract from a 2023/2024 `Visitor | Pool | Home` block."""
    header = next(
        (i for i, r in enumerate(rows) if "Visitor" in [c.strip() for c in r]), None
    )
    if header is None:
        return []
    cols = _header_index(rows[header])
    if not {"visitor", "home"} <= cols.keys():
        return []
    vis_col, home_col = cols["visitor"], cols["home"]
    pool_col = cols.get("pool", cols.get("spreads"))
    if pool_col is None:
        # 2023 week 5 leaves the column unlabelled, between the two teams
        if home_col - vis_col != 2:
            return []
        pool_col = vis_col + 1

    out = []
    for r in rows[header + 1 :]:
        if len(r) <= home_col:
            continue
        vis, home = _abbr(r[vis_col]), _abbr(r[home_col])
        pool = _num(r[pool_col])
        if vis is None or home is None or pool is None or vis == home:
            continue
        # positive = home favoured
        fav, dog = (home, vis) if pool > 0 else (vis, home)
        out.append({"fav": fav, "dog": dog, "spread": abs(pool)})
    return out


def pull_pool_lines(season: int, *, refresh: bool = False) -> pl.DataFrame:
    """Pool spreads for one season, home perspective, joined to the schedule.

    Columns: season, week, home_team, away_team, pool_spread. Cached to
    `data/pool/` because the Sheets read quota is 60/minute and a full
    workbook is ~25 tabs.
    """
    cache = POOL_DIR / f"pool_lines_{season}.parquet"
    if cache.exists() and not refresh:
        return pl.read_parquet(cache)

    _, layout = WORKBOOKS[season]
    grids = raw_grids(season if season != 2024 else 2023)

    records = []
    for title, rows in grids.items():
        week = season_week(season, title)
        if week is None:
            continue
        games = (
            _parse_visitor_home(rows)
            if layout == "visitor_home"
            else _parse_lines_block(rows)
        )
        records += [dict(g, week=week) for g in games]

    if not records:
        return pl.DataFrame(
            schema={
                "season": pl.Int64,
                "week": pl.Int64,
                "home_team": pl.String,
                "away_team": pl.String,
                "pool_spread": pl.Float64,
            }
        )

    lines = pl.DataFrame(records).with_columns(season=pl.lit(season, pl.Int64))
    out = _to_home_perspective(lines, season)
    POOL_DIR.mkdir(parents=True, exist_ok=True)
    out.write_parquet(cache)
    return out


def _to_home_perspective(lines: pl.DataFrame, season: int) -> pl.DataFrame:
    """Join to the schedule so it decides home/away, then sign the spread."""
    import nflreadpy as nfl

    sched = (
        nfl.load_schedules(seasons=[season])
        .select("season", "week", "home_team", "away_team")
        .with_columns(
            home_team=pl.col("home_team").map_elements(standardize_teams, pl.String),
            away_team=pl.col("away_team").map_elements(standardize_teams, pl.String),
        )
    )
    # a sheet row matches a game on {fav, dog} unordered
    pair = pl.concat_list("home_team", "away_team").list.sort()
    sched = sched.with_columns(pair=pair)
    lines = lines.with_columns(pair=pl.concat_list("fav", "dog").list.sort())

    joined = lines.join(sched, on=["season", "week", "pair"], how="inner")
    return (
        joined.with_columns(
            pool_spread=pl.when(pl.col("fav") == pl.col("home_team"))
            .then(pl.col("spread"))
            .otherwise(-pl.col("spread"))
        )
        .select("season", "week", "home_team", "away_team", "pool_spread")
        .unique(subset=["season", "week", "home_team"], keep="first")
        .sort("week", "home_team")
    )


def raw_grids(season: int, *, refresh: bool = False) -> dict[str, list[list[str]]]:
    """Every tab of a season's workbook, as a title -> grid mapping.

    Cached to `data/pool/raw/`. The Sheets API allows 60 reads a minute and
    a workbook is ~25 tabs, so the whole thing is fetched in one batched
    call and parsed from disk afterwards.
    """
    cache = POOL_DIR / "raw" / f"{season}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())

    key, _ = (WORKBOOKS | PICKS_ONLY_WORKBOOKS)[season]
    sheet = load_service_account().open_by_key(key)
    titles = [ws.title for ws in sheet.worksheets()]

    for attempt in range(6):
        try:
            batch = sheet.values_batch_get([f"'{t}'!A1:AZ80" for t in titles])
            break
        except Exception as exc:  # noqa: BLE001 - only 429 is worth retrying
            if "429" not in str(exc) or attempt == 5:
                raise
            time.sleep(20 * (attempt + 1))

    grids = {
        title: block.get("values", [])
        for title, block in zip(titles, batch["valueRanges"], strict=True)
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(grids))
    return grids


# slot label -> (slot, pick_type), matching `parser.py`'s vocabulary so both
# sources land in one table. Numbered labels are handled separately.
GSHEET_SLOTS = {
    "BB": ("bb", "best_bet"),
    "BEST BET": ("bb", "best_bet"),
    "UD": ("udog", "underdog"),
    "U-DOG": ("udog", "underdog"),
    "UNDERDOG": ("udog", "underdog"),
    "SD": ("sd", "survivor"),
    "SURVIVOR": ("sd", "survivor"),
    "MNF": ("mnf", "mnf"),
    "MON": ("mnf", "mnf"),
}
SLOT_NUM_RE = re.compile(r"^(?:PICK|GAME|GM)?\s*([1-6])$")

# side-tables that live in the pick grid and would otherwise read as people:
# "Griffin's Survivor Plan", "Original Picks", "Scores", "JHR week 5"
NOT_A_PICKER_RE = re.compile(r"\b(pick|plan|score|week|total|avg)", re.I)

# "TEAM" is the entry Team Reichert actually submits, not a person
PICKER_ALIASES = {"TEAM": "Team", "Griff": "Griffin"}

# header cells that sit right of the slot column but name no picker
NOT_A_PICKER = {
    "notes",
    "consensus",
    "visitor",
    "pool",
    "home",
    "away",
    "spreads",
    "spread",
    "line",
    "game",
    "moneyline",
    "week score",
    "final picks",
    "times selected",
    "pick",
    "picks",
}


def _slot_of(cell: str) -> tuple[str, str] | None:
    """Slot for a label cell, tolerating the annotations people type in.

    2021 week 3 labels its rows "BB. Late dad change" and "4. Changed from
    NE at Harry's request", so a leading slot token counts.
    """
    label = cell.strip().upper()
    for candidate in (label, label.split()[0].rstrip(".") if label.split() else ""):
        if candidate in GSHEET_SLOTS:
            return GSHEET_SLOTS[candidate]
        if m := SLOT_NUM_RE.match(candidate):
            return m.group(1), "regular"
    return None


def parse_picks_grid(rows: list[list[str]]) -> list[dict]:
    """Pull picks out of a pickers-as-columns week tab.

    2020 through 2024 all put slot labels down one column and a picker
    across each column to its right, but the slot column moves (col E in
    2020, col A in 2021) and the labels are spelled four different ways.
    So the slot column is found by counting recognisable labels, and a
    column only counts as a picker if its cells under those labels
    actually parse as teams — which is what rejects the notes, consensus
    and lines columns without having to name them all.

    Results in the sheet are ignored; picks are regraded from the
    schedule, so a mis-typed W/L cannot leak into the analysis.
    """
    slots_by_col: dict[int, list[tuple[int, str, str]]] = {}
    for r_idx, row in enumerate(rows):
        for c_idx, cell in enumerate(row):
            if slot := _slot_of(cell):
                slots_by_col.setdefault(c_idx, []).append((r_idx, *slot))

    # a bare '1' in a W/L cell reads as the "pick 1" slot, and the result
    # grid has hundreds of them — so the real slot column is the one that
    # also spells out a best bet, which no result column ever does
    with_bb = [c for c, v in slots_by_col.items() if any(s == "bb" for _, s, _ in v)]
    if not with_bb:
        return []

    def block(col: int) -> list[tuple[int, str, str]]:
        """The distinct slots in one run under this column's best bet."""
        bb_row = next(r for r, s, _ in slots_by_col[col] if s == "bb")
        rows_, seen = [], set()
        for r, slot, pick_type in slots_by_col[col]:
            if bb_row <= r <= bb_row + 12 and slot not in seen:
                seen.add(slot)
                rows_.append((r, slot, pick_type))
        return rows_

    # a season-summary block elsewhere on the tab can hold more slot-looking
    # cells than the pick grid, so score on distinct slots in one run and
    # break ties leftward — the pick grid comes before any copy of it
    slot_col = max(with_bb, key=lambda c: (len(block(c)), -c))
    slot_rows = block(slot_col)
    if len(slot_rows) < 5:
        return []
    first_slot_row = slot_rows[0][0]

    header = next(
        (
            r
            for r in range(first_slot_row - 1, -1, -1)
            if sum(1 for c in rows[r][slot_col + 1 :] if c.strip()) >= 2
        ),
        None,
    )
    if header is None:
        return []

    picks = []
    for col, name in enumerate(rows[header]):
        name = name.strip()
        # a column headed by a team abbreviation is a consensus tally, not
        # a person; nobody in this pool is called BUF
        if (
            col <= slot_col
            or not name
            or name.lower() in NOT_A_PICKER
            or NOT_A_PICKER_RE.search(name)
            or _abbr(name) is not None
        ):
            continue
        name = PICKER_ALIASES.get(name, name)
        teams = {
            slot: (_abbr(rows[r][col]), pick_type)
            for r, slot, pick_type in slot_rows
            if len(rows[r]) > col
        }
        hits = {s: v for s, v in teams.items() if v[0] is not None}
        if len(hits) < 5:  # a notes or scoring column, not a picker
            continue
        picks += [
            {
                "picker": name,
                "slot": slot,
                "pick_type": pick_type,
                "team_picked": team,
            }
            for slot, (team, pick_type) in hits.items()
        ]
    return picks


def pull_picks(season: int) -> pl.DataFrame:
    """Every pick in a season's workbook: season, week, picker, slot, team."""
    grids = raw_grids(season if season != 2024 else 2023)
    records = []
    for title, rows in grids.items():
        week = season_week(season, title)
        if week is None:
            continue
        records += [dict(p, week=week) for p in parse_picks_grid(rows)]

    if not records:
        return pl.DataFrame(
            schema={
                "season": pl.Int64,
                "week": pl.Int64,
                "picker": pl.String,
                "slot": pl.String,
                "pick_type": pl.String,
                "team_picked": pl.String,
            }
        )
    return (
        pl.DataFrame(records)
        .with_columns(season=pl.lit(season, pl.Int64))
        .select("season", "week", "picker", "slot", "pick_type", "team_picked")
        .sort("week", "picker", "slot")
    )
