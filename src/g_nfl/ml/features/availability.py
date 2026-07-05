"""Lever 2 of #39: availability-weighted unit value lost.

Upgrade of the rejected L3 injury *count* (`injuries.py`): weight WHO is
listed on the injury report by how much they actually play. Per
(team, season, week, unit) — OL / skill / front-7 / secondary, **QB
excluded** (lever 1 owns it, `qb_change.py`) — the feature is the
expected snap-value lost to injury:

    expected_loss = sum over that unit's reported players of
                    (1 - p_play) * lagged_season_to_date_snap_share

Player value proxy = lagged mean snap-share (`offense_pct` for OL/skill,
`defense_pct` for front-7/secondary) from `load_snap_counts`, strictly
one game behind (mirrors `qb.py`/`continuity.py`'s lag convention); a
player's first game of a season falls back to his prior-season mean
(if that season is loaded), else 0 — never a leak, never invented.

Availability comes from the weekly injury report (`load_injuries`),
own-week join, no lag: the report is known pre-kickoff (L3 precedent,
`injuries.py`). ``report_status`` -> p_play: Out=0.0, Doubtful=0.2,
Questionable=0.7, no report = not on the table at all (implicitly 1.0,
contributes nothing).

Injuries key players by ``gsis_id``; snap counts key by
``pfr_player_id``. Crosswalked via `nflreadpy.load_players()`'s
``gsis_id``/``pfr_id`` columns (~99.9% match rate on designated,
non-QB injury rows over the tune seasons -- see #39 recon). Rows that
don't cross-walk, or whose player never appears in snap counts (no
unit, no lagged share to draw on), are dropped -- a documented
approximation for a small tail, not invented data.

Off by default (see `build_features`'s ``availability`` param, which --
like ``qb_change`` -- needs the raw ``snaps``/``injuries``/``players``
frames threaded in). Adjustment-shaped like lever 1: rides the matrix
for a future additive correction, excluded from tree training features
(`registry.ADJUSTMENT_COLS`) -- not yet applied (#39 diagnostic first).
"""

import polars as pl

UNIT_POSITIONS = {
    "ol": {"T", "G", "C"},
    "skill": {"RB", "WR", "TE", "FB"},
    "front7": {"DE", "DT", "NT", "LB"},
    "sec": {"CB", "S", "FS", "SS", "DB"},
}
UNIT_PCT_COL = {
    "ol": "offense_pct",
    "skill": "offense_pct",
    "front7": "defense_pct",
    "sec": "defense_pct",
}
UNIT_TO_COL = {u: f"avail_loss_{u}" for u in UNIT_POSITIONS}
AVAIL_COLS = list(UNIT_TO_COL.values())

# report_status -> probability the player actually plays
P_PLAY = {"Out": 0.0, "Doubtful": 0.2, "Questionable": 0.7}


def _player_unit_snaps(snaps: pl.DataFrame) -> pl.DataFrame:
    """Each unit-eligible player-game's snap share (own unit's pct col)."""
    frames = [
        snaps.filter(
            (pl.col("game_type") == "REG") & pl.col("position").is_in(list(positions))
        ).select(
            "pfr_player_id",
            "team",
            "season",
            "week",
            pl.col(UNIT_PCT_COL[unit]).fill_null(0.0).alias("share"),
            unit=pl.lit(unit),
        )
        for unit, positions in UNIT_POSITIONS.items()
    ]
    return pl.concat(frames, how="vertical_relaxed")


