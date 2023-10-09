import os
import re
import pandas as pd
import requests
from io import BytesIO
from src import utils
from src.config import (
    INPREDICABLE_PATH,
    UNABATED_PATH,
    ESPN_PATH,
    NFELO_PATH,
    SUMER_ELO_PATH,
    SUMER_OFFENSE_PATH,
    SUMER_DEFENSE_PATH,
    SUMER_PLAYER_PATH,
)


def clean_inpredictible_df(df: pd.DataFrame):
    df = utils.clean_df_columns(df)
    # remove unnecessary columns
    cols_to_drop = ["lstwk1", "gpf1", "ogfp2", "dgfp2", "wl1", "projected_seed1"]
    df = df.drop(columns=cols_to_drop)
    # rename columns
    df = df.rename(
        columns={
            "gpf": "ovr",
            "ogpf": "off",
            "ogpf1": "off_rank",
            "dgpf": "def",
            "dgpf1": "def_rank",
        }
    )
    # parse out team names from goblygook
    # split wins and losses


def scrape_inpredictable(week: int, season: int) -> None:
    df = pd.read_html("https://stats.inpredictable.com/rankings/nfl.php")[0]
    df.columns = df.columns.droplevel(level=0)
    df = utils.clean_df_columns(df)

    # check the dataset is of the correct size
    assert df.shape[0] == 32, print(
        f"{utils.ANSI.RED}Error{utils.ANSI.RESET} - not 32 teams"
    )

    # dont overwrite an existing file
    file_path = f"{INPREDICABLE_PATH}/inpredictable-{season}-wk{week}.csv"
    if os.path.isfile(file_path):
        print(f"{file_path} exists!")
    else:
        # write the file to the correct path
        df.to_csv(file_path)
        print(
            f"{utils.ANSI.GREEN}Success{utils.ANSI.RESET} - Inpredictable Week {week}"
        )


def scrape_unabated(week: int, season: int) -> None:
    # Creating a BytesIO object
    byte_stream = BytesIO(
        requests.get("https://content.unabated.com/content/ratings/mp-nfl.csv").content
    )
    # Reading the bytes into a DataFrame
    df = pd.read_csv(byte_stream, delimiter=",", encoding="utf-8")
    df = utils.clean_df_columns(df)
    assert df.shape[0] == 32
    # dont overwrite an existing file
    file_path = f"{UNABATED_PATH}/unabated-{season}-wk{week}.csv"
    if os.path.isfile(file_path):
        print(f"{file_path} exists!")
    else:
        # write the file to the correct path
        df.to_csv(file_path)
        print(f"{utils.ANSI.GREEN}Success{utils.ANSI.RESET} - Unabated Week {week}")


def scrape_espn(week: int, season: int) -> None:
    df_list = pd.read_html("https://www.espn.com/nfl/fpi")
    df = df_list[1]
    df.columns = df.columns.droplevel(level=0)
    # join teams to ranks
    team_list = [df_list[0].columns[0]] + list(team[0] for team in df_list[0].values)
    df["team_name"] = team_list
    # clean and reorder columns
    df = utils.clean_df_columns(df)
    df = df[
        [
            "team_name",
            "wlt",
            "fpi",
            "rk",
            "trend",
            "off",
            "def",
            "st",
            "sos",
            "rem_sos",
            "avgwp",
        ]
    ]
    assert df.shape[0] == 32

    # dont overwrite an existing file
    file_path = f"{ESPN_PATH}/espn-{season}-wk{week}.csv"
    if os.path.isfile(file_path):
        print(f"{file_path} exists!")
    else:
        # write the file to the correct path
        df.to_csv(file_path)
        print(f"{utils.ANSI.GREEN}Success{utils.ANSI.RESET} - ESPN Week {week}")


def scrape_nfelo(week: int, season: int) -> None:
    df = pd.read_html("https://www.nfeloapp.com/nfl-power-ratings/")[0]
    df.columns = df.columns.droplevel(0)
    df = utils.clean_df_columns(df)
    df = df.rename(columns={df.columns[0]: "team"})
    df["team"] = df["team"].apply(lambda x: re.search(r"([A-Z]+)$", x).group(1))

    tendencies = pd.read_html(
        "https://www.nfeloapp.com/nfl-power-ratings/nfl-team-tendencies/"
    )[0]
    tendencies.columns = tendencies.columns.droplevel(0)
    tendencies = utils.clean_df_columns(tendencies)
    tendencies = tendencies.rename(columns={tendencies.columns[0]: "team"})
    tendencies["team"] = tendencies["team"].apply(
        lambda x: re.search(r"([A-Z]+)$", x).group(1)
    )
    tendencies = tendencies.drop(columns=["season"])
    df = pd.merge(df, tendencies, on="team")

    assert df.shape[0] == 32

    # dont overwrite an existing file
    file_path = f"{NFELO_PATH}/nfelo-{season}-wk{week}.csv"
    if os.path.isfile(file_path):
        print(f"{file_path} exists!")
    else:
        # write the file to the correct path
        df.to_csv(file_path)
        print(f"{utils.ANSI.GREEN}Success{utils.ANSI.RESET} - NFELO Week {week}")
