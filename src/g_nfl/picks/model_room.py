"""gModel against the room: is the model worth a vote? (plan item 5).

The room is 45-48% and gModel is a coin flip against the pool line
(notes/modelling/scoreboard.md). Neither is an edge on its own. The untested
question is what happens where they disagree: if the room is wrong more often
on those games, "gModel disagrees" earns a place beside the four behavioural
guardrails, and if it is not, the answer to how gModel combines with consensus
is that it does not.

Four measurements over 2020-2025, all on walk-forward predictions so no fold
sees its own week:

1. the room's rate by how hard the model agrees or disagrees with the side
2. the model's rate on games the members split evenly, which is the only
   place a tiebreak can act
3. the model as a fifth guardrail: veto a side the model dislikes by X or
   more, replaced by flip and by substitute, in pool points
4. the majority entry with the model's vote added, against the majority of
   members alone

The rules and the thresholds here were read off the same six seasons they are
scored on. Only the veto sweep is held out season by season, and even that
chose its shape after the fact. 2026 is the first honest season.
"""

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

import polars as pl

from g_nfl.picks.analytics import summarize
from g_nfl.picks.backtest import SLOT_POINTS, run
from g_nfl.picks.guardrails import Rule, build_rules, fit, load_config
from g_nfl.picks.history import TEAM_PICKERS
from g_nfl.picks.ledger import majority_entry

#: Boundaries of the |model edge| bands, in points.
EDGE_BANDS = (1.0, 3.0, 7.0)

#: How far the model has to dislike a side before the veto fires, swept.
VETO_THRESHOLDS = (1.0, 2.0, 3.0, 4.0)


def load_predictions(path: Path | str) -> dict[str, float]:
    """Predicted home margin per game, from a walk-forward preds parquet."""
    preds = pl.read_parquet(path)
    return dict(zip(preds["game_id"].to_list(), preds["pred"].to_list(), strict=True))


def attach_model(
    rows: list[dict[str, Any]], preds: dict[str, float]
) -> list[dict[str, Any]]:
    """Rows the model has a line for, carrying its view of the side taken.

    ``model_edge`` is the model's margin minus the line the pick graded
    against, signed from the picked side: positive means the model likes the
    side the room took. Rows with no prediction or no line are dropped, since
    there is nothing to compare.
    """
    out = []
    for r in rows:
        pred = preds.get(r["game_id"])
        if pred is None or r["line"] is None:
            continue
        home_edge = pred - r["line"]
        out.append({**r, "model_edge": home_edge if r["picked_home"] else -home_edge})
    return out


def edge_size(edge: float) -> str:
    """How far the model's line sits from the pool's, as a band label."""
    size = abs(edge)
    for hi in EDGE_BANDS:
        if size < hi:
            return f"<{hi:g}"
    return f"{EDGE_BANDS[-1]:g}+"


def edge_band(edge: float) -> str:
    """The band a pick falls in: which way the model leans, and how hard."""
    return f"{'agrees' if edge > 0 else 'disagrees'} {edge_size(edge)}"


