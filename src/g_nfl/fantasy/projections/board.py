"""Per-game points-above-replacement (PPGAR) draft board (issue #31).

Takes #30 season projections and a league's starting-lineup config, derives a
replacement-level per-game baseline per position, and ranks every player by
``ppgar = proj_ppg - replacement_ppg(position)`` so positions are comparable.

Per-game (not season-total) on purpose: the #30 backtest showed a large positive
level bias from the flat 17-game denominator. PPGAR compares rate to rate, so
games-played cancels on both player and baseline.

Replacement baseline = the best *non-starting* player at each position, found by a
greedy leaguewide lineup fill: dedicated slots first, then each FLEX / SUPER_FLEX
slot takes the best eligible player still on the board. The first player who
doesn't make any starting lineup sets that position's replacement level.
"""

from __future__ import annotations

from collections import Counter

import polars as pl

from g_nfl.sleeper.client import SleeperClient

# Positions we project + rank. K/DEF have no #30 projection -> excluded.
BOARD_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

# Flex slot name -> positions eligible to fill it. Covers Sleeper's common flex
# labels; unknown slot names (K, DEF, BN, IR, taxi, dedicated) are ignored.
FLEX_ELIGIBILITY: dict[str, frozenset[str]] = {
    "FLEX": frozenset({"RB", "WR", "TE"}),
    "WRRB_FLEX": frozenset({"RB", "WR"}),
    "REC_FLEX": frozenset({"WR", "TE"}),
    "SUPER_FLEX": frozenset({"QB", "RB", "WR", "TE"}),
}


def replacement_baselines(
    proj: pl.DataFrame, teams: int, roster_positions: list[str]
) -> dict[str, float]:
    """Per-position replacement-level ``proj_ppg`` via greedy leaguewide fill.

    ``proj`` needs ``position`` + ``proj_ppg`` (the #30 output). ``roster_positions``
    is Sleeper's per-team starting-slot list (incl. BN/K/DEF, which are ignored).
    Returns ``{pos: replacement_ppg}`` — the ppg of the first non-startable player.
    """
    slots = Counter(roster_positions)

    # Per-position pools: proj_ppg sorted best-first.
    pools: dict[str, list[float]] = {
        pos: proj.filter(pl.col("position") == pos)
        .sort("proj_ppg", descending=True)["proj_ppg"]
        .to_list()
        for pos in BOARD_POSITIONS
    }
    used: dict[str, int] = {pos: 0 for pos in BOARD_POSITIONS}

    # Dedicated slots: teams * slot count off the top of each pool.
    for pos in BOARD_POSITIONS:
        used[pos] = min(slots.get(pos, 0) * teams, len(pools[pos]))

    # Flex slots: each instance takes the best eligible player still on the board.
    flex_instances = [
        ftype
        for slot, n in slots.items()
        if slot in FLEX_ELIGIBILITY
        for ftype in [slot] * (n * teams)
    ]
    for ftype in flex_instances:
        elig = FLEX_ELIGIBILITY[ftype]
        best_pos, best_val = None, float("-inf")
        for pos in elig:
            if used[pos] < len(pools[pos]) and pools[pos][used[pos]] > best_val:
                best_pos, best_val = pos, pools[pos][used[pos]]
        if best_pos is not None:
            used[best_pos] += 1

    # Replacement = first non-starter; clamp to last available if pool exhausted.
    return {
        pos: pools[pos][min(used[pos], len(pools[pos]) - 1)]
        for pos in BOARD_POSITIONS
        if pools[pos]
    }


