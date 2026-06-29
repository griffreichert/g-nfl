"""Team-week injury aggregates from the weekly injury report.

Turns the player-level report into one row per team-week with counts
by game-status severity and position group, ready to join the game
matrix on (team, season, week). The injury report for week N is known
before kickoff, so unlike performance stats these features need **no
lag** — but they must be joined on the *game's own* week, not week-1.

Position groups: QB; SKILL (RB/WR/TE/FB); OL (T/G/C); rest = DEF
(specialists K/P/LS folded into DEF — rarely reported, low signal).
"""

import polars as pl

POSITION_GROUPS = {
    "QB": "qb",
    "RB": "skill",
    "WR": "skill",
    "TE": "skill",
    "FB": "skill",
    "T": "ol",
    "G": "ol",
    "C": "ol",
}

# report_status -> severity weight: how likely the player misses the game
STATUS_WEIGHTS = {"Out": 1.0, "Doubtful": 0.75, "Questionable": 0.5}


def team_week_injuries(injuries: pl.DataFrame) -> pl.DataFrame:
    """Aggregate the injury report to team-week injury-burden features.

    Returns one row per (team, season, week) with `inj_<group>_out`
    counts (players ruled Out), `inj_<group>_q` counts (Questionable +
    Doubtful), and `inj_<group>_burden` (severity-weighted sum). Only
    players with a game-status designation count; being listed with
    practice notes but no designation is ignored.
    """
    designated = (
        injuries.with_columns(pl.col("report_status").cast(pl.Utf8))
        .filter(
            (pl.col("game_type") == "REG")
            & pl.col("report_status").is_in(list(STATUS_WEIGHTS))
        )
        .with_columns(
            group=pl.col("position").replace_strict(POSITION_GROUPS, default="def"),
            weight=pl.col("report_status").replace_strict(
                STATUS_WEIGHTS, return_dtype=pl.Float64
            ),
            is_out=pl.col("report_status") == "Out",
        )
    )

    agg = designated.group_by("team", "season", "week", "group").agg(
        out=pl.col("is_out").sum(),
        q=(~pl.col("is_out")).sum(),
        burden=pl.col("weight").sum(),
    )

    wide = agg.pivot(
        on="group",
        index=["team", "season", "week"],
        values=["out", "q", "burden"],
    )
    # pivot names columns like "out_qb"; rename to inj_qb_out and fill
    # groups with no injured players that week with 0
    renames = {}
    for col in wide.columns:
        for metric in ("out", "q", "burden"):
            if col.startswith(f"{metric}_"):
                renames[col] = f"inj_{col.removeprefix(f'{metric}_')}_{metric}"
    wide = wide.rename(renames)

    expected = [
        f"inj_{g}_{m}"
        for g in ("qb", "skill", "ol", "def")
        for m in ("out", "q", "burden")
    ]
    missing = [c for c in expected if c not in wide.columns]
    return (
        wide.with_columns(
            [pl.lit(0.0 if c.endswith("burden") else 0).alias(c) for c in missing]
        )
        .select("team", "season", "week", *expected)
        .fill_null(0)
    )


def add_injuries(matrix: pl.DataFrame, injuries: pl.DataFrame) -> pl.DataFrame:
    """Join home/away team-week injury burden onto the game matrix.

    **No lag** (unlike the performance stats in `matrix`): the injury
    report for a game's week is known pre-kickoff, so we join on the
    game's *own* (season, week). Team-weeks with no designated injuries
    have no row in the aggregate and get 0 after the left join.
    """
    tw = team_week_injuries(injuries).with_columns(
        pl.col("season").cast(matrix.schema["season"]),
        pl.col("week").cast(matrix.schema["week"]),
    )
    inj_cols = [c for c in tw.columns if c.startswith("inj_")]
    away = tw.rename({"team": "away_team", **{c: f"away_{c}" for c in inj_cols}})
    home = tw.rename({"team": "home_team", **{c: f"home_{c}" for c in inj_cols}})
    fill = [f"{side}_{c}" for side in ("away", "home") for c in inj_cols]
    return (
        matrix.join(away, on=["away_team", "season", "week"], how="left")
        .join(home, on=["home_team", "season", "week"], how="left")
        .with_columns(pl.col(fill).fill_null(0))
    )
