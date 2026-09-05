"""The `gModel` entry: the champion's line against the pool's (#13).

`ml/predict.py` produces the week's board and grades it against the market
close. This turns that board into a pool entry, which is a different number:
the pool grades against its own spread (notes/SCORING.md), so the edge here
is the model's line against the pool line, and the market close only stands in
where the Friday number has not been entered yet.

Every run stores the whole board, not the seven games that become an entry.
The picks table is what the room sees; `model_predictions` is what a later
question gets asked of, and the six games gModel passed over are half of any
answer about whether it can pick.

| slot | rule |
|---|---|
| best bet, regulars | largest edge against the pool line, one side per game |
| MNF | the Monday game's better side, taken first so the slot can be filled |
| underdog | the dog with the most expected points: P(outright) x the spread |
| survivor | this week's leg of the best remaining path (`survivor.py`) |

Expectation, from six seasons and four independent disproofs
(notes/modelling/scoreboard.md): gModel is a coin flip against the pool line.
The entry exists to put a benchmark on the ledger, not to find edge.
"""

import argparse
import hashlib
import json
import os
import subprocess
from typing import Any

import polars as pl

from g_nfl.ml.models.spread import DEFAULT_PARAMS
from g_nfl.ml.predict import FEATURE_SET, predict_week, refresh_season, training_seasons
from g_nfl.ml.train import CHAMPION_PARAMS, DEFAULT_CARRYOVER_K, DEFAULT_TARGET
from g_nfl.picks.survivor import win_probability

PICKER = "gModel"

#: Pool slots this fills. Underdog and survivor are extra.
REGULARS = 5


