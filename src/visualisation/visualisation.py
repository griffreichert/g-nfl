from typing import Literal, Tuple, Union

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
from adjustText import adjust_text
from matplotlib.offsetbox import AnnotationBbox

from src.utils.logos import get_team_logo
from src.utils.paths import LOGO_PATH
from src.visualisation import colors

""" Resources I found helpful

Tej Seth great notebook on logos plotting basics - https://github.com/tejseth/nfl-tutorials-2022/blob/master/nfl_data_py_1.ipynb

"""


def plot_scatter(
    data: pd.DataFrame,
    x: str,
    y: str,
    marker: Literal["team", "player"] = "team",
    marker_size: str = "",
    add_marker_label: bool = False,
    alpha: float = 1.0,
    title: Union[str, None] = None,
    ax_labels: Tuple[str, str] = ("", ""),
    mean_reference: bool = True,
    zero_reference: bool = False,
    best_fit: bool = False,
    logo_size: Union[int, None] = None,
    flip_x: bool = False,
    flip_y: bool = False,
    custom_style: Union[dict, None] = None,
) -> None:

    assert all(col in data.columns for col in [marker, x, y])
    add_logo = marker_size == ""
    # make the logo
    if logo_size is None:
        if marker == "player":
            logo_size = 30
        elif marker == "team":
            logo_size = 50
    plt.style.use("seaborn-v0_8-whitegrid")
    if custom_style:
        plt.style.use(custom_style)

    plt.rcParams["figure.figsize"] = [12, 8]
    plt.rcParams["figure.autolayout"] = True
    _, ax = plt.subplots()

    marker_labels = []  # List to hold all text objects for adjustment

    # Iterate over the DataFrame rows
    for _, row in data.iterrows():
        # Add the team logo
        if add_logo:
            ab = AnnotationBbox(
                get_team_logo(row["team"], size=(logo_size, logo_size), alpha=alpha),
                (row[x], row[y]),
                frameon=False,
            )
            ax.add_artist(ab)
        # if not adding a logo add a marker dot
        else:
            if marker_size:
                size = row[marker_size]
            else:
                size = 40  # Default marker size if marker_size is not provided
            ax.scatter(
                row[x],
                row[y],
                s=size,
                color=colors.team_unique_colors[row["team"]],
                alpha=alpha,
            )
        if add_marker_label:
            label = ax.text(
                row[x],  # Initial offset for text placement
                row[y],
                row[marker],
                fontsize=12,
                ha="left",
                va="center",
            )
            marker_labels.append(label)

    # Adjust text labels to avoid overlap, with parameters to keep them close

    # Add padding to the axis limits
    padding_percentage = 0.1  # Adjust this value as needed
    x_min, x_max = data[x].min(), data[x].max()
    y_min, y_max = data[y].min(), data[y].max()

    x_padding = (x_max - x_min) * padding_percentage
    y_padding = (y_max - y_min) * padding_percentage

    plt.xlim(x_min - x_padding, x_max + x_padding)
    plt.ylim(y_min - y_padding, y_max + y_padding)
    # Set axis limits based on the plot
    if flip_x:
        plt.gca().invert_xaxis()
    if flip_y:
        plt.gca().invert_yaxis()

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
    plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)

    # Adjust text labels to avoid overlap, with controlled arrow properties
    if add_marker_label:
        adjust_text(
            marker_labels,
            arrowprops=dict(arrowstyle="-", color="gray", lw=0.5, shrinkA=5, shrinkB=5),
            only_move={
                "texts": "xy",
            },  # Limit movement to reduce displacement
            force_text=0.1,  # Reduce the force to keep text closer
            # expand_text=(1.05, 1.2),  # Control expansion, adjust these values as needed
            # expand_points=(1.05, 1.2),  # Control expansion for points as well
            lim=100,  # Limit the number of iterations
        )
    plt.show()


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
    print("deprecated, use plot_scatter() instead")
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
