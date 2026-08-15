"""Ranked draft board: ESPN projections -> league scoring -> PPGAR -> tiers (issue #89).

```
fetch_espn_projections()          # 87
  -> score(lines, config)         # 88 -> proj_ppg
  -> build_board(...)             # existing, unchanged
  -> attach_ecr() -> attach_tiers()
```

Run: ``uv run python -m g_nfl.fantasy.draft_board --preset ppr_12``
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import nflreadpy
import polars as pl

from g_nfl.fantasy.outcomes import attach_outcomes, build_history, residuals
from g_nfl.fantasy.projections.board import build_board, to_markdown
from g_nfl.fantasy.scoring import PRESETS, LeagueConfig, score
from g_nfl.fantasy.sources.espn import fetch_espn_projections

BOARD_COLUMNS = [
    "overall_rank",
    "player_name",
    "position",
    "pos_rank",
    "team",
    "tier",
    "proj_ppg",
    "ppgar",
    "ecr",
    "sd",
    "vs_ecr",
]

# A tier break is a ppgar drop bigger than this, in points per game. #78 settles
# the principled answer; this is a knob with a defensible default until then.
DEFAULT_TIER_GAP = 0.75


def load_ecr() -> tuple[pl.DataFrame, str]:
    """FantasyPros redraft-overall ECR keyed on ``gsis_id``, plus its scrape date.

    PPR-only: FantasyPros publishes no half-PPR or TE-premium redraft page, so
    the number is worth less the further a league sits from full PPR.
    """
    rankings = nflreadpy.load_ff_rankings().filter(
        pl.col("page_type") == "redraft-overall"
    )
    scrape_date = rankings["scrape_date"].max()

    ids = (
        nflreadpy.load_ff_playerids()
        .select("fantasypros_id", "gsis_id")
        .drop_nulls(["fantasypros_id", "gsis_id"])
        .unique("fantasypros_id")
    )
    ecr = (
        rankings.select(
            pl.col("id").cast(pl.Utf8).alias("fantasypros_id"),
            pl.col("ecr"),
            pl.col("sd"),
        )
        .join(
            ids.with_columns(pl.col("fantasypros_id").cast(pl.Utf8)),
            on="fantasypros_id",
        )
        .select("gsis_id", "ecr", "sd")
        .unique("gsis_id")
    )
    return ecr, str(scrape_date)


def attach_tiers(board: pl.DataFrame, gap: float = DEFAULT_TIER_GAP) -> pl.DataFrame:
    """Number tiers per position: a new tier starts where ppgar drops by > ``gap``."""
    return board.sort("ppgar", descending=True).with_columns(
        (
            (pl.col("ppgar").shift(1).over("position") - pl.col("ppgar")).fill_null(0.0)
            > gap
        )
        .cum_sum()
        .over("position")
        .add(1)
        .alias("tier")
    )


def attach_vs_ecr(board: pl.DataFrame) -> pl.DataFrame:
    """``ecr - overall_rank``: who this league's scoring likes more than the room.

    Positive means we rank the player higher than the consensus does, so he is
    someone to wait on rather than reach for. Units are ranks over two different
    populations — ECR is expert opinion under generic PPR, ``overall_rank`` is
    PPGAR under *your* scoring — so part of every delta is the league config
    doing its job. A very large one usually means a projection problem rather
    than an edge, which makes this the column that tells you where to look.
    """
    return board.with_columns((pl.col("ecr") - pl.col("overall_rank")).alias("vs_ecr"))


def snake_picks(slot: int, teams: int, rounds: int) -> list[int]:
    """Overall pick numbers belonging to ``slot`` in a snake draft, 1-indexed."""
    return [
        (rnd - 1) * teams + (slot if rnd % 2 else teams - slot + 1)
        for rnd in range(1, rounds + 1)
    ]


def picks_until_next_turn(slot: int, teams: int, rnd: int) -> int:
    """Other teams' picks between your pick in ``rnd`` and your pick in ``rnd + 1``.

    Snake, so this alternates: an early slot waits a long time after round 1 and
    barely any time after round 2. That asymmetry is the reason the number is
    worth showing at all.
    """
    picks = snake_picks(slot, teams, rnd + 1)
    return picks[rnd] - picks[rnd - 1] - 1


def _best_available(board: pl.DataFrame) -> pl.DataFrame:
    """Top remaining player per position, by board rank."""
    return board.sort("overall_rank").group_by("position", maintain_order=True).first()


def next_turn_outlook(board: pl.DataFrame, picks_between: int) -> pl.DataFrame:
    """What the top of each position looks like now, and at your next turn.

    Survival model: the next ``picks_between`` picks take the next
    ``picks_between`` players *in board order*. That is a proxy, and a
    self-flattering one, since it assumes the room drafts off this board. #92(c)
    replaces it with ADP, where ``minPick``/``maxPick`` give a real spread.
    """
    now = _best_available(board).select(
        "position",
        pl.col("player_name").alias("best_now"),
        pl.col("ppgar").alias("ppgar_now"),
    )
    later = _best_available(board.sort("overall_rank").slice(picks_between)).select(
        "position",
        pl.col("player_name").alias("best_next_turn"),
        pl.col("ppgar").alias("ppgar_next_turn"),
    )
    return (
        now.join(later, on="position", how="left")
        .with_columns(
            (pl.col("ppgar_now") - pl.col("ppgar_next_turn")).alias("cost_of_waiting")
        )
        .sort("cost_of_waiting", descending=True)
    )


def attach_next_turn_value(
    board: pl.DataFrame, picks_between: int
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Add ``vs_next_turn``: ppgar over the best of that position at your next turn.

    PPGAR measures a player against a replacement he shares with the whole
    season. ``vs_next_turn`` measures him against the alternative you actually
    face, which is the one the draft asks about.
    """
    outlook = next_turn_outlook(board, picks_between)
    scored = board.join(
        outlook.select("position", "ppgar_next_turn"), on="position", how="left"
    ).with_columns((pl.col("ppgar") - pl.col("ppgar_next_turn")).alias("vs_next_turn"))
    return scored.drop("ppgar_next_turn"), outlook


