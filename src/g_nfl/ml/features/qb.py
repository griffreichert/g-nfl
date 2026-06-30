"""L4 QB player-grain features: starting-QB quality keyed on the player.

Each team-game gets its *starting* QB's recency-weighted EPA/CPOE plus
career volume, computed over the QB's own chronological dropback stream
and **lagged one game** so the current game is never in his estimate.

The starter's *identity* is taken from the current game (the QB with the
most dropbacks) — genuinely known pre-kickoff at deploy time, so that
"leak" is acceptable — but his *metrics* are strictly lagged. The EWMA is
career-spanning and keyed on ``passer_player_id``, so the signal follows
the QB across team moves and starts thin (null EWMA, 0 volume) for rookies.

Needs pbp with enough prior-season lookback to warm the EWMA — see
``backtest``, which loads 3 seasons before the earliest eval season. Off
by default (see ``build_features`` ``qb_ctx``).
"""

import polars as pl

# EWMA half-life in dropbacks (~half a season of attempts). Starting knob;
# tuned in the A/B sweep, not hand-picked.
QB_HALF_LIFE = 300

QB_COLS = ["qb_epa_ewm", "qb_cpoe_ewm", "qb_dropbacks", "qb_games"]


def _dropbacks(pbp: pl.DataFrame) -> pl.DataFrame:
    """Regular-season QB dropback plays with a named passer."""
    return pbp.filter(
        (pl.col("season_type") == "REG")
        & (pl.col("qb_dropback") == 1)
        & pl.col("passer_player_id").is_not_null()
    )


def qb_game_history(pbp: pl.DataFrame, half_life: float = QB_HALF_LIFE) -> pl.DataFrame:
    """Per (qb, game) lagged EWMA + cumulative volume, keyed on the player.

    Builds a per-dropback EWMA over each QB's chronological play stream,
    reduces to the end-of-game value per (qb, game), then **shifts one
    game** so every row holds the QB's state *entering* that game (no
    current-game leak). Volume cols are cumulative prior dropbacks/games.
    """
    db = (
        _dropbacks(pbp)
        .select(
            "passer_player_id",
            "game_id",
            "game_date",
            "play_id",
            "qb_epa",
            (pl.col("cpoe") / 100).alias("cpoe"),
        )
        .sort("passer_player_id", "game_date", "play_id")
        .with_columns(
            qb_epa_ewm=pl.col("qb_epa")
            .ewm_mean(half_life=half_life, ignore_nulls=True)
            .over("passer_player_id"),
            qb_cpoe_ewm=pl.col("cpoe")
            .ewm_mean(half_life=half_life, ignore_nulls=True)
            .over("passer_player_id"),
        )
    )
    per_game = (
        db.group_by("passer_player_id", "game_id", maintain_order=True)
        .agg(
            game_date=pl.first("game_date"),
            qb_epa_ewm=pl.last("qb_epa_ewm"),
            qb_cpoe_ewm=pl.last("qb_cpoe_ewm"),
            n_db=pl.len(),
        )
        .sort("passer_player_id", "game_date")
        .with_columns(
            qb_dropbacks=pl.col("n_db").cum_sum().over("passer_player_id"),
            qb_games=pl.int_range(1, pl.len() + 1).over("passer_player_id"),
        )
    )
    # lag one game: row now holds the QB's pre-game state
    return per_game.with_columns(
        pl.col(QB_COLS).shift(1).over("passer_player_id")
    ).select("passer_player_id", "game_id", *QB_COLS)


