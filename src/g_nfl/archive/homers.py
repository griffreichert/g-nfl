import nfl_data_py as nfl
import numpy as np
import pandas as pd
import plotly.express as px

from g_nfl.utils.paths import HOMERS_PATH
from src import old_utils

PROCESSED_FILE_PATH = f"{HOMERS_PATH}/homers-processed.pkl"


def process_picks(df: pd.DataFrame, week, season) -> pd.DataFrame:
    """Execute the full pipeline to process no-homers picks

    Args:
        df (pd.DataFrame): _description_
        week (_type_): _description_
        season (_type_): _description_

    Returns:
        pd.DataFrame: _description_
    """
    df = clean_raw_picks(df)
    df = transform_picks(df, week, season)
    df = evaluate_picks(df, season)
    return df


def clean_raw_picks(df: pd.DataFrame):
    df = df.dropna(axis=1, how="all")
    df = old_utils.clean_df_columns(df)
    df = df.rename(columns={"team": "final", "pick": "pick_type"})
    assert all(
        col in ["pick_type", "final", "ben", "chuck", "griffin", "harry", "hunter"]
        for col in df.columns
    ), print(df.columns)
    assert len(df) == 9
    df["pick_type"] = (
        df.pick_type.map({i: "reg" for i in range(1, 6)})
        .fillna(df["pick_type"])
        .apply(str.lower)
    )
    df["pick_type"] = df.pick_type.apply(
        lambda x: "reg" if x not in ["bb", "reg", "sd", "ud", "mnf"] else x
    )
    return df


def transform_picks(df, week, season):
    # melt picks into a long table format
    df = pd.melt(
        df, id_vars=["pick_type"], var_name="picker", value_name="pick"
    ).dropna()
    df["season"] = season
    df["week"] = week
    df["pick"] = (
        df["pick"]
        .apply(str.upper)
        .apply(str.strip)
        .apply(lambda x: x.split("/")[0] if "/" in x else x)
    )
    df = df[df["pick"] != ""]
    # Map bad team names
    df["pick"] = df["pick"].apply(old_utils.standardize_teams)

    # turn pick types into one hot cols to make lookup faster
    df["spread_pick"] = df["pick_type"].map({"ud": False, "sd": False}).fillna(True)
    df["best_bet"] = df["pick_type"] == "bb"
    df["underdog_pick"] = df["pick_type"] == "ud"
    df["survivor_pick"] = df["pick_type"] == "sd"
    df["mnf_pick"] = df["pick_type"] == "mnf"
    df = df.drop(columns="pick_type")
    return df


def evaluate_picks(df, season):
    nfl_schedule = nfl.import_schedules([season])[
        ["game_id", "season", "week", "away_team", "home_team", "result", "spread_line"]
    ]
    # evaluate home and away picks against the score
    home_picks = pd.merge(
        df,
        nfl_schedule,
        left_on=["season", "week", "pick"],
        right_on=["season", "week", "home_team"],
    )
    away_picks = pd.merge(
        df,
        nfl_schedule,
        left_on=["season", "week", "pick"],
        right_on=["season", "week", "away_team"],
    )
    evaluated_picks = pd.concat([home_picks, away_picks], ignore_index=True)
    evaluated_picks["away_pick"] = (
        evaluated_picks["pick"] == evaluated_picks["away_team"]
    )
    evaluated_picks["away_cover"] = evaluated_picks.apply(
        old_utils.cover_result, axis=1
    )
    evaluated_picks["home_cover"] = 1 - evaluated_picks["away_cover"]
    evaluated_picks["pick_result"] = evaluated_picks.apply(pick_result, axis=1)

    return evaluated_picks


def pick_result(row, spread_col="spread_line"):
    """Score the result of spread picks, best bets, survivor, and underdog picks

    Args:
        row (_type_): _description_
        spread_col (str, optional): _description_. Defaults to "spread_line".

    Returns:
        int/float: result of the pick
    """
    res = 0
    # determine if pick was home or away team
    row["away_pick"]

    # determine spread bets
    if row["spread_pick"]:
        if row["away_pick"]:
            res = row["away_cover"]
        else:
            res = row["home_cover"]
        # double best bets
        if row["best_bet"]:
            res *= 2
    # sudden death
    if row["survivor_pick"]:
        if row["away_pick"]:
            if row["result"] < 0:
                res = 1
        else:
            if row["result"] > 0:
                res = 1
    if row["underdog_pick"]:
        if row["away_pick"]:
            if row["result"] < 0:
                res = abs(row[spread_col])
        else:
            if row["result"] > 0:
                res = abs(row[spread_col])
    return res


def plot_scores(df, pick_type="spread_pick", agg_sum=True):
    week_label = old_utils.optional_list_label(df["week"])
    season_label = old_utils.optional_list_label(df["season"])

    # filter to look at a specific pick type, group by the picker
    grouped_df = df[df[pick_type]].groupby("picker")["pick_result"]
    if agg_sum:
        grouped_df = grouped_df.sum()
    else:
        grouped_df = grouped_df.mean()
    grouped_df = grouped_df.sort_values(ascending=False).round(2).reset_index()
    # Create a Plotly bar chart
    fig = px.bar(
        grouped_df,
        x="pick_result",
        y="picker",
        orientation="h",
        color="picker",
        color_discrete_map=old_utils.picker_colors,
        text_auto=True,
        height=500,
        width=800,
        title=f"{season_label} Week{'s' if '-' in week_label else ''} {week_label}{' ' if agg_sum else ' Avg '}Scores - {pick_type.split('_')[0].capitalize()}",
    )
    # fig.update_yaxes(categoryorder="total descending")
    fig.update_traces(showlegend=False)

    # Show the plot in the Jupyter Notebook
    fig.show()
