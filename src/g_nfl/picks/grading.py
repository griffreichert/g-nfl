"""Grade saved picks against final game results and build picker standings.

Pure functions over plain dicts — runs on the deployed API, so no
polars/pandas (analysis-group deps stay out of core).

Conventions:
- ``spread`` on a pick is the game's market line at pick time, in the
  same convention as nflverse ``spread_line``: positive = home team
  favored by that many points (the app stores ``market_spread`` on
  every pick row).
- A game result row carries ``result`` = home score - away score.
- ATS pick types (regular, best_bet, mnf): picked home team covers
  when result > spread, picked away team covers when result < spread,
  equal is a push.
- Straight-up pick types (survivor, underdog): win when the picked
  team won the game outright; a tie is a push.
- Picks for games without a result yet are ``pending``; ATS picks with
  no stored spread are ``no_spread`` (ungradeable, reported but not
  counted in records).
"""

from collections import defaultdict
from typing import Any

# profit on a winning 1-unit bet at -110
WIN_PROFIT = 100 / 110
# win rate needed to break even at -110
BREAK_EVEN = 110 / 210

ATS_PICK_TYPES = {"regular", "best_bet", "mnf"}
STRAIGHT_UP_PICK_TYPES = {"survivor", "underdog"}
# pick types that count toward the headline ATS record and units
RECORD_PICK_TYPES = {"regular", "best_bet"}


def grade_pick(pick: dict[str, Any], result: float | None) -> str:
    """Outcome of one pick: win / loss / push / pending / no_spread.

    `result` is the game's home margin, or None if not played yet.
    """
    if result is None:
        return "pending"

    game_id = pick["game_id"]
    home_team = game_id.split("_")[3]
    picked_home = pick["team_picked"] == home_team

    if pick.get("pick_type", "regular") in STRAIGHT_UP_PICK_TYPES:
        if result == 0:
            return "push"
        home_won = result > 0
        return "win" if picked_home == home_won else "loss"

    spread = pick.get("spread")
    if spread is None:
        return "no_spread"
    margin_vs_spread = result - spread
    if margin_vs_spread == 0:
        return "push"
    home_covered = margin_vs_spread > 0
    return "win" if picked_home == home_covered else "loss"


def _empty_record() -> dict[str, Any]:
    return {"wins": 0, "losses": 0, "pushes": 0, "pending": 0, "win_pct": None}


def _tally(record: dict[str, Any], outcome: str) -> None:
    key = {"win": "wins", "loss": "losses", "push": "pushes", "pending": "pending"}
    if outcome in key:
        record[key[outcome]] += 1


def _finalize(record: dict[str, Any]) -> dict[str, Any]:
    decided = record["wins"] + record["losses"]
    record["win_pct"] = record["wins"] / decided if decided else None
    return record


def _units(record: dict[str, Any]) -> float:
    """Profit in units betting 1 unit per decided ATS pick at -110."""
    return record["wins"] * WIN_PROFIT - record["losses"]


def picker_standings(
    picks: list[dict[str, Any]], results: dict[str, float | None]
) -> list[dict[str, Any]]:
    """Season standings per picker, with a weekly cumulative trend.

    `picks` are pick rows (picker, game_id, team_picked, pick_type,
    spread, week); `results` maps game_id -> home margin (None or
    missing = not played). Returns one dict per picker, sorted by ATS
    units descending: headline ATS record/units over regular+best_bet,
    per-pick-type records, and a `weekly` list with cumulative units
    and win% week by week.
    """
    by_picker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in picks:
        by_picker[p["picker"]].append(p)

    standings = []
    for picker, picker_picks in by_picker.items():
        ats = _empty_record()
        by_type: dict[str, dict[str, Any]] = {}
        weekly_records: dict[int, dict[str, Any]] = {}
        no_spread = 0

        for p in picker_picks:
            outcome = grade_pick(p, results.get(p["game_id"]))
            if outcome == "no_spread":
                no_spread += 1
                continue
            pick_type = p.get("pick_type", "regular")
            _tally(by_type.setdefault(pick_type, _empty_record()), outcome)
            if pick_type in RECORD_PICK_TYPES:
                _tally(ats, outcome)
                _tally(weekly_records.setdefault(p["week"], _empty_record()), outcome)

        weekly = []
        cum_wins = cum_losses = 0
        cum_units = 0.0
        for week in sorted(weekly_records):
            rec = _finalize(weekly_records[week])
            cum_wins += rec["wins"]
            cum_losses += rec["losses"]
            cum_units += _units(rec)
            decided = cum_wins + cum_losses
            weekly.append(
                {
                    "week": week,
                    **rec,
                    "units": round(_units(rec), 3),
                    "cum_units": round(cum_units, 3),
                    "cum_win_pct": cum_wins / decided if decided else None,
                }
            )

        standings.append(
            {
                "picker": picker,
                "ats": _finalize(ats),
                "units": round(_units(ats), 3),
                "by_type": {t: _finalize(r) for t, r in sorted(by_type.items())},
                "no_spread": no_spread,
                "weekly": weekly,
            }
        )

    standings.sort(key=lambda s: s["units"], reverse=True)
    return standings
