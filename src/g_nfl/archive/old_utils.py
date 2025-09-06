import os
import re
from collections import defaultdict

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LinearRegression, Ridge

from g_nfl.utils.paths import LOGO_PATH

############################
#                          #
#        Team Utils        #
#                          #
############################

nfl_teams = {
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LA",
    "LAC",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
}


def get_nfl_teams() -> list:
    # list(sorted(nfl.import_schedules([2023]).away_team.unique()))
    return list(nfl_teams)


def standardize_teams(team):
    team_map = {
        "ARZ": "ARI",
        "BLT": "BAL",
        "CLV": "CLE",
        "HST": "HOU",
        "JAG": "JAX",
        "JAC": "JAX",
        "LAR": "LA",
        "PHL": "PHI",
        "WSH": "WAS",
        "WFT": "WAS",
    }
    team = team_map.get(team, team)
    assert team in nfl_teams, print(team, "not in dict")
    return team


def download_team_pngs():
    # Base URL for the team logos and local directory
    base_url = "https://a.espncdn.com/i/teamlogos/nfl/500/"

    # Create the local directory if it doesn't exist
    if not os.path.exists(LOGO_PATH):
        os.makedirs(LOGO_PATH)

    # Iterate through the list of teams, download logos, and save them locally
    for team in nfl_teams:
        team = team.lower()
        url = f"{base_url}{team}.png"
        response = requests.get(url)
        if response.status_code == 200:
            # Save the image to the local directory
            with open(LOGO_PATH / f"{team}.png", "wb") as file:
                file.write(response.content)
        else:
            print(f"Failed to download logo for {team}")
    print(f"Logos downloaded to {LOGO_PATH}")


############################
#                          #
#       Betting Utils      #
#                          #
############################


def derive_market_power_ratings(df: pd.DataFrame, weighted=True) -> tuple:
    """_summary_

    Args:
        df (pd.DataFrame): _description_

    Returns:
        tuple:
            pd.DataFrame:
            tuple: home field advantage, mean score
    """
    # function to calculate the expected score for home and away based on the spread and total
    exp_home_score = lambda row: (row["total"] + row["spread_line"]) / 2
    exp_away_score = lambda row: (row["total"] - row["spread_line"]) / 2

    mean_score = df["total"].mean() / 2

    # get the expected scores for each game
    df["exp_away"] = df.apply(exp_away_score, axis=1)
    df["exp_home"] = df.apply(exp_home_score, axis=1)

    # scale them based on the average team score
    df["scaled_away"] = df["exp_away"] - mean_score
    df["scaled_home"] = df["exp_home"] - mean_score

    current_week = df["week"].max()

    # create a system of equations where each row represents the coefficients for an offense going against a defense
    system = []
    for _, away_team, home_team, scaled_away, scaled_home, week in df[
        ["away_team", "home_team", "scaled_away", "scaled_home", "week"]
    ].itertuples():
        weight_coef = 1
        # inpredictable methodology
        # https://www.inpredictable.com/p/methodology.html
        if weighted:
            weight_coef = 1 / (current_week - week + 0.4)
        # Perspective of home team
        # 1 * home_offense - 1 * away_defense + 0.5 * home_field_advantage = home_score
        system.append(
            {
                f"{home_team}_off": 1 * weight_coef,
                f"{away_team}_def": -1 * weight_coef,
                "hfa": 0.5 * weight_coef,
                "score": scaled_home * weight_coef,
            }
        )
        # Perspective of away team (home field hurts you)
        # 1 * away_offense - 1 * home_defense - 0.5 * home_field_advantage = away_score
        system.append(
            {
                f"{away_team}_off": 1 * weight_coef,
                f"{home_team}_def": -1 * weight_coef,
                "hfa": -0.5 * weight_coef,
                "score": scaled_away * weight_coef,
            }
        )

    # turn the system of equations into a dataframe, fill teams not in that game as 0's
    system_df = pd.DataFrame(system).fillna(0)

    # sort the columns of the system of equations
    sorted_system_cols = list(sorted(system_df.columns))
    sorted_system_cols.remove("hfa")
    sorted_system_cols.remove("score")
    sorted_system_cols += ["hfa", "score"]

    system_df = system_df[sorted_system_cols]

    # use linear regression to solve for the coefficients
    reg = LinearRegression(fit_intercept=False)
    reg.fit(system_df.drop("score", axis=1), system_df["score"])

    # can use ridge regression to penalize large values if it makes them
    if reg.coef_[:-1][0] > 10:
        print("ridge")
        reg = Ridge(alpha=0.01, fit_intercept=False)
        reg.fit(system_df.drop("score", axis=1), system_df["score"])

    hfa = round(reg.coef_[-1], 2)

    # dict to hold team ratings
    rating_dict = defaultdict(dict)
    # iterate over offensive and defensive coefficients (ignore hfa and score columns)
    for team_str, rating in zip(system_df.columns[:-2], reg.coef_[:-1]):
        team, unit = team_str.split("_")
        rating_dict[team][unit] = rating

    power_ratings = pd.DataFrame(rating_dict).T
    power_ratings["ovr"] = power_ratings["off"] + power_ratings["def"]
    power_ratings = power_ratings[["ovr", "off", "def"]].copy()
    return power_ratings.sort_values("ovr", ascending=False), hfa


class ANSI:
    RESET = "\033[0m"
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


def cover_result(row, result_col="result", spread_col="spread_line"):
    # will return a 1 if the away team covered
    if row[result_col] == row[spread_col]:
        return 0.5
    elif row[result_col] < row[spread_col]:
        return 1
    return 0


def optional_list_label(col):
    # Calculate the lowest and highest weeks
    min_val = col.min()
    max_val = col.max()
    return str(min_val) if min_val == max_val else f"{min_val}-{max_val}"


####################################
#                                  #
#       Dataframe Processing       #
#                                  #
####################################


def clean_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    """_summary_

    Args:
        df (pd.DataFrame): Dataframe to clean

    Returns:
        pd.DataFrame: dataframe with cleaned columns
    """
    df.columns = [
        re.sub(r"\s", "_", re.sub(r"[^\w\s]", "", col.lower())) for col in df.columns
    ]
    return df


def reduce_memory_usage(df: pd.DataFrame, verbose=True) -> pd.DataFrame:
    """Reduct the memory usage of a dataframe by casting columns to their lowest possible values

    Args:
        df (pd.DataFrame): dataframe to shrink
        verbose (bool, optional): print amount of memory saved. Defaults to True.

    Returns:
        pd.DataFrame: dataframe with reduced memory
    """
    numerics = ["int8", "int16", "int32", "int64", "float16", "float32", "float64"]
    start_mem = df.memory_usage().sum() / 1024**2
    for col in df.columns:
        col_type = df[col].dtypes
        if col_type in numerics:
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == "int":
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
                elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                    df[col] = df[col].astype(np.int64)
            else:
                if (
                    c_min > np.finfo(np.float16).min
                    and c_max < np.finfo(np.float16).max
                ):
                    df[col] = df[col].astype(np.float16)
                elif (
                    c_min > np.finfo(np.float32).min
                    and c_max < np.finfo(np.float32).max
                ):
                    df[col] = df[col].astype(np.float32)
                else:
                    df[col] = df[col].astype(np.float64)
    end_mem = df.memory_usage().sum() / 1024**2
    if verbose:
        print(
            "Mem. usage decreased to {:.2f} Mb ({:.1f}% reduction)".format(
                end_mem, 100 * (start_mem - end_mem) / start_mem
            )
        )
    return df