def build_board(
    proj: pl.DataFrame, teams: int, roster_positions: list[str]
) -> pl.DataFrame:
    """Attach replacement baselines + PPGAR, rank across positions.

    Returns ``proj`` (BOARD_POSITIONS only) plus ``replacement_ppg``, ``ppgar``,
    ``overall_rank`` (by ppgar desc), and ``pos_rank``; sorted by ppgar.
    """
    baselines = replacement_baselines(proj, teams, roster_positions)
    repl = pl.DataFrame(
        {"position": list(baselines), "replacement_ppg": list(baselines.values())}
    )
    return (
        proj.filter(pl.col("position").is_in(BOARD_POSITIONS))
        .join(repl, on="position", how="inner")
        .with_columns((pl.col("proj_ppg") - pl.col("replacement_ppg")).alias("ppgar"))
        .sort("ppgar", descending=True)
        .with_columns(
            pl.int_range(1, pl.len() + 1).alias("overall_rank"),
            pl.col("ppgar")
            .rank("ordinal", descending=True)
            .over("position")
            .alias("pos_rank"),
        )
    )


def board_for_league(
    proj: pl.DataFrame, league_id: str, client: SleeperClient | None = None
) -> pl.DataFrame:
    """Build a board from a live Sleeper league's size + starting lineup."""
    client = client or SleeperClient()
    lg = client.league(league_id)
    return build_board(proj, lg["total_rosters"], lg["roster_positions"])


def attach_efficiency_rates(board: pl.DataFrame, rates: pl.DataFrame) -> pl.DataFrame:
    """Left-join WR/TE diagnostic efficiency rates (tprr/yprr/fdrr) onto a
    board for eyeballing; QB/RB rows get nulls. Diagnostic only — does not
    touch ppgar/rank (issue #34: the z-score ppg adjustment backtested
    mixed/negative, see ``efficiency.py`` module docstring).
    """
    return board.join(rates, on="player_id", how="left")


def to_markdown(board: pl.DataFrame, top: int = 60) -> str:
    """Render the top-``top`` rows as a markdown table.

    Includes ``tier``/``ecr``/``sd`` (draft board) and ``tprr``/``yprr``/``fdrr``
    (see ``attach_efficiency_rates``) if present. ``last_team`` is #30's column
    name for the team; the #87 stat-line schema calls it ``team``.
    """
    cols = ["overall_rank", "player_name", "position", "pos_rank"]
    cols += [c for c in ("last_team", "team", "tier") if c in board.columns]
    cols += ["proj_ppg", "ppgar"]
    cols += [
        c
        for c in ("ecr", "sd", "floor", "ceiling", "tprr", "yprr", "fdrr")
        if c in board.columns
    ]
    rows = board.head(top).select(cols).iter_rows()
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"

    def _fmt(c: object) -> str:
        if c is None:
            return "-"
        if isinstance(c, float):
            return f"{c:.2f}"
        return str(c)

    body = "\n".join("| " + " | ".join(_fmt(c) for c in r) + " |" for r in rows)
    return f"{head}\n{sep}\n{body}"


if __name__ == "__main__":
    from pathlib import Path

    from g_nfl.fantasy.projections.efficiency import blend_efficiency_rates
    from g_nfl.fantasy.projections.season import project_season
    from g_nfl.sleeper.client import KNOWN_LEAGUES

    TARGET = 2025
    SEASONS = [2022, 2023, 2024]
    proj = project_season(SEASONS, TARGET, scoring="half")

    client = SleeperClient()
    lid = KNOWN_LEAGUES["dudes_rock"]
    lg = client.league(lid)
    print(f"League {lg['name']}: {lg['total_rosters']} teams")
    print(
        "Baselines (half-PPR ppg):",
        replacement_baselines(proj, lg["total_rosters"], lg["roster_positions"]),
    )

    board = build_board(proj, lg["total_rosters"], lg["roster_positions"])
    rates = blend_efficiency_rates(SEASONS, TARGET)
    board = attach_efficiency_rates(board, rates)
    md = to_markdown(board, top=50)
    print("\n" + md)

    out = Path("data") / "fantasy" / f"board_{TARGET}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# PPGAR board {TARGET} — {lg['name']}\n\n{md}\n")
    print(f"\nWrote {out}")
