try:
    import nfl_data_py as nfl

    NFL_DATA_AVAILABLE = True
except ImportError:
    NFL_DATA_AVAILABLE = False

import math

import pandas as pd

from g_nfl import AVG_POINTS, CUR_SEASON, HFA, SPREAD_STDEV

predict_home_score = lambda row: AVG_POINTS + row.home_off - row.away_def + HFA / 2
predict_away_score = lambda row: AVG_POINTS + row.away_off - row.home_def - HFA / 2


def percentile_to_spread(percentile: float, stdev: float = SPREAD_STDEV) -> float:
    """Simple approximation of inverse normal distribution for percentile to spread conversion"""
    # Simple approximation - for a full app you'd want the real scipy version
    if percentile <= 0.5:
        z_score = -abs(percentile - 0.5) * 2.5  # Rough approximation
    else:
        z_score = abs(percentile - 0.5) * 2.5
    return round(z_score * stdev, 2)


def get_week_spreads(week: int, season: int = CUR_SEASON) -> pd.DataFrame:
    if not NFL_DATA_AVAILABLE:
        # Return sample data if nfl_data_py is not available
        return create_sample_schedule_data(week)

    try:
        schedule_df = nfl.import_schedules([season])
        schedule_df = (
            schedule_df[
                [
                    "week",
                    "game_id",
                    "away_team",
                    "home_team",
                    "spread_line",
                    "total_line",
                ]
            ]
            .query(f"week=={week}")
            .reset_index(level=0)
            .reset_index(level=0)
            .rename(columns={"level_0": "game_order"})
            .drop(columns=["index", "week"])
            .set_index("game_id")
        )
        schedule_df["game_order"] = schedule_df["game_order"] + 1
        return schedule_df
    except Exception as e:
        # Fallback to sample data if API fails
        return create_sample_schedule_data(week)


def create_sample_schedule_data(week: int) -> pd.DataFrame:
    """Create sample NFL schedule data for testing when nfl_data_py is not available"""
    sample_games = [
        {
            "game_id": f"2024_0{week}_BUF_MIA",
            "away_team": "BUF",
            "home_team": "MIA",
            "spread_line": -3.5,
            "total_line": 47.5,
        },
        {
            "game_id": f"2024_0{week}_NYJ_NE",
            "away_team": "NYJ",
            "home_team": "NE",
            "spread_line": -1.0,
            "total_line": 42.5,
        },
        {
            "game_id": f"2024_0{week}_BAL_PIT",
            "away_team": "BAL",
            "home_team": "PIT",
            "spread_line": -2.5,
            "total_line": 45.0,
        },
        {
            "game_id": f"2024_0{week}_CIN_CLE",
            "away_team": "CIN",
            "home_team": "CLE",
            "spread_line": -6.5,
            "total_line": 44.0,
        },
        {
            "game_id": f"2024_0{week}_HOU_IND",
            "away_team": "HOU",
            "home_team": "IND",
            "spread_line": -3.0,
            "total_line": 46.5,
        },
        {
            "game_id": f"2024_0{week}_JAX_TEN",
            "away_team": "JAX",
            "home_team": "TEN",
            "spread_line": -1.5,
            "total_line": 41.0,
        },
        {
            "game_id": f"2024_0{week}_KC_LV",
            "away_team": "KC",
            "home_team": "LV",
            "spread_line": -9.5,
            "total_line": 43.5,
        },
        {
            "game_id": f"2024_0{week}_LAC_DEN",
            "away_team": "LAC",
            "home_team": "DEN",
            "spread_line": -2.0,
            "total_line": 45.5,
        },
        {
            "game_id": f"2024_0{week}_DAL_WAS",
            "away_team": "DAL",
            "home_team": "WAS",
            "spread_line": -4.0,
            "total_line": 48.0,
        },
        {
            "game_id": f"2024_0{week}_NYG_PHI",
            "away_team": "NYG",
            "home_team": "PHI",
            "spread_line": -7.5,
            "total_line": 46.0,
        },
        {
            "game_id": f"2024_0{week}_CHI_GB",
            "away_team": "CHI",
            "home_team": "GB",
            "spread_line": -6.0,
            "total_line": 47.0,
        },
        {
            "game_id": f"2024_0{week}_DET_MIN",
            "away_team": "DET",
            "home_team": "MIN",
            "spread_line": -1.0,
            "total_line": 52.5,
        },
        {
            "game_id": f"2024_0{week}_ATL_NO",
            "away_team": "ATL",
            "home_team": "NO",
            "spread_line": -3.5,
            "total_line": 44.5,
        },
        {
            "game_id": f"2024_0{week}_CAR_TB",
            "away_team": "CAR",
            "home_team": "TB",
            "spread_line": -8.5,
            "total_line": 43.0,
        },
        {
            "game_id": f"2024_0{week}_SF_ARI",
            "away_team": "SF",
            "home_team": "ARI",
            "spread_line": -7.0,
            "total_line": 49.5,
        },
        {
            "game_id": f"2024_0{week}_SEA_LA",
            "away_team": "SEA",
            "home_team": "LA",
            "spread_line": -1.5,
            "total_line": 48.5,
        },
    ]

    df = pd.DataFrame(sample_games)
    df["game_order"] = range(1, len(df) + 1)
    return df.set_index("game_id")


def guess_the_lines_ovr(
    power_df: pd.DataFrame, week: int, season: int = CUR_SEASON
) -> pd.DataFrame:
    # get power and schedule_dfs
    schedule_df = get_week_spreads(week, season)

    gtl = pd.merge(
        schedule_df,
        power_df[["net_gpf"]],
        how="left",
        left_on="away_team",
        right_index=True,
    ).rename(
        columns={
            "net_gpf": "away_gpf",
        }
    )
    gtl = pd.merge(
        gtl, power_df[["net_gpf"]], how="left", left_on="home_team", right_index=True
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
    gtl["rank"] = (
        gtl["difference"].abs().rank(method="dense", ascending=False).astype(int)
    )
    return gtl


def guess_the_lines(
    power_df: pd.DataFrame, week: int, season: int = CUR_SEASON
) -> pd.DataFrame:
    # get power and schedule_dfs
    schedule_df = get_week_spreads(week, season)
    # power_df = get_power_ratings(week, season)

    gtl = pd.merge(
        schedule_df, power_df, how="left", left_on="away_team", right_index=True
    ).rename(columns={"ovr": "away_ovr", "off": "away_off", "def": "away_def"})
    gtl = pd.merge(
        gtl, power_df, how="left", left_on="home_team", right_index=True
    ).rename(columns={"ovr": "home_ovr", "off": "home_off", "def": "home_def"})
    gtl["hfa"] = HFA
    gtl["pred_away_score"] = gtl.apply(predict_away_score, axis=1)
    gtl["pred_home_score"] = gtl.apply(predict_home_score, axis=1)
    gtl["pred_line"] = gtl["pred_home_score"] - gtl["pred_away_score"]
    gtl["pred_total"] = gtl["pred_home_score"] + gtl["pred_away_score"]
    return gtl.round(1)
