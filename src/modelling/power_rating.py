import nfl_data_py as nfl
import pandas as pd

from src.utils.config import AVG_POINTS, CUR_SEASON, HFA
from src.utils.connections import load_service_account

file_name_template = "NFL Power Ratings - {season}"
sa = load_service_account()

predict_home_score = lambda row: AVG_POINTS + row.home_off - row.away_def + HFA / 2
predict_away_score = lambda row: AVG_POINTS + row.away_off - row.home_def - HFA / 2


def get_power_ratings(week: int, season: int = CUR_SEASON) -> pd.DataFrame:
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
    gsheet = sa.open(file_name_template.format(season=season))
    # open power ratings for this week
    work_sheet = gsheet.worksheet(f"Wk {week}")
    power_df = pd.DataFrame(work_sheet.get(range_name="A1:D33"))
    # reset column names
    power_df.columns = power_df.iloc[0]
    power_df = power_df.drop(0).set_index("team").astype("float32")
    return power_df


def get_schedule(week: int, season: int = CUR_SEASON) -> pd.DataFrame:
    schedule_df = nfl.import_schedules([season])
    schedule_df = (
        schedule_df[
            ["week", "game_id", "away_team", "home_team", "spread_line", "total_line"]
        ]
        .query(f"week=={week}")
        .set_index("game_id")
        .drop(columns=["week"])
        .rename(columns={"spread_line": "market_line"})
    )
    return schedule_df


def guess_the_lines(week: int, season: int = CUR_SEASON) -> pd.DataFrame:
    # get power and schedule_dfs
    schedule_df = get_schedule(week, season)
    power_df = get_power_ratings(week, season)

    gtl = pd.merge(schedule_df, power_df, left_on="away_team", right_index=True).rename(
        columns={"ovr": "away_ovr", "off": "away_off", "def": "away_def"}
    )
    gtl = pd.merge(gtl, power_df, left_on="home_team", right_index=True).rename(
        columns={"ovr": "home_ovr", "off": "home_off", "def": "home_def"}
    )
    gtl["hfa"] = HFA
    gtl["pred_away_score"] = gtl.apply(predict_away_score, axis=1)
    gtl["pred_home_score"] = gtl.apply(predict_home_score, axis=1)
    gtl["pred_line"] = gtl["pred_home_score"] - gtl["pred_away_score"]
    gtl["pred_total"] = gtl["pred_home_score"] + gtl["pred_away_score"]
    return gtl.round(1)
