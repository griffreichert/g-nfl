import pandas as pd
import scipy.stats as stats
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound

from src.modelling.utils import guess_the_lines_ovr
from src.scraping.google_sheets import col_to_int
from src.utils.config import CUR_SEASON
from src.utils.connections import load_service_account
from src.utils.teams import standardize_teams

pickers = ["Griffin", "Harry", "Chuck", "Hunter", "Jacko"]

google_sheet_names = {
    "Griffin": "NFL Power Ratings",
    "Harry": "GHR NFL Power Rating Template",
    "Chuck": "Copy of NFL Power Rating Template - CR",
    # "Hunter": "",
    # "Jacko": "",
}

master_google_sheet = "Picks Pool 24"

# Load the service acount from the google_config.json file
sa = load_service_account()


def calc_percentile_to_gpf(percentile: float, stdev=11.5) -> float:
    assert percentile >= 0.0
    while percentile > 1.0:
        percentile /= 10
    gpf = stats.norm.ppf(percentile) * stdev
    return gpf


def get_power_ratings(
    week: int, picker: str = "Griffin", season: int = CUR_SEASON
) -> pd.DataFrame:
    sheet_name = google_sheet_names[picker]
    tab_name = f"Wk {week}"

    try:
        # open the google sheet
        gsheet = sa.open(sheet_name)
    except SpreadsheetNotFound as e:
        print(
            f"WARNING: google sheet '{sheet_name}' not found, ensure it is shared with the service account"
        )
        raise e
    # open power ratings for this week
    try:
        work_sheet = gsheet.worksheet(tab_name)
        # gsheet.worksheet(f"Wk {week} fail")
    except WorksheetNotFound as e:
        print(f"WARNING: tab '{tab_name}' not found")
        raise e

    power_df = pd.DataFrame(work_sheet.get(range_name="A1:P33"))
    # reset column names
    power_df.columns = power_df.iloc[0]
    power_df = power_df.drop(0)
    power_df["team"] = power_df["team"].apply(standardize_teams)
    power_df = power_df.set_index("team").astype("float32")
    assert len(power_df) == 32

    return power_df


# def run_picks
def orchestrate_power_ratings_to_picks(
    week: int,
    picker: str = "Griffin",
    overwrite_tab: bool = False,
    hide_cols: bool = True,
    season: int = CUR_SEASON,
):
    sheet_name = google_sheet_names[picker]
    tab_name = f"Wk {week}"

    try:
        # open the google sheet
        gsheet = sa.open(sheet_name)
    except SpreadsheetNotFound as e:
        print(
            f"WARNING: google sheet '{sheet_name}' not found, ensure it is shared with the service account"
        )
        raise e

    power_df = get_power_ratings(week, picker=picker, season=season)

    gtl = (
        guess_the_lines_ovr(power_df, week=week, season=season)
        .drop(columns=["away_gpf", "home_gpf"])
        .reset_index(level=0)
    )
    gtl["adj_line"] = gtl["pred_line"]
    gtl["adj_difference"] = None
    gtl["adj_pick"] = None
    gtl["adj_rank"] = None
    gtl["confidence_pick"] = None
    gtl["confidence_rank"] = None
    col_char_mappings = {col: chr(65 + i) for i, col in enumerate(gtl.columns)}

    adj_difference_formulas = []
    adj_pick_formulas = []
    adj_rank_formulas = []
    confidence_pick_formulas = []
    confidence_rank_formulas = []
    n = len(gtl)
    for index, row in gtl.iterrows():
        i = int(index) + 2
        adj_difference_formulas.append(
            f"={col_char_mappings['adj_line']}{i}-{col_char_mappings['spread_line']}{i}"
        )
        adj_pick_formulas.append(
            f"=IF({col_char_mappings['adj_difference']}{i}>0,{col_char_mappings['home_team']}{i}, {col_char_mappings['away_team']}{i})"
        )
        adj_rank_formulas.append(
            f"=RANK(ABS({col_char_mappings['adj_difference']}{i}), ARRAYFORMULA(ABS(${col_char_mappings['adj_difference']}$2:${col_char_mappings['adj_difference']}${n+1})))"
        )
        confidence_pick_formulas.append(
            f"=IF({col_char_mappings['adj_line']}{i}>0,{col_char_mappings['home_team']}{i}, {col_char_mappings['away_team']}{i})"
        )
        confidence_rank_formulas.append(
            f"=RANK(ABS({col_char_mappings['pred_line']}{i}), ARRAYFORMULA(ABS(${col_char_mappings['pred_line']}$2:${col_char_mappings['pred_line']}${n+1})), 1)"
        )
    gtl["adj_difference"] = adj_difference_formulas
    gtl["adj_pick"] = adj_pick_formulas
    gtl["adj_rank"] = adj_rank_formulas
    gtl["confidence_pick"] = confidence_pick_formulas
    gtl["confidence_rank"] = confidence_rank_formulas
    pick_tab = tab_name + " - Picks"

    try:
        pick_worksheet = gsheet.worksheet(pick_tab)
        if overwrite_tab:
            gsheet.del_worksheet(pick_worksheet)
        else:
            print(f"Picks tab {pick_tab} already exists and overwrite_tab set to False")
            return None
    except WorksheetNotFound:
        pass

    pick_worksheet = gsheet.add_worksheet(pick_tab, 100, 100)

    data_to_upload = gtl.values.tolist()
    data_to_upload.insert(0, gtl.columns.tolist())
    data_to_upload = [
        [round(val, 2) if isinstance(val, float) else val for val in row]
        for row in data_to_upload
    ]
    # Update the worksheet with formulas
    # If update is causing issues, ensure that the values are treated correctly
    # by setting values explicitly as formulas
    cell_range = (
        f"A1:{chr(65 + len(gtl.columns) - 1)}{len(gtl) + 1}"  # Adjust range as needed
    )
    pick_worksheet.update(values=data_to_upload, range_name=cell_range, raw=False)

    if hide_cols:
        i = col_to_int(col_char_mappings["spread_line"])
        pick_worksheet.hide_columns(i, i + 1)

        i = col_to_int(col_char_mappings["difference"])
        j = col_to_int(col_char_mappings["rank"])
        pick_worksheet.hide_columns(i, j + 1)
        i = col_to_int(col_char_mappings["adj_difference"])
        j = col_to_int(col_char_mappings["confidence_rank"])
        pick_worksheet.hide_columns(i, j + 1)

    return gtl.drop(
        columns=[col for col in gtl.columns if "adj" in col or "confidence" in col]
    )
