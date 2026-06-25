"""Pick-trend analysis over parsed pool picks (#20).

Answers: which teams does the pool pile onto each week, does the
consensus actually cover, and is there a tail/fade edge? ATS analysis
uses the BB + numbered + MNF slots; survivor and underdog slots are
summarized separately. Results come from the sheet's own W/L grading.

Run a season report:

    uv run python -m g_nfl.pool.analysis data/pool/standings_2025.xlsx --season 2025
"""

from __future__ import annotations

import polars as pl

ATS_TYPES = ("regular", "best_bet", "mnf")


def to_df(picks: list[dict]) -> pl.DataFrame:
    """Parsed pick rows -> DataFrame."""
    return pl.DataFrame(picks)


def _ats(df: pl.DataFrame, max_week: int = 18) -> pl.DataFrame:
    """ATS picks for regular-season weeks, with a win/loss flag."""
    return df.filter(
        pl.col("pick_type").is_in(ATS_TYPES), pl.col("week") <= max_week
    ).with_columns(
        win=(pl.col("result") == "W").cast(pl.Int8),
        graded=pl.col("result").is_in(["W", "L"]),
    )


def team_popularity(df: pl.DataFrame, max_week: int = 18) -> pl.DataFrame:
    """Season ATS pick counts and cover rate per team."""
    return (
        _ats(df, max_week)
        .group_by("team_picked")
        .agg(
            picks=pl.len(),
            wins=pl.col("win").sum(),
            graded=pl.col("graded").sum(),
        )
        .with_columns(win_pct=pl.col("wins") / pl.col("graded"))
        .sort("picks", descending=True)
    )


def weekly_consensus(df: pl.DataFrame, max_week: int = 18) -> pl.DataFrame:
    """Most-picked ATS team each week with pick count and result."""
    counts = (
        _ats(df, max_week)
        .group_by("week", "team_picked")
        .agg(picks=pl.len(), wins=pl.col("win").sum(), graded=pl.col("graded").sum())
    )
    return (
        counts.filter(pl.col("picks") == pl.col("picks").max().over("week"))
        .with_columns(win_pct=pl.col("wins") / pl.col("graded"))
        .sort("week")
    )


def popularity_curve(df: pl.DataFrame, max_week: int = 18) -> pl.DataFrame:
    """Cover rate as a function of how many pool members picked the team.

    The tail/fade question in one table: if heavily-picked teams cover
    >52.4% you tail the pool, if they cover <47.6% you fade it.
    """
    counts = (
        _ats(df, max_week)
        .group_by("week", "team_picked")
        .agg(picks=pl.len(), wins=pl.col("win").sum(), graded=pl.col("graded").sum())
    )
    return (
        counts.group_by("picks")
        .agg(
            team_weeks=pl.len(),
            wins=pl.col("wins").sum(),
            graded=pl.col("graded").sum(),
        )
        .with_columns(win_pct=pl.col("wins") / pl.col("graded"))
        .sort("picks", descending=True)
    )


def tail_fade(df: pl.DataFrame, min_picks: int = 6, max_week: int = 18) -> dict:
    """Record of tailing every team picked by >= min_picks members in a week.

    Fading is the mirror image (pushes ignored), so one record answers both.
    """
    counts = (
        _ats(df, max_week)
        .group_by("week", "team_picked")
        .agg(picks=pl.len(), wins=pl.col("win").max(), graded=pl.col("graded").max())
        .filter(pl.col("picks") >= min_picks, pl.col("graded") == 1)
    )
    bets = counts.height
    wins = int(counts["wins"].sum()) if bets else 0
    return {
        "min_picks": min_picks,
        "bets": bets,
        "tail_record": f"{wins}-{bets - wins}",
        "tail_pct": wins / bets if bets else None,
        "fade_pct": (bets - wins) / bets if bets else None,
    }


