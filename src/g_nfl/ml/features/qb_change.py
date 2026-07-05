"""L4 QB-change delta: the injury report as a pre-kickoff trigger.

Lever 1 of notes/sharpness-player-availability.md (issue #41). Depth
charts were rejected (no timestamp pre-2025, confirmed stale in at
least one case); the weekly injury report has a real ``date_modified``
and is known pre-kickoff, so it drives the trigger.

For each team-game:
1. **Usual starter** = the actual starter (most dropbacks, `qb.starters`)
   of that team's most recent *prior* game — strictly lagged, no season
   reset (mirrors `qb.py`'s career-spanning convention).
2. **Trigger** = the usual starter is listed ``Out``/``Doubtful`` on the
   injury report for that (season, week, team). Own-week join, no lag —
   the report is known pre-kickoff (L3 precedent, `injuries.py`).
   ``Questionable`` does not trigger in v1.
3. **Projected starter when triggered** = the team's backup: the QB with
   the second-most season-to-date dropbacks entering that week (lagged).
   No such QB (cold) -> a replacement-level constant: the 25th
   percentile of that week's leaguewide (lagged) starter EWMA. A
   documented approximation, not a precise backup-quality estimate.
4. ``qb_downgrade`` = usual starter's lagged personal EWMA minus the
   projected starter's (0.0 when not triggered, the common case; also
   0.0 if the usual starter's own EWMA is null -- no information to act
   on, never invented). ``qb_out`` is the 0/1 trigger flag.

Both QBs' EWMA values are looked up **as of the target game's date** via
an as-of join against their own chronological history (`qb.py`'s
`qb_game_history`, already lagged one game) -- this covers a QB who
plays in the exact target game (his own already-lagged row) and one who
doesn't (falls back to his last known appearance, anywhere).

Off by default (see `build_features`'s ``qb_change`` param, which -- like
``snaps`` -- takes the raw injuries DataFrame itself as the toggle).
"""

import polars as pl

from g_nfl.ml.features.qb import QB_HALF_LIFE, _dropbacks, qb_game_history, starters

TRIGGER_STATUSES = {"Out", "Doubtful"}
REPLACEMENT_PCTL = 0.25

QB_CHANGE_COLS = ["qb_downgrade", "qb_out"]


def _team_game_dates(pbp: pl.DataFrame) -> pl.DataFrame:
    return pbp.select("game_id", "posteam", "season", "week", "game_date").unique()


def _usual_starters(pbp: pl.DataFrame) -> pl.DataFrame:
    """Each team-game's usual starter = the team's actual starter in its
    most recent prior game (shift 1, no season reset)."""
    tg = starters(pbp).join(
        _team_game_dates(pbp), on=["game_id", "posteam"], how="left"
    )
    return (
        tg.sort("posteam", "game_date")
        .with_columns(usual_starter=pl.col("passer_player_id").shift(1).over("posteam"))
        .select("game_id", "posteam", "season", "week", "game_date", "usual_starter")
    )


def _backup_starters(pbp: pl.DataFrame) -> pl.DataFrame:
    """Each (team, season, week)'s backup = the QB with the 2nd-most
    season-to-date dropbacks entering that week (lagged). Teams with
    fewer than 2 QBs with any prior dropbacks that season get no row
    (cold -> replacement-level fallback downstream)."""
    # dropbacks thrown by any passer, per team-week (not just the starter --
    # a backup's mop-up/spot-start snaps are exactly the signal we rank on)
    db_by_qb = (
        _dropbacks(pbp)
        .group_by("posteam", "season", "week", "passer_player_id")
        .agg(n_db=pl.len())
    )
    weeks = db_by_qb.select("posteam", "season", "week").unique()
    passers = db_by_qb.select("posteam", "season", "passer_player_id").unique()
    grid = weeks.join(passers, on=["posteam", "season"], how="left")
    entering = (
        grid.join(
            db_by_qb, on=["posteam", "season", "week", "passer_player_id"], how="left"
        )
        .with_columns(pl.col("n_db").fill_null(0))
        .sort("posteam", "passer_player_id", "season", "week")
        .with_columns(
            cum=pl.col("n_db").cum_sum().over(["posteam", "passer_player_id", "season"])
        )
        .with_columns(
            entering=pl.col("cum")
            .shift(1)
            .over(["posteam", "passer_player_id", "season"])
            .fill_null(0)
        )
    )
    ranked = entering.filter(pl.col("entering") > 0).with_columns(
        rank=pl.col("entering")
        .rank("ordinal", descending=True)
        .over(["posteam", "season", "week"])
    )
    return ranked.filter(pl.col("rank") == 2).select(
        "posteam", "season", "week", backup_starter="passer_player_id"
    )


def _ewm_history(pbp: pl.DataFrame, half_life: float) -> pl.DataFrame:
    """Each QB's own lagged personal EWMA, dated, for the as-of lookup."""
    return (
        qb_game_history(pbp, half_life)
        .select("passer_player_id", "game_id", "qb_epa_ewm")
        .join(pbp.select("game_id", "game_date").unique(), on="game_id", how="left")
        .select("passer_player_id", "game_date", "qb_epa_ewm")
    )


