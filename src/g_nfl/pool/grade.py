"""Grade pool picks against the pool spread and the final score.

The workbooks carry their own W/L cells, but they are hand-entered, use
four different conventions, and are missing for whole seasons. Everything
here is regraded from the nflverse schedule instead, so one rule applies
to every season and a mis-typed cell cannot reach the analysis.

Sign convention throughout is nflverse's: `spread_line` and `pool_spread`
are positive when the **home** team is favoured, and `result` is
`home_score - away_score`. So the home team covers when
`result > spread`, and a pick's own margin against its own number is
`cover = result - spread` flipped for an away pick.

Grading against the pool line is the point (see notes/SCORING.md); games
with no pool line recorded fall back to the market close, and the row says
which was used so analysis can exclude them.
"""

from __future__ import annotations

import polars as pl

from g_nfl.utils.teams import standardize_teams

# slots scored against the spread; underdog and survivor are outright pools
ATS_TYPES = ("regular", "best_bet", "mnf")
SLOT_POINTS = {"best_bet": 2, "regular": 1, "mnf": 1}

# the pool paid a best bet one point in 2020 and doubled it from 2021 —
# every winning 2020 best bet in the workbook is scored 1, none scored 2
DOUBLE_BEST_BET_FROM = 2021


def load_games(seasons: list[int]) -> pl.DataFrame:
    """Schedule rows with the market close and the final margin."""
    import nflreadpy as nfl

    return (
        nfl.load_schedules(seasons=seasons)
        .select("season", "week", "home_team", "away_team", "spread_line", "result")
        .with_columns(
            home_team=pl.col("home_team").map_elements(standardize_teams, pl.String),
            away_team=pl.col("away_team").map_elements(standardize_teams, pl.String),
        )
        .with_columns(
            game_id=pl.format(
                "{}_{}_{}_{}",
                "season",
                pl.col("week").cast(pl.String).str.zfill(2),
                "away_team",
                "home_team",
            )
        )
    )


def grade(
    picks: pl.DataFrame, games: pl.DataFrame, pool_lines: pl.DataFrame
) -> pl.DataFrame:
    """Attach the game, the line and the outcome to every pick.

    `picks` needs season, week, picker, slot, pick_type, team_picked.
    Picks whose team was on a bye — or misspelled past rescue — drop out,
    since there is no game to grade them against.
    """
    board = games.join(
        pool_lines.select("season", "week", "home_team", "pool_spread"),
        on=["season", "week", "home_team"],
        how="left",
    )
    # one row per team per week, so a pick joins on the team it named
    sides = pl.concat(
        [
            board.with_columns(team=pl.col("home_team"), is_home=pl.lit(True)),
            board.with_columns(team=pl.col("away_team"), is_home=pl.lit(False)),
        ]
    )

    graded = picks.join(
        sides,
        left_on=["season", "week", "team_picked"],
        right_on=["season", "week", "team"],
        how="inner",
    ).with_columns(
        line=pl.coalesce("pool_spread", "spread_line"),
        line_source=pl.when(pl.col("pool_spread").is_not_null())
        .then(pl.lit("pool"))
        .otherwise(pl.lit("market")),
    )

    return (
        graded.with_columns(
            # the picked team's own number: positive means it is the dog and
            # is getting points, which is also what the underdog slot pays
            team_spread=pl.when("is_home")
            .then(-pl.col("line"))
            .otherwise(pl.col("line")),
            # margin from the picked team's side
            margin=pl.when("is_home")
            .then(pl.col("result"))
            .otherwise(-pl.col("result")),
        )
        .with_columns(
            cover=pl.col("margin") + pl.col("team_spread"),
            su_win=pl.col("margin") > 0,
        )
        .with_columns(
            ats_result=pl.when(pl.col("cover") > 0)
            .then(pl.lit("W"))
            .when(pl.col("cover") < 0)
            .then(pl.lit("L"))
            .otherwise(pl.lit("P")),
        )
        .with_columns(
            points=_points(),
        )
    )


def _points() -> pl.Expr:
    """Pool points for a graded pick, by slot type (notes/SCORING.md).

    A push scores nothing. The underdog slot pays the spread itself on an
    outright win, which is why it can outscore a best bet.
    """
    slot_value = (
        pl.when(
            (pl.col("pick_type") == "best_bet")
            & (pl.col("season") < DOUBLE_BEST_BET_FROM)
        )
        .then(1)
        .otherwise(pl.col("pick_type").replace_strict(SLOT_POINTS, default=0))
    )
    ats = (
        pl.when(pl.col("ats_result") == "W")
        .then(slot_value)
        .otherwise(0)
        .cast(pl.Float64)
    )
    underdog = pl.when(pl.col("su_win")).then(pl.col("team_spread")).otherwise(0.0)
    return (
        pl.when(pl.col("pick_type") == "underdog")
        .then(underdog)
        .when(pl.col("pick_type").is_in(ATS_TYPES))
        .then(ats)
        # survivor scores no pool points; it is its own elimination pool
        .otherwise(0.0)
    )
