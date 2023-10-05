import pandas as pd
import numpy as np
import re

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


def clean_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [
        re.sub(r"\s", "_", re.sub(r"[^\w\s]", "", col.lower())) for col in df.columns
    ]
    return df


def cover_result(row, result_col="result", spread_col="spread_line"):
    if row[result_col] == row[spread_col]:
        return 0.5
    elif row[result_col] < row[spread_col]:
        return 1
    return 0


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
    assert team in nfl_teams, team
    return team


def pick_result(row, spread_col="spread_line"):
    res = 0
    away_flag = row["pick"] == row["away_team"]

    # determine spread bets
    if row["pick_type"] in ["bb", "reg", "mnf"]:
        if away_flag:
            res = row["away_cover"]
        else:
            res = row["home_cover"]
        # double best bets
        if row["pick_type"] == "bb":
            res *= 2
    # sudden death
    if row["pick_type"] == "sd":
        if away_flag:
            if row["result"] < 0:
                res = 1
        elif row["result"] > 0:
            res = 1
    if row["pick_type"] == "ud":
        if away_flag:
            if row["result"] < 0:
                res = abs(row[spread_col])
        else:
            if row["result"] > 0:
                res = abs(row[spread_col])
    return res


def reduce_memory_usage(df, verbose=True):
    """Reduct the memory usage of a dataframe by casting columns to their lowest possible values"""
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
