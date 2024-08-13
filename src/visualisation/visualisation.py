from typing import Tuple, Union

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
from matplotlib.offsetbox import AnnotationBbox

from src.utils.logos import get_team_logo
from src.utils.paths import LOGO_PATH
from src.visualisation import colors

""" Resources I found helpful

Tej Seth great notebook on logos plotting basics - https://github.com/tejseth/nfl-tutorials-2022/blob/master/nfl_data_py_1.ipynb

"""


def plot_team_scatter(
    data: pd.DataFrame,
    x: str,
    y: str,
    title: Union[str, None] = None,
    ax_labels: Tuple[str, str] = ("", ""),
    mean_reference: bool = True,
    zero_reference: bool = True,
    flip_def: bool = False,
    alpha: float = 1.0,
) -> None:

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
        ab = AnnotationBbox(get_team_logo(team, alpha=alpha), (xi, yi), frameon=False)
        ax.add_artist(ab)

    # Add padding to the axis limits
    padding_percentage = 0.1  # Adjust this value as needed
    x_min, x_max = data[x].min(), data[x].max()
    y_min, y_max = data[y].min(), data[y].max()

    x_padding = (x_max - x_min) * padding_percentage
    y_padding = (y_max - y_min) * padding_percentage

    plt.xlim(x_min - x_padding, x_max + x_padding)
    plt.ylim(y_min - y_padding, y_max + y_padding)
    # Set axis limits based on the plot
    if flip_def:
        # plt.xlim(x_max + x_padding, x_min - x_padding)
        # plt.ylim(y_max + y_padding, y_min - y_padding)
        plt.gca().invert_yaxis()
        plt.gca().invert_xaxis()
    # else:
    #     plt.xlim(x_min - x_padding, x_max + x_padding)
    #     plt.ylim(y_min - y_padding, y_max + y_padding)

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
    plt.xlabel(ax_labels[0] or x)
    plt.ylabel(ax_labels[1] or y)

    plt.show()


def plot_bar(
    data: pd.DataFrame,
    x: str,
    y: str,
    title: Union[str, None] = None,
    ax_labels: Tuple[str, str] = ("", ""),
    citation: bool = True,
    dark_mode: bool = True,
) -> None:
    fig = px.bar(
        data,
        x=x,
        y=y,
        orientation="h",
        color="team",
        color_discrete_map=colors.team_unique_colors,
        opacity=0.85,
    )
    if "team" in data.columns:
        # Iterate through the data and add logos to the chart
        for _, row in data.iterrows():
            scale = 1.25
            fig.add_layout_image(
                dict(
                    source=f"https://a.espncdn.com/i/teamlogos/nfl/500/{row['team']}.png",
                    x=row[x],
                    y=row[y],
                    xref="x",
                    yref="y",
                    sizex=scale,  # Adjust the size
                    sizey=scale,  # Adjust the size
                    sizing="contain",
                    opacity=1,
                    xanchor="center",
                    yanchor="middle",
                )
            )
    # TODO: could flip for defenses here
    fig.update_yaxes(categoryorder="total ascending")

    MARGIN = 100

    citation_kwargs = {
        "annotations": [
            dict(
                text="Data: @nflfastR | Chart: @griffreichert",
                x=-0.25,  # centered
                y=-0.1,  # position above
                xref="paper",
                yref="paper",
                showarrow=False,
                xanchor="left",
                yanchor="top",
                font=dict(size=12),
            )
        ],
        "margin": dict(t=MARGIN, b=MARGIN, l=MARGIN, r=MARGIN),
    }

    fig.update_layout(
        height=800,
        width=700,
        template="plotly_dark" if dark_mode else "plotly_white",
        # template="plotly_white",
        xaxis_title=ax_labels[0] or x,  # NOTE: flipped because horizontal
        yaxis_title="",
        title=title,
        title_x=0.5,  # Centers the title horizontally
    )
    if citation:
        fig.update_layout(**citation_kwargs)

    fig.update_traces(showlegend=False)
    # Show the chart
    fig.show()