def build_draft_board(
    config: LeagueConfig, season: int, tier_gap: float = DEFAULT_TIER_GAP
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Full pipeline. Returns the board and the provenance to print alongside it."""
    stat_lines = fetch_espn_projections(season)
    fetched_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    board = build_board(
        score(stat_lines, config), config.teams, config.roster_positions
    )

    ecr, scrape_date = load_ecr()
    board = attach_tiers(board.join(ecr, on="gsis_id", how="left"), tier_gap)
    board = attach_vs_ecr(board)
    # gsis_id rides along: it is the join key for #86's outcome percentiles, and
    # ``to_markdown`` picks its own columns so it never reaches the table.
    board = board.sort("overall_rank").select(["gsis_id", *BOARD_COLUMNS])

    provenance = {
        "espn_fetched": fetched_at,
        "ecr_scraped": scrape_date,
        "ecr_matched": f"{board['ecr'].is_not_null().mean():.1%}",
        "players": str(board.height),
    }
    return board, provenance


def _header(
    preset: str, config: LeagueConfig, season: int, provenance: dict[str, str]
) -> str:
    s = config.scoring
    return "\n".join(
        [
            f"# {season} draft board — {preset}",
            "",
            f"- **League**: {config.teams} teams, "
            f"{'/'.join(config.roster_positions)}, {config.bench} bench",
            f"- **Scoring**: {s.reception} PPR"
            + (f" (+{s.te_premium} TE)" if s.te_premium else "")
            + f", {s.rec_yd}/rec yd, {s.rush_yd}/rush yd, {s.pass_yd}/pass yd, "
            f"{s.td} TD, {s.pass_td} pass TD, {s.interception} INT, "
            f"{s.fumble_lost} fumble",
            f"- **ESPN projections fetched**: {provenance['espn_fetched']}",
            f"- **FantasyPros ECR scraped**: {provenance['ecr_scraped']} "
            f"({provenance['ecr_matched']} of players matched). "
            "ECR is expert opinion, not ADP, and the redraft page is PPR-only.",
            f"- **Players**: {provenance['players']}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", default="ppr_12", choices=sorted(PRESETS))
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--tier-gap", type=float, default=DEFAULT_TIER_GAP)
    parser.add_argument("--top", type=int, default=100, help="rows in the markdown")
    parser.add_argument("--out-dir", type=Path, default=Path("data/fantasy"))
    parser.add_argument("--slot", type=int, help="your draft slot, 1-indexed")
    parser.add_argument("--round", type=int, default=1, help="round you are picking in")
    parser.add_argument(
        "--outcomes",
        action="store_true",
        help="add floor/ceiling from historical residuals (#86, slow: fetches history)",
    )
    parser.add_argument("--history", type=int, nargs=2, default=[2019, 2025])
    args = parser.parse_args()

    config = PRESETS[args.preset]
    board, provenance = build_draft_board(config, args.season, args.tier_gap)

    if args.outcomes:
        history_seasons = list(range(args.history[0], args.history[1] + 1))
        resid = residuals(build_history(history_seasons, config))
        board = attach_outcomes(board, resid, args.season)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"board_{args.season}_{args.preset}"
    csv_path = args.out_dir / f"{stem}.csv"
    md_path = args.out_dir / f"{stem}.md"

    board.write_csv(csv_path)
    header = _header(args.preset, config, args.season, provenance)
    md_path.write_text(f"{header}\n\n{to_markdown(board, top=args.top)}\n")

    print(header)
    print()
    print(to_markdown(board, top=30))

    if args.slot:
        gap = picks_until_next_turn(args.slot, config.teams, args.round)
        picks = snake_picks(args.slot, config.teams, args.round + 1)
        print(
            f"\nSlot {args.slot}, round {args.round}: pick {picks[args.round - 1]}, "
            f"then pick {picks[args.round]} — {gap} picks in between."
        )
        print(next_turn_outlook(board, gap))

    print(f"\nWrote {csv_path} and {md_path}")


if __name__ == "__main__":
    main()