def picker_records(df: pl.DataFrame, max_week: int = 18) -> pl.DataFrame:
    """ATS record per pool member, plus their most-repeated team."""
    ats = _ats(df, max_week)
    records = (
        ats.group_by("picker")
        .agg(
            picks=pl.len(),
            wins=pl.col("win").sum(),
            graded=pl.col("graded").sum(),
        )
        .with_columns(win_pct=pl.col("wins") / pl.col("graded"))
    )
    favorites = (
        ats.group_by("picker", "team_picked")
        .agg(n=pl.len())
        .filter(pl.col("n") == pl.col("n").max().over("picker"))
        .group_by("picker")
        .agg(
            favorite=pl.col("team_picked").sort().str.join("/"),
            favorite_n=pl.col("n").first(),
        )
    )
    return records.join(favorites, on="picker").sort("win_pct", descending=True)


def survivor_summary(df: pl.DataFrame) -> pl.DataFrame:
    """Survivor picks per week: most popular team and how many remain alive."""
    sd = df.filter(pl.col("pick_type") == "survivor")
    return (
        sd.group_by("week")
        .agg(
            alive=pl.len(),
            top=pl.col("team_picked").mode().sort().first(),
            top_n=pl.col("team_picked")
            .value_counts(sort=True)
            .first()
            .struct.field("count"),
        )
        .sort("week")
    )


def format_report(picks: list[dict], season: int) -> str:
    """Season pick-trend report as printable text."""
    df = to_df(picks)
    lines = [f"# Pool pick trends — {season} season", ""]

    pop = team_popularity(df)
    lines += ["## Most picked teams (ATS, weeks 1-18)"]
    for row in pop.head(8).iter_rows(named=True):
        lines.append(
            f"  {row['team_picked']:4s} {row['picks']:3d} picks, "
            f"covered {row['win_pct']:.0%}"
        )
    lines += ["", "## Least picked"]
    for row in pop.tail(5).iter_rows(named=True):
        lines.append(
            f"  {row['team_picked']:4s} {row['picks']:3d} picks, "
            f"covered {row['win_pct']:.0%}"
        )

    lines += ["", "## Cover rate by pool popularity (picks per team-week)"]
    for row in popularity_curve(df).iter_rows(named=True):
        pct = f"{row['win_pct']:.0%}" if row["graded"] else "— (push/ungraded)"
        lines.append(
            f"  {row['picks']:2d} pickers: {row['team_weeks']:3d} team-weeks, "
            f"covered {pct}"
        )

    for n in (10, 8, 6):
        tf = tail_fade(df, min_picks=n)
        lines.append(
            f"\n## Tail every {n}+ pick consensus: {tf['tail_record']} "
            f"({tf['tail_pct']:.0%} tail / {tf['fade_pct']:.0%} fade)"
            if tf["bets"]
            else f"\n## No team reached {n}+ picks in a week"
        )

    lines += ["", "## Survivor picks by week (alive count, most popular)"]
    for row in survivor_summary(df).iter_rows(named=True):
        lines.append(
            f"  wk {row['week']:2d}: {row['alive']:2d} alive, "
            f"top pick {row['top']} x{row['top_n']}"
        )

    lines += ["", "## Picker ATS records"]
    for row in picker_records(df).iter_rows(named=True):
        lines.append(
            f"  {row['picker']:12s} {row['wins']:3d}-{row['graded'] - row['wins']:<3d}"
            f" ({row['win_pct']:.0%})  favorite: {row['favorite']} x{row['favorite_n']}"
        )

    return "\n".join(lines)


def main() -> None:
    import argparse
    from pathlib import Path

    from g_nfl.pool.parser import parse_workbook

    ap = argparse.ArgumentParser(description="Pool pick trend report")
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--season", type=int, required=True)
    args = ap.parse_args()

    picks = parse_workbook(args.xlsx, args.season)
    print(format_report(picks, args.season))


if __name__ == "__main__":
    main()
