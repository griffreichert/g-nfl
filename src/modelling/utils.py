import nfl_data_py as nfl
import pandas as pd
from scipy.stats import norm

from src.utils.config import AVG_POINTS, CUR_SEASON, HFA, SPREAD_STDEV

predict_home_score = lambda row: AVG_POINTS + row.home_off - row.away_def + HFA / 2
predict_away_score = lambda row: AVG_POINTS + row.away_off - row.home_def - HFA / 2


def percentile_to_spread(percentile: float, stdev: float = SPREAD_STDEV) -> float:
    return round(float(norm.ppf(percentile)) * stdev, 2)


def get_week_spreads(week: int, season: int = CUR_SEASON) -> pd.DataFrame:
    schedule_df = nfl.import_schedules([season])
    schedule_df = (
        schedule_df[
            ["week", "game_id", "away_team", "home_team", "spread_line", "total_line"]
        ]
        .query(f"week=={week}")
        .set_index("game_id")
        .drop(columns=["week"])
        # .rename(columns={"spread_line": "market_line"})
    )
    return schedule_df


def guess_the_lines_ovr(
    power_df: pd.DataFrame, week: int, season: int = CUR_SEASON
) -> pd.DataFrame:
    # get power and schedule_dfs
    schedule_df = get_week_spreads(week, season)

    gtl = pd.merge(
        schedule_df, power_df[["net_gpf"]], left_on="away_team", right_index=True
    ).rename(
        columns={
            "net_gpf": "away_gpf",
        }
    )
    gtl = pd.merge(
        gtl, power_df[["net_gpf"]], left_on="home_team", right_index=True
    ).rename(
        columns={
            "net_gpf": "home_gpf",
        }
    )
    gtl = gtl.drop(columns=["total_line"])
    gtl["pred_line"] = (gtl["home_gpf"] - gtl["away_gpf"] + HFA).round(2)
    gtl["difference"] = gtl["pred_line"] - gtl["spread_line"]
    gtl["pick"] = gtl.apply(
        lambda row: row["home_team"] if row["difference"] > 0 else row["away_team"],
        axis=1,
    )
    gtl["difference_rank"] = (
        gtl["difference"].abs().rank(method="dense", ascending=False).astype(int)
    )
    return gtl.sort_values("difference_rank")


def guess_the_lines(
    power_df: pd.DataFrame, week: int, season: int = CUR_SEASON
) -> pd.DataFrame:
    # get power and schedule_dfs
    schedule_df = get_week_spreads(week, season)
    # power_df = get_power_ratings(week, season)

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
