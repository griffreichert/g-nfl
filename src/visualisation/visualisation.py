import os
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import nfl_data_py as nfl
import pandas as pd
from matplotlib.offsetbox import AnnotationBbox, OffsetImage

""" Resources I found helpful

Tej Seth great notebook on logos plotting basics - https://github.com/tejseth/nfl-tutorials-2022/blob/master/nfl_data_py_1.ipynb

"""

# define your path to the logos
LOGO_PATH = Path("../bin/logos")  # os.path.dirname(os.getcwd())


def fetch_logos():
    # if the path to the logos directory does not exist, create it
    if not os.path.exists(LOGO_PATH):
        print("fetching team logos...")
        os.makedirs(LOGO_PATH, exist_ok=True)
        logos = nfl.import_team_desc()[["team_abbr", "team_logo_espn"]]

        # get the logos for each team and store them to tif files in the logo path directory "<team>.tif"
        for _, team, logo in logos.itertuples():
            urllib.request.urlretrieve(logo, LOGO_PATH / f"{team}.tif")
        print("successfully retrieved logos")


def get_team_logo(team) -> OffsetImage:
    return OffsetImage(
        plt.imread(str(LOGO_PATH / f"{team}.tif"), format="tif"), zoom=0.08
    )


def plot_team_scatter(
    data: pd.DataFrame,
    x: str,
    y: str,
    title=None,
    ax_labels=None,
    mean_reference=True,
    zero_reference=True,
):
    # if team is the index of the df, turn it into a regular column
    if "team" not in data.columns:
        data = data.reset_index(level=0)
        data = data.rename(columns={data.columns[0]: "team"})

    assert all(
        col in data.columns for col in ["team", x, y]
    )  # ensure columns are in df

    plt.rcParams["figure.figsize"] = [12, 8]
    plt.rcParams["figure.autolayout"] = True
    fig, ax = plt.subplots()

    for xi, yi, team in zip(data[x].values, data[y].values, data["team"].values):
        ab = AnnotationBbox(get_team_logo(team), (xi, yi), frameon=False)
        ax.add_artist(ab)

    # Add padding to the axis limits
    padding_percentage = 0.1  # Adjust this value as needed
    x_min, x_max = data[x].min(), data[x].max()
    y_min, y_max = data[y].min(), data[y].max()

    x_padding = (x_max - x_min) * padding_percentage
    y_padding = (y_max - y_min) * padding_percentage
    # set axis limits based on the plot
    plt.xlim(x_min - x_padding, x_max + x_padding)
    plt.ylim(y_min - y_padding, y_max + y_padding)

    # add reference lines for 0's if the min is negative and we show the flag
    if zero_reference:
        if y_min < 0:
            plt.axhline(0, color="lightgrey", linestyle="-", linewidth=0.8)
        if x_min < 0:
            plt.axvline(0, color="lightgrey", linestyle="-", linewidth=0.8)

    # add reference lines for league averages
    if mean_reference:
        plt.axhline(data[y].mean(), color="red", linestyle="--", linewidth=0.8)
        plt.axvline(data[x].mean(), color="red", linestyle="--", linewidth=0.8)

    # add a title
    if title:
        plt.title(title)

    # label the axes
    if ax_labels:
        plt.xlabel(ax_labels[0])
        plt.ylabel(ax_labels[1])

    plt.show()

    return plt


if __name__ == "__main__":
    fetch_logos()
