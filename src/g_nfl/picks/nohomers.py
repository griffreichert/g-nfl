"""The `No Homers` entry: the mechanical benchmark the call has to beat (#58).

Six seasons say the room has no positive edge and several repeatable ways to
lose, and that anything systematic beat what Team Reichert actually submitted by
11 to 16 points of pool share. So the ledger needs an entry with no judgement in
it at all, submitted every week alongside the humans and graded in public.

Everything below is a rule that was measured, and the measurement is in
[[notes/pick-behaviour]] and [[notes/pick-analytics]]. None of them is an edge.
Three of the four beat what we did, which is the whole point.

| slot | rule | why |
|---|---|---|
| best bet, regulars | unflagged dogs, closest line first | 54.2% of pool points in the 2025 walk-forward against TEAM's 38.5%, and it needs no fitting |
| MNF | the Monday game's unflagged dog | same rule, forced onto one game |
| underdog | a 6-10 point dog | flat peak of the EV curve, 1.80 points a pick |
| survivor | biggest unused favourite | placeholder; the real problem is sequential and lives in survivor.py |

The best bet is the closest line rather than the strongest opinion, because
`pick-behaviour` found the double-points slot carries no information: best bets
hit 49.9% against 48.4% for regulars, and nothing tested separates them.
"""

from __future__ import annotations

from typing import Any

from g_nfl.picks.guardrails import RuleFit
from g_nfl.picks.sides import candidate_side

PICKER = "No Homers"

#: Pool slots this fills. Underdog and survivor are extra.
REGULARS = 5

#: The underdog pool pays the spread on an outright win, so EV is
#: P(win) x spread and the two terms fight. Measured over 2021-2025: 1-3 point
#: dogs return 1.06 points a pick, 3-6 return 1.60, 6-10 return 1.80, and 10+
#: return 1.04 while winning a fifth as often. The peak is shallow and this band
#: is where the room already picks.
DOG_BAND = (6.0, 10.0)


def _sides(games: list[Any]) -> list[dict[str, Any]]:
    """Both sides of every game, shaped for the guardrail predicates."""
    return [
        candidate_side(game, team)
        for game in games
        for team in (game.away_team, game.home_team)
    ]


def _clean(side: dict[str, Any], fits: list[RuleFit]) -> bool:
    """No qualifying guardrail fires on this side.

    Advisory rules are ignored. `pool_worse_than_market` reads the closing line,
    which does not exist when this entry is built.
    """
    return not any(
        f.rule.matches(side) for f in fits if f.qualifies and not f.rule.advisory
    )


def build_entry(games: list[Any], fits: list[RuleFit], spent: set[str]) -> list[dict]:
    """A complete entry: best bet, five regulars, MNF, underdog, survivor.

    `spent` is the survivor teams this entry has already used. Slots that cannot
    be filled are left out rather than filled with something the rules do not
    support, so a thin slate produces a short entry.
    """
    sides = _sides(games)
    mnf_ids = {g.game_id for g in games if g.is_mnf}

    picks: list[dict] = []
    used: set[str] = set()

    # MNF first: it is the one slot with no choice of game, so letting the
    # regulars pick that game first would leave the Monday slot unfillable.
    mnf = _best_dog([s for s in sides if s["game_id"] in mnf_ids], fits)
    if mnf:
        picks.append(_pick(mnf, "mnf"))
        used.add(mnf["game_id"])

    ats = [s for s in sides if s["game_id"] not in mnf_ids]
    for i, side in enumerate(_dogs_by_closest(ats, fits)[: REGULARS + 1]):
        if side["game_id"] in used:
            continue
        picks.append(_pick(side, "best_bet" if i == 0 else "regular"))
        used.add(side["game_id"])

    dog = _underdog(sides)
    if dog:
        picks.append(_pick(dog, "underdog"))

    survivor = _survivor(sides, spent)
    if survivor:
        picks.append(_pick(survivor, "survivor"))

    return picks