def _lookup_ewm(
    games: pl.DataFrame, id_col: str, ewm_dated: pl.DataFrame
) -> pl.DataFrame:
    """As-of attach ``<id_col>_ewm``: the named QB's most recent lagged
    personal EWMA with `game_date` <= the target game's date. Safe even
    when he plays in the exact target game -- that row is itself already
    lagged one game (see `qb.qb_game_history`) -- and falls back to his
    last known appearance anywhere when he doesn't."""
    known = (
        games.filter(pl.col(id_col).is_not_null())
        .select("game_id", "posteam", "game_date", id_col)
        .sort(id_col, "game_date")
    )
    joined = known.join_asof(
        ewm_dated.sort("passer_player_id", "game_date"),
        left_on="game_date",
        right_on="game_date",
        by_left=id_col,
        by_right="passer_player_id",
        strategy="backward",
    ).select("game_id", "posteam", pl.col("qb_epa_ewm").alias(f"{id_col}_ewm"))
    return games.join(joined, on=["game_id", "posteam"], how="left")


def team_week_qb_change(
    pbp: pl.DataFrame, injuries: pl.DataFrame, half_life: float = QB_HALF_LIFE
) -> pl.DataFrame:
    """Per (game_id, posteam): ``qb_downgrade`` + ``qb_out``."""
    trig = (
        injuries.filter(
            (pl.col("game_type") == "REG")
            & pl.col("report_status").is_in(list(TRIGGER_STATUSES))
        )
        # nflreadpy's older-season injury pulls carry season/week as
        # Float64 (nulls upcast the column); match pbp's dtypes so the
        # trigger join doesn't fail on a type mismatch (same defensive
        # cast as injuries.add_injuries).
        .with_columns(
            pl.col("season").cast(pbp.schema["season"]),
            pl.col("week").cast(pbp.schema["week"]),
        )
        .select(
            "season",
            "week",
            pl.col("team").alias("posteam"),
            pl.col("gsis_id").alias("usual_starter"),
        )
        .unique()
        .with_columns(triggered=pl.lit(True))
    )

    games = (
        _usual_starters(pbp)
        .join(_backup_starters(pbp), on=["posteam", "season", "week"], how="left")
        .join(trig, on=["season", "week", "posteam", "usual_starter"], how="left")
        .with_columns(pl.col("triggered").fill_null(False))
    )

    ewm_dated = _ewm_history(pbp, half_life)
    games = _lookup_ewm(games, "usual_starter", ewm_dated)
    games = _lookup_ewm(games, "backup_starter", ewm_dated)

    replacement = games.group_by("season", "week").agg(
        replacement_ewm=pl.col("usual_starter_ewm").quantile(REPLACEMENT_PCTL)
    )
    games = games.join(replacement, on=["season", "week"], how="left")

    return games.with_columns(
        qb_downgrade=pl.when(
            pl.col("triggered") & pl.col("usual_starter_ewm").is_not_null()
        )
        .then(
            pl.col("usual_starter_ewm")
            - pl.coalesce(["backup_starter_ewm", "replacement_ewm"])
        )
        .otherwise(0.0),
        qb_out=pl.col("triggered").cast(pl.Int8),
    ).select("game_id", "posteam", *QB_CHANGE_COLS)


def apply_qb_adjustment(preds: pl.DataFrame, k: float) -> pl.DataFrame:
    """Explicit additive QB-change correction on top of the model's
    prediction (diagnostic: `scratch/qb_change_additive.py`, #41).

    XGBoost ignores ``home/away_qb_downgrade`` (rare-nonzero columns), but
    the signal is real: shifting the predicted home margin down when the
    home team's starter is downgraded (and up when the away team's is)
    closes the model-vs-market sharpness gap in QB-change games. Nulls in
    either downgrade column are treated as 0 (no trigger this game).
    """
    return preds.with_columns(
        pred=pl.col("pred")
        - k * pl.col("home_qb_downgrade").fill_null(0.0)
        + k * pl.col("away_qb_downgrade").fill_null(0.0)
    )


def add_qb_change(
    matrix: pl.DataFrame,
    pbp: pl.DataFrame,
    injuries: pl.DataFrame,
    half_life: float = QB_HALF_LIFE,
) -> pl.DataFrame:
    """Attach home/away ``qb_downgrade``/``qb_out`` to the game matrix."""
    tg = team_week_qb_change(pbp, injuries, half_life)
    away = tg.rename(
        {"posteam": "away_team", **{c: f"away_{c}" for c in QB_CHANGE_COLS}}
    )
    home = tg.rename(
        {"posteam": "home_team", **{c: f"home_{c}" for c in QB_CHANGE_COLS}}
    )
    fill = [f"{side}_{c}" for side in ("away", "home") for c in QB_CHANGE_COLS]
    return (
        matrix.join(away, on=["game_id", "away_team"], how="left")
        .join(home, on=["game_id", "home_team"], how="left")
        .with_columns(pl.col(fill).fill_null(0.0))
    )
