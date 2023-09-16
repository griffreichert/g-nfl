import pandas as pd
from src.utils import clean_df_columns


def clean_inpredictible_df(df: pd.DataFrame):
    df = clean_df_columns(df)
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


# TODO: FIND WEEK 1 POWER NUMBERS