def _team_epa_ewm(pbp: pl.DataFrame, half_life: float) -> pl.DataFrame:
    """Per (team, game) lagged EWMA of *whoever* dropped back for the team.

    Same machinery as `qb_game_history` but grouped on ``posteam`` not the
    passer — a team-grain QB-production baseline, lagged one game. The
    downgrade feature is the starter's personal EWMA minus this: ~0 when
    the usual QB plays, large-negative when a backup steps in.
    """
    db = (
        _dropbacks(pbp)
        .select("posteam", "game_id", "game_date", "play_id", "qb_epa")
        .sort("posteam", "game_date", "play_id")
        .with_columns(
            ewm=pl.col("qb_epa")
            .ewm_mean(half_life=half_life, ignore_nulls=True)
            .over("posteam")
        )
    )
    return (
        db.group_by("posteam", "game_id", maintain_order=True)
        .agg(game_date=pl.first("game_date"), team_qb_epa_ewm=pl.last("ewm"))
        .sort("posteam", "game_date")
        .with_columns(pl.col("team_qb_epa_ewm").shift(1).over("posteam"))
        .select("posteam", "game_id", "team_qb_epa_ewm")
    )


def starters(pbp: pl.DataFrame) -> pl.DataFrame:
    """Each team's starting QB per game = the most-dropbacks passer."""
    return (
        _dropbacks(pbp)
        .group_by("game_id", "posteam", "passer_player_id")
        .agg(n=pl.len())
        .sort("n", descending=True)
        .group_by("game_id", "posteam", maintain_order=True)
        .agg(passer_player_id=pl.first("passer_player_id"))
    )


def add_qb_context(
    matrix: pl.DataFrame, pbp: pl.DataFrame, half_life: float = QB_HALF_LIFE
) -> pl.DataFrame:
    """Attach each team's starting-QB lagged features as home_/away_ cols.

    ``pbp`` must include prior-season lookback to warm the EWMA. Cold
    start (rookie's first game, no history) leaves the EWMA null and sets
    volume to 0; xgboost handles the nulls.
    """
    hist = qb_game_history(pbp, half_life)
    team_game = (
        starters(pbp)
        .join(hist, on=["passer_player_id", "game_id"], how="left")
        .select("game_id", "posteam", *QB_COLS)
    )
    away = team_game.rename(
        {"posteam": "away_team", **{c: f"away_{c}" for c in QB_COLS}}
    )
    home = team_game.rename(
        {"posteam": "home_team", **{c: f"home_{c}" for c in QB_COLS}}
    )
    vol = [
        f"{side}_qb_{m}" for side in ("away", "home") for m in ("dropbacks", "games")
    ]
    return (
        matrix.join(away, on=["game_id", "away_team"], how="left")
        .join(home, on=["game_id", "home_team"], how="left")
        .with_columns(pl.col(vol).fill_null(0))
    )


def add_qb_downgrade(
    matrix: pl.DataFrame, pbp: pl.DataFrame, half_life: float = QB_HALF_LIFE
) -> pl.DataFrame:
    """Attach ``home_/away_qb_downgrade`` = starter EWMA minus team baseline.

    Near 0 when the team's usual QB starts; large-negative when a weaker
    backup starts (injury / mid-season change) and positive when an
    upgrade starts. Isolates the player-grain *delta* the team aggregates
    miss, instead of the (redundant) absolute starter level. Cold start
    (no starter history) leaves it null; xgboost handles it.
    """
    hist = qb_game_history(pbp, half_life)
    team = _team_epa_ewm(pbp, half_life)
    team_game = (
        starters(pbp)
        .join(
            hist.select("passer_player_id", "game_id", "qb_epa_ewm"),
            on=["passer_player_id", "game_id"],
            how="left",
        )
        .join(team, on=["posteam", "game_id"], how="left")
        .select(
            "game_id",
            "posteam",
            qb_downgrade=pl.col("qb_epa_ewm") - pl.col("team_qb_epa_ewm"),
        )
    )
    away = team_game.rename(
        {"posteam": "away_team", "qb_downgrade": "away_qb_downgrade"}
    )
    home = team_game.rename(
        {"posteam": "home_team", "qb_downgrade": "home_qb_downgrade"}
    )
    return matrix.join(away, on=["game_id", "away_team"], how="left").join(
        home, on=["game_id", "home_team"], how="left"
    )
