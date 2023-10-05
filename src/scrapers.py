import os
import pandas as pd
import requests
from io import BytesIO
from src import utils
from src.config import INPREDICABLE_PATH


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
    assert not os.path.isfile(file_path), print(
        f"{utils.ANSI.RED}Error{utils.ANSI.RESET} - {file_path} exists!"
    )

    # write the file to the correct path
    df.to_csv(f"{INPREDICABLE_PATH}/inpredictable-{season}-wk{week}.csv")
    print(f"{utils.ANSI.GREEN}Success{utils.ANSI.RESET} - Inpredictable Week {week}")


def scrape_unabated(week: int, season: int) -> None:
    # Creating a BytesIO object
    byte_stream = BytesIO(
        requests.get("https://content.unabated.com/content/ratings/mp-nfl.csv").content
    )
    # Reading the bytes into a DataFrame
    df = pd.read_csv(byte_stream, delimiter=",", encoding="utf-8")
    df = utils.clean_df_columns(df)
    assert df.shape[0] == 32