def agreement(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The room's rate by band, clustered per game and shrunk."""
    return summarize(rows, lambda r: edge_band(r["model_edge"]))


def ats_winners(rows: list[dict[str, Any]]) -> dict[str, str]:
    """The side that covered, per game.

    Read off the room's own result: a pick that lost means the other side
    covered. Pushes never reach here, `graded_rows` drops them.
    """
    return {r["game_id"]: (r["team"] if r["won"] else r["opp"]) for r in rows}


def model_sides(rows: list[dict[str, Any]]) -> dict[str, str]:
    """The side the model would have taken, per game."""
    return {
        r["game_id"]: (r["team"] if r["model_edge"] > 0 else r["opp"]) for r in rows
    }


def even_splits(rows: list[dict[str, Any]], min_votes: int = 2) -> list[dict[str, Any]]:
    """Games the members split down the middle, with the model's side on each.

    A tiebreak can only act where the room has no collective opinion, and an
    even split is the whole of that set. `min_votes` per side keeps out the
    1-1 games, where "the room split" is two people.
    """
    votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["picker"] not in TEAM_PICKERS:
            votes[r["game_id"]][r["team"]] += 1

    winners = ats_winners(rows)
    sides = model_sides(rows)
    out = []
    for game_id, tally in sorted(votes.items()):
        if len(tally) != 2:
            continue
        (_a, count_a), (_b, count_b) = tally.items()
        if count_a != count_b or count_a < min_votes:
            continue
        out.append(
            {
                "game_id": game_id,
                "votes": count_a,
                "model_side": sides[game_id],
                "model_won": sides[game_id] == winners[game_id],
            }
        )
    return out


def magnitude(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The room's rate by how far the model sits from the line, either way.

    The direction cut is the one the plan asks for; this one is the control.
    A band that is bad whichever side the model takes is not the model
    disagreeing, it is the model and the room both reacting to the size of
    the line.
    """
    return summarize(rows, lambda r: edge_size(r["model_edge"]))


def veto_rule(threshold: float) -> Rule:
    """A rule that fires when the model dislikes a side by `threshold` or more."""
    return Rule(
        f"model_dislikes_{threshold:g}",
        f"Model disagrees by {threshold:g}+",
        "The model's line puts this side behind the number the pool posted.",
        lambda row, t=threshold: (
            row.get("model_edge") is not None and row["model_edge"] <= -t
        ),
    )


def model_votes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One vote for the model's side of every game, in every ATS slot.

    The tallies in `ledger.majority_entry` are per slot, so a vote in each is
    what carries the model's opinion into all three of them at the weight one
    member's pick carries in the tally it appears in.
    """
    sides = model_sides(rows)
    weeks = {(r["season"], r["week"], r["game_id"]) for r in rows}
    return [
        {
            "picker": "gModel",
            "season": season,
            "week": week,
            "game_id": game_id,
            "team_picked": sides[game_id],
            "pick_type": slot,
        }
        for season, week, game_id in sorted(weeks)
        for slot in SLOT_POINTS
    ]


def as_pick(row: dict[str, Any]) -> dict[str, Any]:
    """A graded row in the shape `ledger.majority_entry` reads."""
    return {
        "picker": row["picker"],
        "season": row["season"],
        "week": row["week"],
        "game_id": row["game_id"],
        "team_picked": row["team"],
        "pick_type": row["slot"],
    }


def majority_points(
    rows: list[dict[str, Any]], picks: list[dict[str, Any]]
) -> tuple[float, float]:
    """(points, available) for the majority entry built from `picks`.

    `rows` supply the outcomes, so the entry can be scored on a side nobody
    in the room took.
    """
    winners = ats_winners(rows)
    by_week: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for p in picks:
        by_week[(p["season"], p["week"])].append(p)

    points = available = 0.0
    for week_picks in by_week.values():
        for pick in majority_entry(week_picks):
            slot_points = SLOT_POINTS[pick["pick_type"]]
            available += slot_points
            if winners[pick["game_id"]] == pick["team_picked"]:
                points += slot_points
    return points, available


def report(
    rows: list[dict[str, Any]], preds: dict[str, float], entry_pickers: set[str]
) -> str:
    """Every measurement, as one markdown page."""
    rows = attach_model(rows, preds)
    members = [r for r in rows if r["picker"] not in entry_pickers]
    lines = [
        "# gModel against the room",
        "",
        f"{len(members)} member picks over "
        f"{len({r['game_id'] for r in members})} games, "
        f"{min(r['season'] for r in rows)}-{max(r['season'] for r in rows)}. "
        "Predictions are walk-forward, so no week is in its own training set.",
        "",
        "## The room's rate, by how hard the model leans",
        "",
        "| band | games | picks | raw | shrunk | z |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cell in agreement(members):
        lines.append(
            f"| {cell['key']} | {cell['games']:.0f} | {cell['picks']} | "
            f"{(cell['pct'] or 0):.1%} | {cell['shrunk_pct']:.1%} | "
            f"{(cell['z'] or 0):+.2f} |"
        )

    splits = even_splits(members)
    won = sum(1 for s in splits if s["model_won"])
    lines += [
        "",
        "## The tiebreak: games the members split evenly",
        "",
        f"{len(splits)} games split down the middle. The model's side covered "
        f"{won} of them, {won / len(splits):.1%}."
        if splits
        else "No game was split evenly.",
        "",
        "## The veto: drop a side the model dislikes",
        "",
        "`flip` takes the other side of the same game, `substitute` swaps in "
        "the room's most-agreed clean side that week. Both in pool points over "
        "the whole span, fitted leave-one-season-out.",
        "",
        "| threshold | games | room's rate | shrunk | earns the board | flip | substitute |",
        "|---|---:|---:|---:|---|---:|---:|",
    ]
    config = load_config()
    for threshold in VETO_THRESHOLDS:
        rule = veto_rule(threshold)
        scored = fit(members, config, [rule])[0]
        deltas = []
        for policy in ("flip", "substitute"):
            replays = run(
                rows,
                entry_pickers,
                policy=policy,
                config=config,
                rules=[rule],
                require_qualified=False,
            )
            deltas.append(sum(r.delta for r in replays))
        lines.append(
            f"| {threshold:g}+ | {scored.games:.0f} | {(scored.pct or 0):.1%} | "
            f"{scored.shrunk_pct:.1%} | "
            f"{'yes' if scored.qualifies else 'no, ' + scored.reason} | "
            f"{deltas[0]:+.0f} | {deltas[1]:+.0f} |"
        )

    lines += [
        "",
        "## The control: the same bands, ignoring which way the model leans",
        "",
        "| band | games | raw | shrunk | mean line |",
        "|---|---:|---:|---:|---:|",
    ]
    for cell in magnitude(members):
        sized = [
            abs(r["line"]) for r in members if edge_size(r["model_edge"]) == cell["key"]
        ]
        lines.append(
            f"| {cell['key']} | {cell['games']:.0f} | {(cell['pct'] or 0):.1%} | "
            f"{cell['shrunk_pct']:.1%} | {sum(sized) / len(sized):.1f} |"
        )

    lines += [
        "",
        "## Does the veto add anything the four rules do not?",
        "",
        "The four behavioural guardrails already veto a third of what the room "
        "buys. Both columns are the guarded entry minus the actual entry, in "
        "pool points; the third is what the model's rule is worth on top.",
        "",
        "| threshold | already flagged | four rules | plus the model | added |",
        "|---|---:|---:|---:|---:|",
    ]
    configured = build_rules(config)
    active = [f.rule for f in fit(members, config, configured) if f.qualifies]
    base = sum(
        r.delta for r in run(rows, entry_pickers, policy="substitute", config=config)
    )
    for threshold in VETO_THRESHOLDS:
        rule = veto_rule(threshold)
        matched = [r for r in members if rule.matches(r)]
        overlap = sum(1 for r in matched if any(a.matches(r) for a in active))
        both = sum(
            r.delta
            for r in run(
                rows,
                entry_pickers,
                policy="substitute",
                config=config,
                rules=configured + [rule],
            )
        )
        lines.append(
            f"| {threshold:g}+ | {overlap / len(matched):.0%} | {base:+.0f} | "
            f"{both:+.0f} | {both - base:+.0f} |"
        )

    member_picks = [as_pick(r) for r in members]
    base_points, base_available = majority_points(rows, member_picks)
    with_model, model_available = majority_points(
        rows, member_picks + model_votes(rows)
    )
    lines += [
        "",
        "## The majority entry, with and without the model's vote",
        "",
        "| entry | points | available | share |",
        "|---|---:|---:|---:|",
        f"| members alone | {base_points:.0f} | {base_available:.0f} | "
        f"{base_points / base_available:.1%} |",
        f"| members + gModel | {with_model:.0f} | {model_available:.0f} | "
        f"{with_model / model_available:.1%} |",
        "",
        "The rules and the thresholds were read off the seasons they are scored",
        "on. 2026 is the first honest out-of-sample season.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score gModel against the room")
    parser.add_argument(
        "--preds",
        type=Path,
        default=Path("data/ml_reports/gmodel_walkforward.parquet"),
        help="walk-forward predictions, from `make backtest --save-preds`",
    )
    parser.add_argument("--output", type=Path, help="write the report here")
    args = parser.parse_args()

    from g_nfl.picks.history import load_history

    text = report(
        load_history(drop_team=False), load_predictions(args.preds), set(TEAM_PICKERS)
    )
    if args.output:
        args.output.write_text(text)
        print(f"wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
