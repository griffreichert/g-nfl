"""What the weekly call is worth, measured (#58).

Two independent sources say the call costs about 1.5 points of hit rate against
the members who sit on it: Reichert against its own members over 2020-2024
(46.0% to 48.0%), and Reichert against the other fifteen Cville entries in 2025
(43.8% to 49.8%). Neither is significant alone. Six seasons pointing the same
way is worth acting on, and [[notes/pick-behaviour]] names the test: log each
member's picks and the submitted set, then score the naive alternatives against
the call.

This is that test, run weekly and in public. Everything is in **pool points**,
because that is what the pool pays: best bet 2, regular 1, MNF 1, push a half.

| entry | what it is |
|---|---|
| TEAM | what the call actually submitted |
| Majority | the side most members took, slot by slot |
| Best member | whoever leads on points *going into* the week, so it never uses the future |
| No Homers | the mechanical entry, `picks/nohomers.py` |
| gModel, bModel | the two model pickers, if they submitted |

If TEAM keeps losing to Majority, that is the finding, and the process should
change mid-season rather than at the end of it.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from g_nfl.picks.grading import grade_pick

#: Pool points per slot. Distinct games per slot is the pool's own rule.
SLOT_POINTS = {"best_bet": 2.0, "regular": 1.0, "mnf": 1.0}

#: Slots this scores. Underdog and survivor are separate pools with different
#: objectives, so mixing them into one number would be meaningless.
SLOTS = tuple(SLOT_POINTS)

TEAM = "TEAM"
MAJORITY = "Majority"
BEST_MEMBER = "Best member"

#: Entries that are outputs rather than opinions, so they never vote in the
#: majority and are never "the best member".
NOT_MEMBERS = frozenset({TEAM, "TEST"})


def score(
    pick: dict[str, Any], result: float | None, line: float | None
) -> float | None:
    """Pool points a pick earned, or None if it cannot be graded yet."""
    outcome = grade_pick(pick, result, line)
    points = SLOT_POINTS.get(pick.get("pick_type", "regular"), 0.0)
    if outcome == "win":
        return points
    if outcome == "loss":
        return 0.0
    if outcome == "push":
        return points / 2
    return None


def majority_entry(picks: list[dict]) -> list[dict]:
    """The room's own picks, resolved slot by slot to one entry.

    Ties break on the game with the most votes overall, then on game id, so the
    entry is the same every time it is built.
    """
    entry: list[dict] = []
    used: set[str] = set()

    for slot in ("mnf", "best_bet", "regular"):
        votes: dict[tuple[str, str], int] = defaultdict(int)
        for p in picks:
            if p.get("pick_type") == slot and p["picker"] not in NOT_MEMBERS:
                votes[(p["game_id"], p["team_picked"])] += 1

        ranked = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
        want = 5 if slot == "regular" else 1
        for (game_id, team), _count in ranked:
            if len([e for e in entry if e["pick_type"] == slot]) >= want:
                break
            if game_id in used:
                continue
            used.add(game_id)
            entry.append({"game_id": game_id, "team_picked": team, "pick_type": slot})
    return entry


def weekly(
    picks: list[dict],
    results: dict[str, float],
    lines: dict[str, float],
) -> list[dict[str, Any]]:
    """Pool points per entry per week, plus a running total.

    `picks` is a season of rows from the `picks` table. Weeks with nothing
    graded yet are left out rather than reported as zero.
    """
    by_week: dict[int, list[dict]] = defaultdict(list)
    for p in picks:
        if p.get("pick_type") in SLOTS:
            by_week[p["week"]].append(p)

    running: dict[str, float] = defaultdict(float)
    rows: list[dict[str, Any]] = []

    for week in sorted(by_week):
        week_picks = by_week[week]
        entries: dict[str, list[dict]] = defaultdict(list)
        for p in week_picks:
            entries[p["picker"]].append(p)

        entries[MAJORITY] = majority_entry(week_picks)

        # "Best" is decided on the table as it stood before this week, so the
        # benchmark never reads a result it could not have known.
        leader = _leader(running, entries)
        if leader:
            entries[BEST_MEMBER] = entries[leader]

        for name, entry in entries.items():
            scored = [
                score(p, results.get(p["game_id"]), lines.get(p["game_id"]))
                for p in entry
            ]
            graded = [s for s in scored if s is not None]
            if not graded:
                continue
            points = sum(graded)
            running[name] += points
            rows.append(
                {
                    "week": week,
                    "entry": name,
                    "points": points,
                    "available": sum(
                        SLOT_POINTS.get(p.get("pick_type", "regular"), 0.0)
                        for p, s in zip(entry, scored, strict=True)
                        if s is not None
                    ),
                    "running": running[name],
                    "leader": leader if name == BEST_MEMBER else None,
                }
            )
    return rows


def _leader(running: dict[str, float], entries: dict[str, list[dict]]) -> str | None:
    """The member with most points so far who also submitted this week."""
    candidates = [
        name
        for name in entries
        if name not in NOT_MEMBERS and name not in (MAJORITY, BEST_MEMBER)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda name: (running.get(name, 0.0), name))


def standings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Season totals per entry, best first."""
    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"points": 0.0, "available": 0.0, "weeks": 0}
    )
    for row in rows:
        t = totals[row["entry"]]
        t["points"] += row["points"]
        t["available"] += row["available"]
        t["weeks"] += 1

    out = [
        {
            "entry": name,
            "points": t["points"],
            "available": t["available"],
            "weeks": int(t["weeks"]),
            "share": t["points"] / t["available"] if t["available"] else None,
        }
        for name, t in totals.items()
    ]
    out.sort(key=lambda d: (-(d["share"] or 0), d["entry"]))
    return out
