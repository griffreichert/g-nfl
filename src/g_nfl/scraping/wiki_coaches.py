"""Fill the OC/DC layer of data/coaches/playcallers.csv from Wikipedia team-season
articles' wikitext staff lists.

PFR blocks WebFetch/requests with a 403 (Cloudflare challenge), so Wikipedia's
raw wikitext is the working structured source. Coverage isn't total: some
team-seasons list "Assistant head coach/offensive coordinator" style compound
titles or use a table instead of a bullet list, and some genuinely have no OC
line because the HC calls the offense himself (e.g. SF/Shanahan every year in
this window) — see data/coaches/README.md for the miss list and why it's
mostly not a parsing bug.
"""

import re
import time

import polars as pl
import requests

from g_nfl.scraping.coaches import PLAYCALLER_COLUMNS

TEAM_NAMES = {
    "ARI": "Arizona_Cardinals",
    "ATL": "Atlanta_Falcons",
    "BAL": "Baltimore_Ravens",
    "BUF": "Buffalo_Bills",
    "CAR": "Carolina_Panthers",
    "CHI": "Chicago_Bears",
    "CIN": "Cincinnati_Bengals",
    "CLE": "Cleveland_Browns",
    "DAL": "Dallas_Cowboys",
    "DEN": "Denver_Broncos",
    "DET": "Detroit_Lions",
    "GB": "Green_Bay_Packers",
    "HOU": "Houston_Texans",
    "IND": "Indianapolis_Colts",
    "JAX": "Jacksonville_Jaguars",
    "KC": "Kansas_City_Chiefs",
    "LA": "Los_Angeles_Rams",
    "LAC": "Los_Angeles_Chargers",
    "LV": "Las_Vegas_Raiders",
    "MIA": "Miami_Dolphins",
    "MIN": "Minnesota_Vikings",
    "NE": "New_England_Patriots",
    "NO": "New_Orleans_Saints",
    "NYG": "New_York_Giants",
    "NYJ": "New_York_Jets",
    "PHI": "Philadelphia_Eagles",
    "PIT": "Pittsburgh_Steelers",
    "SEA": "Seattle_Seahawks",
    "SF": "San_Francisco_49ers",
    "TB": "Tampa_Bay_Buccaneers",
    "TEN": "Tennessee_Titans",
    "WAS": "Washington_Commanders",
}

# historical franchise names by season, overriding TEAM_NAMES above
HISTORICAL = {
    ("LA", 2015): "St._Louis_Rams",
    ("LAC", 2015): "San_Diego_Chargers",
    ("LAC", 2016): "San_Diego_Chargers",
    ("LV", 2015): "Oakland_Raiders",
    ("LV", 2016): "Oakland_Raiders",
    ("LV", 2017): "Oakland_Raiders",
    ("LV", 2018): "Oakland_Raiders",
    ("LV", 2019): "Oakland_Raiders",
    ("WAS", 2015): "Washington_Redskins",
    ("WAS", 2016): "Washington_Redskins",
    ("WAS", 2017): "Washington_Redskins",
    ("WAS", 2018): "Washington_Redskins",
    ("WAS", 2019): "Washington_Redskins",
    ("WAS", 2020): "Washington_Football_Team",
    ("WAS", 2021): "Washington_Football_Team",
}

ROLE_PATTERNS = [
    ("HC", re.compile(r"^head coach\b", re.I)),
    ("OC", re.compile(r"\boffensive coordinator\b", re.I)),
    ("DC", re.compile(r"\bdefensive coordinator\b", re.I)),
]

LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
BULLET_RE = re.compile(r"^\*+\s*([^–—-]+?)\s*[–—-]\s*(.+)$")


def extract_name(value: str) -> str | None:
    m = LINK_RE.search(value)
    if m:
        return (m.group(2) or m.group(1)).strip()
    # no wikilink - strip refs/braces, take plain text
    plain = re.sub(r"\{\{.*?\}\}|<ref.*?</ref>|<ref[^/]*/>", "", value).strip()
    plain = plain.split("{{")[0].strip()
    return plain or None


def fetch_wikitext(title: str) -> str | None:
    url = f"https://en.wikipedia.org/w/index.php?title={title}&action=raw"
    r = requests.get(url, headers={"User-Agent": "g-nfl-research/1.0"}, timeout=15)
    if r.status_code != 200:
        return None
    return r.text


def parse_staff(wikitext: str) -> dict:
    found = {}
    for line in wikitext.splitlines():
        m = BULLET_RE.match(line.strip())
        if not m:
            continue
        role_text, value = m.group(1).strip(), m.group(2).strip()
        for role, pattern in ROLE_PATTERNS:
            if pattern.match(role_text) and role not in found:
                name = extract_name(value)
                if name:
                    found[role] = name
    return found


def title_for(season: int, team: str) -> str:
    franchise = HISTORICAL.get((team, season), TEAM_NAMES[team])
    return f"{season}_{franchise}_season"


def build_oc_dc(start_season=2015, end_season=2025, sleep=0.3):
    rows = []
    misses = []
    for season in range(start_season, end_season + 1):
        for team in TEAM_NAMES:
            title = title_for(season, team)
            wt = fetch_wikitext(title)
            time.sleep(sleep)
            if wt is None:
                misses.append((season, team, title, "fetch_failed"))
                continue
            staff = parse_staff(wt)
            url = f"https://en.wikipedia.org/wiki/{title}"
            for role in ("OC", "DC"):
                if role in staff:
                    rows.append(
                        (
                            season,
                            team,
                            role,
                            staff[role],
                            1,
                            18,
                            0,
                            None,
                            None,
                            None,
                            url,
                            "medium",
                        )
                    )
                else:
                    misses.append((season, team, title, f"no_{role}"))
    return rows, misses


def merge_into_csv(
    rows: list[tuple], path: str = "data/coaches/playcallers.csv"
) -> pl.DataFrame:
    """Add sweep rows without overwriting any (season, team, role) already present."""
    import os

    sweep = pl.DataFrame(rows, schema=PLAYCALLER_COLUMNS, orient="row")
    if os.path.exists(path):
        existing = pl.read_csv(path)
        existing_keys = existing.select(["season", "team", "role"]).unique()
        sweep_new = sweep.join(existing_keys, on=["season", "team", "role"], how="anti")
        out = pl.concat([existing, sweep_new], how="diagonal_relaxed")
    else:
        out = sweep
    out = out.sort(["season", "team", "role", "start_week"])
    out.write_csv(path)
    return out


if __name__ == "__main__":
    rows, misses = build_oc_dc()
    print(f"got {len(rows)} OC/DC rows, {len(misses)} misses")
    out = merge_into_csv(rows)
    print(f"merged into data/coaches/playcallers.csv, now {len(out)} rows total")
    for season, team, _title, reason in misses:
        print(f"  miss: {season} {team} ({reason})")
