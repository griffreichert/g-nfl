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
    board = board.sort("overall_rank").select(BOARD_COLUMNS)

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
    args = parser.parse_args()

    config = PRESETS[args.preset]
    board, provenance = build_draft_board(config, args.season, args.tier_gap)

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
    print(f"\nWrote {csv_path} and {md_path}")


if __name__ == "__main__":
    main()