def board_rows(preds: pl.DataFrame, games: list[Any]) -> list[dict]:
    """The week's board: one row per game, the model against the pool line.

    `games` are `GameLine`s from the API, carrying both numbers. A game with
    neither line keeps its prediction and carries a null edge, which is how a
    Tuesday run before the lines land still stores a board.
    """
    lines = {g.game_id: g for g in games}
    rows = []
    for row in preds.iter_rows(named=True):
        game = lines.get(row["game_id"])
        pool = game.pool_spread if game else None
        market = game.market_spread if game else row["spread_line"]
        line = pool if pool is not None else market
        rows.append(
            {
                "season": row["season"],
                "week": row["week"],
                "game_id": row["game_id"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "pred_margin": round(row["pred"], 3),
                "pool_spread": pool,
                "market_spread": market,
                "edge": None if line is None else round(row["pred"] - line, 3),
                "line_source": None
                if line is None
                else ("pool" if pool is not None else "market"),
                "home_win_prob": round(win_probability(row["pred"]), 4),
            }
        )
    return rows


def sides(board: list[dict]) -> list[dict]:
    """Both sides of every priced game, seen from the side.

    `edge` is signed for the side, so positive means the model makes this team
    better than the line does. `points` is what the side is getting, positive
    for a dog, matching `analytics.from_picked`.
    """
    out = []
    for row in board:
        if row["edge"] is None:
            continue
        line = (
            row["pool_spread"]
            if row["pool_spread"] is not None
            else row["market_spread"]
        )
        for team, home in ((row["home_team"], True), (row["away_team"], False)):
            margin = row["pred_margin"] if home else -row["pred_margin"]
            out.append(
                {
                    "game_id": row["game_id"],
                    "team": team,
                    "home": home,
                    "edge": row["edge"] if home else -row["edge"],
                    "points": -line if home else line,
                    "model_points": -margin,
                    "win_prob": win_probability(margin),
                }
            )
    return out


def build_entry(
    board: list[dict],
    mnf_ids: set[str],
    spent: set[str],
    survivor: dict | None = None,
) -> list[dict]:
    """A complete entry: best bet, five regulars, MNF, underdog, survivor.

    Games rank by the size of the edge and each is used once. MNF fills first,
    because it is the one slot with no choice of game and letting the regulars
    take that game would leave it unfillable. Slots that cannot be filled are
    left out, so a thin slate produces a short entry.
    """
    all_sides = sides(board)
    best: dict[str, dict] = {}
    for side in all_sides:
        held = best.get(side["game_id"])
        if held is None or side["edge"] > held["edge"]:
            best[side["game_id"]] = side

    picks = []
    mnf = [s for s in best.values() if s["game_id"] in mnf_ids]
    if mnf:
        picks.append(_pick(max(mnf, key=lambda s: (s["edge"], s["game_id"])), "mnf"))

    # every surviving side is the better half of its game, so its edge is
    # already the size of the disagreement
    ats = sorted(
        (s for s in best.values() if s["game_id"] not in mnf_ids),
        key=lambda s: (-s["edge"], s["game_id"]),
    )
    for i, side in enumerate(ats[: REGULARS + 1]):
        picks.append(_pick(side, "best_bet" if i == 0 else "regular"))

    dog = underdog(all_sides)
    if dog:
        picks.append(_pick(dog, "underdog"))

    survivor = survivor or biggest_favourite(all_sides, spent)
    if survivor:
        picks.append(_pick(survivor, "survivor"))

    return picks


def underdog(all_sides: list[dict]) -> dict | None:
    """The dog with the most expected points: P(outright win) x the spread.

    The slot pays the spread on an outright win, so the two terms fight and
    the best dog is somewhere in the middle of the board rather than at
    either end (notes/pick-analytics.md).
    """
    dogs = [s for s in all_sides if s["points"] > 0]
    if not dogs:
        return None
    return max(dogs, key=lambda s: (s["win_prob"] * s["points"], s["game_id"]))


def biggest_favourite(all_sides: list[dict], spent: set[str]) -> dict | None:
    """Highest win probability among teams this entry has not spent.

    The fallback for survivor, used when a season has no board artifact to
    plan against. Knowingly the weak rule: survivor is a season-long
    assignment problem and this answers only for Sunday.
    """
    available = [s for s in all_sides if s["team"] not in spent]
    if not available:
        return None
    return max(available, key=lambda s: (s["win_prob"], s["game_id"]))


def survivor_side(
    season: int, week: int, board: list[dict], spent: set[str]
) -> dict | None:
    """This week's leg of the best remaining survivor path.

    The planner solves the rest of the season at once, so the team it spends
    now is the one whose absence costs the future least. gModel's predictions
    replace the board's own numbers for this week; later weeks keep the
    artifact's ratings, which is all anyone has for them. None when the season
    has no artifact, and the caller falls back to the biggest favourite.
    """
    from g_nfl.picks.survivor import plan
    from g_nfl.picks.survivor_board import build_board

    try:
        model_board, teams, weeks = build_board(
            season,
            week,
            spent=sorted(spent),
            market_spreads={r["game_id"]: r["pred_margin"] for r in board},
        )
    except FileNotFoundError:
        return None

    solved = plan(model_board, teams, weeks)
    if not solved:
        return None
    leg = next(p for p in solved["picks"] if p["week"] == week)
    side = next(s for s in sides(board) if s["team"] == leg["team"])
    return {**side, "win_prob": leg["prob"], "survival": solved["survival"]}


def _pick(side: dict, pick_type: str) -> dict:
    return {
        "game_id": side["game_id"],
        "team_picked": side["team"],
        "pick_type": pick_type,
        "spread": side["points"],
        "note": _note(side, pick_type),
    }


def _note(side: dict, pick_type: str) -> str:
    if pick_type == "underdog":
        points = side["win_prob"] * side["points"]
        return (
            f"{side['win_prob']:.0%} to win outright getting "
            f"{side['points']:+.1f}: {points:.2f} points."
        )
    if pick_type == "survivor":
        survival = side.get("survival")
        path = f", path survives {survival:.1%}" if survival else ""
        return f"{side['win_prob']:.0%} to win outright{path}."
    return (
        f"Model {side['team']} {side['model_points']:+.1f}, "
        f"line {side['points']:+.1f}: edge {side['edge']:+.1f}."
    )


def fingerprint(config: dict[str, Any], board: list[dict]) -> str:
    """Hash of everything that moved a number in this run.

    Two runs of a week are the same run when the predictions and the lines
    both match: new injury data or restated play-by-play changes the
    predictions, and a corrected pool line changes the lines. So a Wednesday
    run and a Saturday one are kept apart and comparable, while a cron retry
    against unchanged inputs lands on the row already there.

    The predictions stand in for the features that produced them, which is
    the honest test — a data change nothing predicts differently on is not a
    different run.
    """
    numbers = sorted(
        (r["game_id"], r["pred_margin"], r["pool_spread"], r["market_spread"])
        for r in board
    )
    payload = json.dumps([config, numbers], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def format_board(season: int, week: int, board: list[dict], entry: list[dict]) -> str:
    """The week's board as a table, biggest disagreement with the market first.

    Sorted on the market, because the close is the sharper of the two numbers
    and the honest read on whether the model saw something. The pool column is
    what the picks are graded against, so both are shown; they only differ
    once the Friday number is entered.

    Every number is a home spread: negative is the home team laying points.
    """
    # one game can carry several slots: the best bet and the underdog are
    # often the same side, and the survivor is a team rather than a side
    taken: dict[str, list[str]] = {}
    for pick in entry:
        taken.setdefault(pick["game_id"], []).append(
            f"{pick['team_picked']} {pick['pick_type']}"
        )

    rows = []
    for row in board:
        market, pool, model = (
            row["market_spread"],
            row["pool_spread"],
            row["pred_margin"],
        )
        rows.append(
            {
                **row,
                "vs_mkt": None if market is None else model - market,
                "vs_pool": None if pool is None else model - pool,
            }
        )
    rows.sort(key=lambda r: -abs(r["vs_mkt"] or 0))

    head = (
        f"{'matchup':<13}{'model':>7}{'market':>8}{'vs mkt':>8}"
        f"{'pool':>8}{'vs pool':>9}   picks"
    )
    lines = [
        f"\n{PICKER} {season} week {week} — {len(board)} games, "
        "sorted by disagreement with the market\n",
        head,
        "-" * len(head),
    ]
    for row in rows:
        market, vs_mkt, pool, vs_pool = (
            f"{v:+.1f}" if v is not None else "--"
            for v in (
                row["market_spread"],
                row["vs_mkt"],
                row["pool_spread"],
                row["vs_pool"],
            )
        )
        lines.append(
            f"{row['away_team'] + ' @ ' + row['home_team']:<13}"
            f"{row['pred_margin']:>+7.1f}{market:>8}{vs_mkt:>8}{pool:>8}{vs_pool:>9}"
            f"   {', '.join(taken.get(row['game_id'], []))}"
        )
    return "\n".join(lines) + "\n"


def git_sha() -> str | None:
    """The commit this ran from, so a run can be rebuilt at its own code."""
    if sha := os.environ.get("GITHUB_SHA"):
        return sha
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return result.stdout.strip() or None


def submit(
    season: int | None = None,
    week: int | None = None,
    dry_run: bool = False,
    refresh: bool = True,
) -> dict[str, Any]:
    """Predict the week, store the board, submit the entry.

    Safe to re-run: the picks table replaces this picker's week, and the board
    lands on its own fingerprint.
    """
    from g_nfl.api.main import get_lines
    from g_nfl.picks.calendar import current_season, current_week
    from g_nfl.utils.database import ModelRunsDatabase, PicksDatabase

    season = season or current_season()
    week = week or current_week(season)
    if refresh:
        refresh_season(season)

    games = get_lines(season, week)
    board = board_rows(predict_week(season, week), games)

    db = PicksDatabase()
    spent = {
        p["team_picked"]
        for p in db.get_season_picks(season)
        if p["picker"] == PICKER and p.get("pick_type") == "survivor"
    }
    entry = build_entry(
        board,
        mnf_ids={g.game_id for g in games if g.is_mnf},
        spent=spent,
        survivor=survivor_side(season, week, board, spent),
    )

    config = {
        "feature_set": FEATURE_SET,
        "target": DEFAULT_TARGET,
        "carryover_k": DEFAULT_CARRYOVER_K,
        "params": {**DEFAULT_PARAMS, **CHAMPION_PARAMS},
        "train_seasons": training_seasons(season),
        "git_sha": git_sha(),
    }
    if dry_run:
        print(format_board(season, week, board, entry))
        print(f"would store {len(board)} predictions, submit {len(entry)} picks")
        return {"board": board, "entry": entry, "config": config}

    runs = ModelRunsDatabase()
    run_id = runs.save_run(
        {
            "model": PICKER,
            "season": season,
            "week": week,
            "fingerprint": fingerprint(config, board),
            "n_games": len(board),
            **config,
        }
    )
    runs.save_predictions(run_id, board)

    payload = {
        (
            f"{p['pick_type']}_{p['game_id']}"
            if p["pick_type"] in ("survivor", "underdog", "mnf")
            else p["game_id"]
        ): p
        for p in entry
    }
    saved = db.save_picks(season, week, payload, PICKER)
    runs.mark_submitted(run_id, season, week, PICKER)
    # last, because save_picks prints a wall of debug rows the table would
    # otherwise scroll off the screen
    print(format_board(season, week, board, entry))
    print(f"stored {len(board)} predictions, run {run_id}")
    print(f"submitted {saved} picks as {PICKER}, {season} week {week}")
    return {"board": board, "entry": entry, "config": config, "run_id": run_id}


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="use the cached season data instead of refetching it",
    )
    args = parser.parse_args()
    submit(args.season, args.week, args.dry_run, refresh=not args.no_refresh)


if __name__ == "__main__":
    main()