def _lagged_player_value(player_snaps: pl.DataFrame) -> pl.DataFrame:
    """Each player-week's lagged season-to-date mean snap share.

    Expanding mean shifted one game within the season (no current-game
    leak, same pattern as `continuity.ol_continuity`); a player's first
    game of a season falls back to his prior-season full mean when that
    season is loaded, else 0 (never invented).
    """
    df = player_snaps.sort("pfr_player_id", "season", "week").with_columns(
        _cs=pl.col("share").cum_sum().over(["pfr_player_id", "season"]),
        _cn=pl.col("share").cum_count().over(["pfr_player_id", "season"]),
    )
    df = df.with_columns(
        lagged=(pl.col("_cs") / pl.col("_cn"))
        .shift(1)
        .over(["pfr_player_id", "season"])
    )
    prior_season = (
        df.group_by("pfr_player_id", "season")
        .agg(prior_season_mean=pl.col("share").mean())
        .with_columns(season=pl.col("season") + 1)
    )
    df = df.join(prior_season, on=["pfr_player_id", "season"], how="left")
    return df.select(
        "pfr_player_id",
        "team",
        "season",
        "week",
        "unit",
        lagged_share=pl.coalesce(["lagged", "prior_season_mean"]).fill_null(0.0),
    )


def team_week_availability(
    snaps: pl.DataFrame, injuries: pl.DataFrame, players: pl.DataFrame
) -> pl.DataFrame:
    """Per (team, season, week): expected snap-value lost by unit."""
    lagged = _lagged_player_value(_player_unit_snaps(snaps))
    xwalk = players.select("gsis_id", "pfr_id").filter(
        pl.col("gsis_id").is_not_null() & pl.col("pfr_id").is_not_null()
    )

    reported = (
        injuries.filter(
            (pl.col("game_type") == "REG")
            & (pl.col("position") != "QB")
            & pl.col("report_status").cast(pl.Utf8).is_in(list(P_PLAY))
        )
        # nflreadpy's older-season injury pulls carry season/week as
        # Float64 (same defensive cast as qb_change/injuries.add_injuries).
        .with_columns(
            pl.col("season").cast(snaps.schema["season"]),
            pl.col("week").cast(snaps.schema["week"]),
            p_play=pl.col("report_status").replace_strict(
                P_PLAY, return_dtype=pl.Float64
            ),
        )
        .join(xwalk, on="gsis_id", how="left")
        .filter(pl.col("pfr_id").is_not_null())
        .select(
            "season",
            "week",
            "team",
            pl.col("pfr_id").alias("pfr_player_id"),
            "p_play",
        )
    )

    joined = reported.join(
        lagged, on=["pfr_player_id", "team", "season", "week"], how="inner"
    ).with_columns(loss=(1 - pl.col("p_play")) * pl.col("lagged_share"))

    agg = joined.group_by("team", "season", "week", "unit").agg(
        expected_loss=pl.col("loss").sum()
    )
    wide = agg.pivot(
        on="unit", index=["team", "season", "week"], values="expected_loss"
    )
    missing = [u for u in UNIT_POSITIONS if u not in wide.columns]
    wide = wide.with_columns([pl.lit(0.0).alias(u) for u in missing])
    return (
        wide.rename(UNIT_TO_COL)
        .select("team", "season", "week", *AVAIL_COLS)
        .fill_null(0.0)
    )


def add_availability(
    matrix: pl.DataFrame,
    snaps: pl.DataFrame,
    injuries: pl.DataFrame,
    players: pl.DataFrame,
) -> pl.DataFrame:
    """Join home/away unit expected-loss onto the game matrix.

    **No lag** on the injury side (own game-week, pre-kickoff-known,
    L3 precedent); the snap-share player value itself is lagged inside
    `team_week_availability`. Team-weeks with nothing reported get 0
    after the left join.
    """
    tw = team_week_availability(snaps, injuries, players).with_columns(
        pl.col("season").cast(matrix.schema["season"]),
        pl.col("week").cast(matrix.schema["week"]),
    )
    away = tw.rename({"team": "away_team", **{c: f"away_{c}" for c in AVAIL_COLS}})
    home = tw.rename({"team": "home_team", **{c: f"home_{c}" for c in AVAIL_COLS}})
    fill = [f"{side}_{c}" for side in ("away", "home") for c in AVAIL_COLS]
    return (
        matrix.join(away, on=["away_team", "season", "week"], how="left")
        .join(home, on=["home_team", "season", "week"], how="left")
        .with_columns(pl.col(fill).fill_null(0.0))
    )
