"""L4 QB player-grain features: starting-QB quality keyed on the player.

Each team-game gets its *starting* QB's recency-weighted EPA/CPOE plus
career volume, computed over the QB's own chronological dropback stream
and **lagged one game** so the current game is never in his estimate.

The starter's *identity* is the schedule's announced starter, known
before kickoff, and his *metrics* are strictly lagged. Identity used to
be inferred from the game itself (the QB with the most dropbacks), which
disagrees with the announced starter on 3.4% of team-games and disagrees
exactly where the starter left injured, so it leaked the injury into a
pre-game feature. `starters` still infers it that way for
`qb_change`, which wants the QB who actually played. The EWMA is
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


def announced_starters(schedule: pl.DataFrame) -> pl.DataFrame:
    """Each team's starting QB per game from the schedule's ``qb_id``.

    Leak-free by construction: the designated starter, known before
    kickoff, which is the only identity a feature may use.
    """
    reg = schedule.filter(pl.col("game_type") == "REG")
    return pl.concat(
        [
            reg.select(
                "game_id",
                posteam=pl.col("home_team"),
                passer_player_id=pl.col("home_qb_id"),
            ),
            reg.select(
                "game_id",
                posteam=pl.col("away_team"),
                passer_player_id=pl.col("away_qb_id"),
            ),
        ]
    ).drop_nulls("passer_player_id")


def starters(pbp: pl.DataFrame) -> pl.DataFrame:
    """Each team's most-dropbacks passer per game.

    This reads the game it describes, so it is not a pre-game fact. It is
    the right frame for `qb_change`, which asks who actually took the
    snaps; it is the wrong one for a feature, which gets
    `announced_starters`.
    """
    return (
        _dropbacks(pbp)
        .group_by("game_id", "posteam", "passer_player_id")
        .agg(n=pl.len())
        .sort("n", descending=True)
        .group_by("game_id", "posteam", maintain_order=True)
        .agg(passer_player_id=pl.first("passer_player_id"))
    )


def add_qb_context(
    matrix: pl.DataFrame,
    pbp: pl.DataFrame,
    schedule: pl.DataFrame,
    half_life: float = QB_HALF_LIFE,
) -> pl.DataFrame:
    """Attach each team's announced starting QB's lagged features as
    home_/away_ cols.

    ``pbp`` must include prior-season lookback to warm the EWMA. Cold
    start (rookie's first game, no history) leaves the EWMA null and sets
    volume to 0; xgboost handles the nulls. ``schedule`` supplies the
    announced starter, which is what a prediction made before kickoff
    actually knows.
    """
    hist = qb_game_history(pbp, half_life)
    team_game = (
        announced_starters(schedule)
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
