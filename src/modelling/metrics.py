from typing import List, Literal, Tuple

import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

success_rate_lambda = lambda x: 1 if x > 0 else 0


def calculate_epa_metrics(
    data: pd.DataFrame,
    team: Literal["posteam", "defteam"] = "posteam",
    percentile: bool = True,
) -> pd.DataFrame:
    """_summary_

    Parameters
    ----------
    data : pd.DataFrame
        pandas dataframe of play by play data
    team : Literal[&quot;posteam&quot;, &quot;defteam&quot;], optional
        _description_, by default "posteam"

    Returns
    -------
    pd.DataFrame
        dataframe containing epa information for the given sample
    """
    sort_ascending = team == "defteam"
    df = data.copy()
    df["success"] = df["epa"].apply(success_rate_lambda)
    epa_df = (
        df.groupby(team)
        .agg({team: "count", "epa": "mean", "success": "mean"})
        .sort_values(by="epa", ascending=False)
        .rename(columns={team: "plays", "success": "success_rate"})
    )
    for col in ["epa", "success_rate"]:
        epa_df[f"{col}_rank"] = epa_df[col].rank(ascending=sort_ascending).astype(int)
        if percentile:
            epa_df[f"{col}_percentile"] = (
                epa_df[col].rank(ascending=(not sort_ascending), pct=True).round(2) * 10
            )
    epa_df["epa"] = epa_df["epa"].round(3)
    epa_df["success_rate"] = epa_df["success_rate"].round(3)
    col_list = list(epa_df.columns)
    col_list.remove("plays")
    col_list = list(sorted(col_list))
    col_list.insert(0, "plays")
    return epa_df[col_list].sort_values("epa_rank")


def dual_epa_metrics(
    data: pd.DataFrame, percentile: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """_summary_

    Parameters
    ----------
    data : pd.DataFrame
        play by play dataframe

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        offense epa dataframe, defense epa dataframe
    """
    return calculate_epa_metrics(data, percentile=percentile), calculate_epa_metrics(
        data, "defteam", percentile=percentile
    )


def metric_over_expectation(
    data: pd.DataFrame,
    y_col: str,
    x_cols: List[str],
    summary: bool = True,
    binary: bool = False,
) -> pd.DataFrame:
    pass
