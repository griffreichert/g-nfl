from collections import defaultdict
import numpy as np
import os
import pandas as pd
import re
import requests
from sklearn.linear_model import LinearRegression
from sklearn.linear_model import Ridge
from src.config import LOGO_PATH

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

# color_map = nfl.import_team_desc().set_index('team_abbr')['team_color'].to_dict()
team_primary_colors = {
    "ARI": "#97233F",
    "ATL": "#A71930",
    "BAL": "#241773",
    "BUF": "#00338D",
    "CAR": "#0085CA",
    "CHI": "#0B162A",
    "CIN": "#FB4F14",
    "CLE": "#FF3C00",
    "DAL": "#002244",
    "DEN": "#002244",
    "DET": "#0076B6",
    "GB": "#203731",
    "HOU": "#03202F",
    "IND": "#002C5F",
    "JAX": "#006778",
    "KC": "#E31837",
    "LA": "#003594",
    "LAC": "#007BC7",
    "LAR": "#003594",
    "LV": "#000000",
    "MIA": "#008E97",
    "MIN": "#4F2683",
    "NE": "#002244",
    "NO": "#D3BC8D",
    "NYG": "#0B2265",
    "NYJ": "#003F2D",
    "OAK": "#000000",
    "PHI": "#004C54",
    "PIT": "#000000",
    "SD": "#007BC7",
    "SEA": "#002244",
    "SF": "#AA0000",
    "STL": "#003594",
    "TB": "#A71930",
    "TEN": "#002244",
    "WAS": "#5A1414",
}

team_alt_colors = {
    "ARI": "#000000",
    "ATL": "#000000",
    "BAL": "#9E7C0C",
    "BUF": "#C60C30",
    "CAR": "#000000",
    "CHI": "#E64100",
    "CIN": "#000000",
    "CLE": "#311D00",
    "DAL": "#B0B7BC",
    "DEN": "#FB4F14",
    "DET": "#B0B7BC",
    "GB": "#FFB612",
    "HOU": "#A71930",
    "IND": "#a5acaf",
    "JAX": "#000000",
    "KC": "#FFB612",
    "LA": "#FFD100",
    "LAC": "#ffc20e",
    "LAR": "#FFD100",
    "LV": "#A5ACAF",
    "MIA": "#F58220",
    "MIN": "#FFC62F",
    "NE": "#C60C30",
    "NO": "#000000",
    "NYG": "#A71930",
    "NYJ": "#000000",
    "OAK": "#A5ACAF",
    "PHI": "#A5ACAF",
    "PIT": "#FFB612",
    "SD": "#ffc20e",
    "SEA": "#69be28",
    "SF": "#B3995D",
    "STL": "#FFD100",
    "TB": "#322F2B",
    "TEN": "#4B92DB",
    "WAS": "#FFB612",
}

team_unique_colors = {
    "ARI": "#97233F",
    "ATL": "#A71930",
    "BAL": "#241773",
    "BUF": "#00338D",
    "CAR": "#0085CA",
    "CHI": "#E64100",
    "CIN": "#FB4F14",
    "CLE": "#FF3C00",
    "DAL": "#002244",
    "DEN": "#FB4F14",
    "DET": "#0076B6",
    "GB": "#203731",
    "HOU": "#03202F",
    "IND": "#002C5F",
    "JAX": "#006778",
    "KC": "#E31837",
    "LA": "#003594",
    "LAC": "#007BC7",
    "LAR": "#003594",
    "LV": "#000000",
    "MIA": "#008E97",
    "MIN": "#4F2683",
    "NE": "#002244",
    "NO": "#D3BC8D",
    "NYG": "#0B2265",
    "NYJ": "#003F2D",
    "OAK": "#000000",
    "PHI": "#004C54",
    "PIT": "#000000",
    "SD": "#007BC7",
    "SEA": "#69be28",
    "SF": "#B3995D",
    "STL": "#003594",
    "TB": "#A71930",
    "TEN": "#4B92DB",
    "WAS": "#5A1414",
}

team_unique_alt_colors = {
    "ARI": "#000000",
    "ATL": "#000000",
    "BAL": "#9E7C0C",
    "BUF": "#C60C30",
    "CAR": "#000000",
    "CHI": "#0B162A",
    "CIN": "#000000",
    "CLE": "#311D00",
    "DAL": "#B0B7BC",
    "DEN": "#002244",
    "DET": "#B0B7BC",
    "GB": "#FFB612",
    "HOU": "#A71930",
    "IND": "#a5acaf",
    "JAX": "#000000",
    "KC": "#FFB612",
    "LA": "#FFD100",
    "LAC": "#ffc20e",
    "LAR": "#FFD100",
    "LV": "#A5ACAF",
    "MIA": "#F58220",
    "MIN": "#FFC62F",
    "NE": "#C60C30",
    "NO": "#000000",
    "NYG": "#A71930",
    "NYJ": "#000000",
    "OAK": "#A5ACAF",
    "PHI": "#A5ACAF",
    "PIT": "#FFB612",
    "SD": "#ffc20e",
    "SEA": "#002244",
    "STL": "#FFD100",
    "SF": "#AA0000",
    "TB": "#322F2B",
    "TEN": "#002244",
    "WAS": "#FFB612",
}

picker_colors = {
    "chuck": "#0B162A",
    "griffin": "#FF3C00",
    "harry": "#311D00",
    "hunter": "#A71930",
    "ben": "#5A1414",
    "final": "#B3995D",
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


###############################
#                             #
#       Odds Processing       #
#                             #
###############################


def implied_probability(odds: int, round_n=4) -> float:
    """Given the odds of a bet, calculate the implied probability

    Args:
        odds (int): odds of the bet (american so 200 would correspond to a 2/1 bet with 33% implied prob). will convert strings to ints
        round_n (int, optional): precision of decimal probability. Defaults to 2.

    Returns:
        float: implied probability of the bet
    """
    try:
        odds = int(odds)
    except ValueError:
        print("Invalid odds in betting-utils.py/implied_probability()")

    assert abs(odds) >= 100, "error odds are <100 cannot calculate prob"
    if odds < 0:
        return round(odds / (odds - 100), round_n)
    else:
        return round(1 - (odds / (odds + 100)), round_n)


def odds(implied_prob: float, as_str=False):
    """Given an implied probability calculate the american odds

    Args:
        implied_prob (float): implied probability of the bet
        as_str (bool, optional): will format value as a string and return positive odds with the '+'. Defaults to False.

    Returns:
        int: american odds of the event, ex: .5 will return 100. '
    """
    # favored event, odds will be negative
    if implied_prob > 0.5:
        res_odds = int((100 * implied_prob) / (implied_prob - 1))
        return f"{res_odds}" if as_str else res_odds
    # underdog event, odds will be positive
    else:
        res_odds = int((100 - 100 * implied_prob) / implied_prob)
        return f"+{res_odds}" if as_str else res_odds


def decimal_odds(implied_prob: float) -> float:
    return 1 / implied_prob


def decimal_implied_probability(decimal_odds: float) -> float:
    return 1 / decimal_odds


def decimal_odds_to_american(decimal_odds: float) -> int:
    if decimal_odds >= 2.0:
        american_odds = (decimal_odds - 1) * 100
    else:
        american_odds = -100 / (decimal_odds - 1)
    return round(american_odds)


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