def _dogs_by_closest(sides: list[dict], fits: list[RuleFit]) -> list[dict]:
    """Unflagged dogs, closest line first, one per game."""
    dogs = [
        s
        for s in sides
        if s["picked_spread"] is not None and s["picked_spread"] > 0 and _clean(s, fits)
    ]
    dogs.sort(key=lambda s: (s["picked_spread"], s["game_id"]))
    seen: set[str] = set()
    out = []
    for side in dogs:
        if side["game_id"] in seen:
            continue
        seen.add(side["game_id"])
        out.append(side)
    return out


def _best_dog(sides: list[dict], fits: list[RuleFit]) -> dict | None:
    dogs = _dogs_by_closest(sides, fits)
    return dogs[0] if dogs else None


def _underdog(sides: list[dict]) -> dict | None:
    """A dog inside the EV band, the biggest one that qualifies.

    Guardrails do not apply: the slot pays on an outright win, so an ATS rule
    about which side covers says nothing about it.
    """
    low, high = DOG_BAND
    band = [
        s
        for s in sides
        if s["picked_spread"] is not None and low <= s["picked_spread"] <= high
    ]
    if not band:
        return None
    return max(band, key=lambda s: (s["picked_spread"], s["game_id"]))


def _survivor(sides: list[dict], spent: set[str]) -> dict | None:
    """Biggest favourite not already spent.

    Guardrails do not apply here either, for the same reason they do not apply
    to the underdog: they are ATS rules and this pool pays on an outright win.

    A placeholder, and knowingly the weak slot. The pool's survivor is a
    season-long assignment problem and `picks/survivor.py` solves it properly;
    wiring that in is worth doing once the entry has a week of history.
    """
    available = [
        s
        for s in sides
        if s["picked_spread"] is not None
        and s["picked_spread"] < 0
        and s["team"] not in spent
    ]
    if not available:
        return None
    return min(available, key=lambda s: (s["picked_spread"], s["game_id"]))


def _pick(side: dict, pick_type: str) -> dict:
    return {
        "game_id": side["game_id"],
        "team_picked": side["team"],
        "pick_type": pick_type,
        "spread": side["picked_spread"],
        "note": _note(side, pick_type),
    }


def _note(side: dict, pick_type: str) -> str:
    spread = side["picked_spread"]
    if pick_type == "underdog":
        return f"Dog inside the {DOG_BAND[0]:.0f}-{DOG_BAND[1]:.0f} EV band."
    if pick_type == "survivor":
        return f"Biggest unused favourite, laying {abs(spread):.1f}."
    return f"Unflagged dog, {spread:+.1f}. Closest lines first."


def submit(season: int | None = None, week: int | None = None, dry_run: bool = False):
    """Build and save this week's entry. Safe to re-run: it replaces its own week."""
    from g_nfl.api.main import get_lines
    from g_nfl.picks.calendar import current_season, current_week
    from g_nfl.picks.guardrails import fit
    from g_nfl.picks.history import load_history
    from g_nfl.utils.database import PicksDatabase

    season = season or current_season()
    week = week or current_week(season)

    games = get_lines(season, week)
    fits = fit(load_history())
    db = PicksDatabase()
    spent = {
        p["team_picked"]
        for p in db.get_season_picks(season)
        if p["picker"] == PICKER and p.get("pick_type") == "survivor"
    }

    entry = build_entry(games, fits, spent)
    for pick in entry:
        print(f"  {pick['pick_type']:<9} {pick['team_picked']:<4} {pick['note']}")

    if dry_run:
        print(f"\nwould submit {len(entry)} picks as {PICKER}, {season} week {week}")
        return entry

    # keyed the way PicksDatabase expects: special slots prefixed so they can
    # share a game with a regular pick
    payload = {
        (
            f"{p['pick_type']}_{p['game_id']}"
            if p["pick_type"] in ("survivor", "underdog", "mnf")
            else p["game_id"]
        ): p
        for p in entry
    }
    saved = db.save_picks(season, week, payload, PICKER)
    print(f"\nsubmitted {saved} picks as {PICKER}, {season} week {week}")
    return entry


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    submit(args.season, args.week, args.dry_run)


if __name__ == "__main__":
    main()
