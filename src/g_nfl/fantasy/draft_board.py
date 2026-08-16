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

# A tier break is a drop this many times bigger than the drops around it (#78).
# Relative, because ppgar gaps shrink by an order of magnitude down a position's
# curve: one absolute threshold cannot serve both the top and the twentieth
# player. 1.75 measured best over the top 40 — every position lands on tiers of
# at most 8, which is the size that answers "wait or reach".
DEFAULT_TIER_SENSITIVITY = 1.75

# Gaps pooled to judge what "the drops around it" means. Nine is wide enough to
# be stable and narrow enough to track the curve as it flattens.
TIER_WINDOW = 9


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


def attach_tiers(
    board: pl.DataFrame,
    sensitivity: float = DEFAULT_TIER_SENSITIVITY,
    window: int = TIER_WINDOW,
) -> pl.DataFrame:
    """Number tiers per position. A break is a drop that stands out locally.

    A cliff is only a cliff relative to the ground around it. Each gap between
    consecutive players is compared against the median gap among its ``window``
    neighbours, and a new tier starts where it is ``sensitivity`` times larger.

    Two rejected alternatives, both measured on the live board (see
    ``notes/fantasy-draft-board.md``):

    - **A fixed ppg threshold**, which is what this replaces. Gaps shrink by an
      order of magnitude down a position, so one number cannot fit the whole
      curve: 0.75 ppg put 74 of the top-200 WRs in a single tier.
    - **Distribution overlap** from #86, which sounds like the principled answer
      and is not. Adjacent players' outcome ranges overlap so heavily that
      ``P(next player scores more)`` sits between 0.34 and 0.59 across the
      entire top 14 at RB and WR. No threshold separates anything, because
      tiers are about cliffs in expected value, not statistical separation.

    Tiers are per position, since that is how drafters think about waiting, and
    they recompute over whatever board they are handed — so striking drafted
    players (#79) re-tiers the survivors for free.
    """
    ranked = board.sort("ppgar", descending=True)
    gap = (pl.col("ppgar").shift(1) - pl.col("ppgar")).over("position")
    return (
        ranked.with_columns(gap.alias("_gap"))
        .with_columns(
            (
                pl.col("_gap")
                > sensitivity
                * pl.col("_gap")
                .rolling_median(window, center=True, min_samples=3)
                .over("position")
            )
            .fill_null(False)  # noqa: FBT003 — the first player starts a tier, not a break
            .cum_sum()
            .over("position")
            .add(1)
            .alias("tier")
        )
        .drop("_gap")
    )


# What the board can be sorted by, and which direction is "better" (#77).
# PPGAR is the default and the only cross-positionally comparable one: it is
# measured against each position's own replacement level, so a point of RB PPGAR
# and a point of WR PPGAR buy the same thing.
#
# P(top-N at position) was measured and rejected as the default. It correlates
# 0.94 with PPGAR anyway, and where it disagrees it is usually wrong for a
# structural reason: the threshold is per position (top 12 QB against top 36 WR),
# so deep positions clear it more easily and drift up the board. It also
# saturates near 0.5 through the middle rounds, exactly where a board is asked to
# discriminate.
#
# Floor and ceiling stay as sorts because the round-dependent argument holds: an
# early bust cannot be replaced so you pay for the floor, a late bust gets
# dropped so the ceiling is close to free. One ranking statistic cannot say both,
# and a sort selector is the cheap way to let the drafter say which one they are
# buying this round.
SORTS: dict[str, str] = {
    "ppgar": "Value over replacement (default)",
    "vs_next_turn": "Value over your next turn",
    "floor": "Floor (10th percentile)",
    "ceiling": "Ceiling (90th percentile)",
    "vs_ecr": "Disagreement with the room",
}


def sort_board(board: pl.DataFrame, by: str = "ppgar") -> pl.DataFrame:
    """Order the board by one of ``SORTS``, best first.

    ``overall_rank`` keeps its PPGAR meaning whatever the sort, so the column
    stays a stable reference rather than renumbering under the reader.
    """
    if by not in board.columns:
        return board.sort("overall_rank")
    return board.sort(by, descending=True, nulls_last=True)


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
    config: LeagueConfig,
    season: int,
    tier_sensitivity: float = DEFAULT_TIER_SENSITIVITY,
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Full pipeline. Returns the board and the provenance to print alongside it."""
    stat_lines = fetch_espn_projections(season)
    fetched_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    board = build_board(
        score(stat_lines, config), config.teams, config.roster_positions
    )

    ecr, scrape_date = load_ecr()
    board = attach_tiers(board.join(ecr, on="gsis_id", how="left"), tier_sensitivity)
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
    parser.add_argument(
        "--tier-sensitivity",
        type=float,
        default=DEFAULT_TIER_SENSITIVITY,
        help="a tier break is a drop this many times the local median gap",
    )
    parser.add_argument("--top", type=int, default=100, help="rows in the markdown")
    parser.add_argument("--out-dir", type=Path, default=Path("data/fantasy"))
    parser.add_argument("--sort", default="ppgar", choices=sorted(SORTS))
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
    board, provenance = build_draft_board(config, args.season, args.tier_sensitivity)

    if args.outcomes:
        history_seasons = list(range(args.history[0], args.history[1] + 1))
        resid = residuals(build_history(history_seasons, config))
        board = attach_outcomes(board, resid, args.season)

    board = sort_board(board, args.sort)

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
