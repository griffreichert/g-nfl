"""L4 continuity features: lineup stability, starting with the O-line.

The O-line is the canonical weak-link unit — five players who have to play
as one, where cohesion (continuity) matters more than raw talent and the
team aggregate can't see it. This lever measures how *stable* a team's
starting five has been within the season, entering each game.

Per team-game: the OL5 = the five offensive linemen (T/G/C) with the most
offensive snaps. ``ol_continuity`` = the running mean, over the season so
far, of how many of the OL5 carried over from the previous game (0-5).
It's the lagged season-to-date average, so the current game's lineup never
enters its own feature (no leak); early-season games are null (no history).

Within-season only for now (cheap, no extra data load). Year-to-year
carryover and the secondary/coverage unit are the next steps once this
earns its keep — see ``notes/modelling/continuity-and-weak-link.md``. Off
by default (see ``build_features`` ``continuity``).
"""

import polars as pl

OL_POS = ("T", "G", "C")
CONT_COLS = ["ol_continuity"]


def _ol5(snaps: pl.DataFrame) -> pl.DataFrame:
    """Each team's starting five linemen per game = most offensive snaps."""
    return (
        snaps.filter(
            (pl.col("game_type") == "REG")
            & pl.col("position").is_in(OL_POS)
            & (pl.col("offense_snaps") > 0)
        )
        .sort("offense_snaps", descending=True)
        .group_by("game_id", "team", "season", "week", maintain_order=True)
        .agg(ol5=pl.col("pfr_player_id").head(5))
    )


def ol_continuity(snaps: pl.DataFrame) -> pl.DataFrame:
    """Per (team, game) lagged season-to-date OL continuity index.

    ``n_retained`` = how many of this game's OL5 also started the prior
    game (set intersection). ``ol_continuity`` is the expanding mean of
    ``n_retained`` over the season, **shifted one game** so it reflects
    stability *entering* the game, not including it.
    """
    g = (
        _ol5(snaps)
        .sort("team", "season", "week")
        .with_columns(prev=pl.col("ol5").shift(1).over("team", "season"))
        .with_columns(
            n_retained=pl.col("ol5").list.set_intersection(pl.col("prev")).list.len()
        )
        .with_columns(
            _cs=pl.col("n_retained").fill_null(0).cum_sum().over("team", "season"),
            _cn=pl.col("n_retained").is_not_null().cum_sum().over("team", "season"),
        )
        .with_columns(
            _mean=pl.when(pl.col("_cn") > 0)
            .then(pl.col("_cs") / pl.col("_cn"))
            .otherwise(None)
        )
        .with_columns(ol_continuity=pl.col("_mean").shift(1).over("team", "season"))
    )
    return g.select("game_id", "team", *CONT_COLS)


def add_continuity(matrix: pl.DataFrame, snaps: pl.DataFrame) -> pl.DataFrame:
    """Attach each team's lagged OL continuity as home_/away_ cols.

    Early-season games (no prior-game history yet) leave the index null;
    xgboost handles the nulls.
    """
    cont = ol_continuity(snaps)
    away = cont.rename({"team": "away_team", **{c: f"away_{c}" for c in CONT_COLS}})
    home = cont.rename({"team": "home_team", **{c: f"home_{c}" for c in CONT_COLS}})
    return matrix.join(away, on=["game_id", "away_team"], how="left").join(
        home, on=["game_id", "home_team"], how="left"
    )
