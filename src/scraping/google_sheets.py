import nfl_data_py as nfl
import pandas as pd

from src.utils.config import CUR_SEASON
from src.utils.connections import load_service_account

# Load the service acount from the google_config.json file
sa = load_service_account()


def get_power_ratings(file_name: str, week: int) -> pd.DataFrame:
    """Get the power rating dataframe for the givem

    Parameters
    ----------
    week : int
        week for power ratings. Ratings are for the upcoming games (i.e. made on a tuesday for the upcoming games on thurs and sun)
    season : int, optional
        season, by default CUR_SEASON

    Returns
    -------
    pd.DataFrame
        power rating dataframe with ovr, off, def ratings. team is the index.
    """
    # open the google sheet
    gsheet = sa.open(file_name)
    # open power ratings for this week
    work_sheet = gsheet.worksheet(f"Wk {week}")
    power_df = pd.DataFrame(work_sheet.get(range_name="A1:P33"))
    # reset column names
    power_df.columns = power_df.iloc[0]
    power_df = power_df.drop(0).set_index("team").astype("float32")
    return power_df
