import os
import sys

import pandas as pd
import streamlit as st
from PIL import Image

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.modelling.utils import get_week_spreads
from src.utils.config import CUR_SEASON

st.set_page_config(page_title="NFL Weekly Games", layout="wide")

# Initialize session state for picks
if "picks" not in st.session_state:
    st.session_state.picks = {}


def get_team_logo(team_name):
    """Get team logo image from bin/logos/ directory"""
    logo_path = os.path.join(
        os.path.dirname(__file__), "..", "bin", "logos", f"{team_name}.tif"
    )
    if os.path.exists(logo_path):
        try:
            return Image.open(logo_path)
        except Exception:
            return None
    return None


st.title("📈 NFL Weekly Games & Spreads")

# Custom CSS to make selected buttons green
st.markdown(
    """
<style>
div.stButton > button[kind="primary"] {
    background-color: #28a745 !important;
    border-color: #28a745 !important;
    color: white !important;
}
div.stButton > button[kind="primary"]:hover {
    background-color: #218838 !important;
    border-color: #1e7e34 !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# Create centered container matching table width
col_spacer1, col_controls, col_spacer2 = st.columns([2, 6, 2])

with col_controls:
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        season = st.selectbox(
            "Select Season",
            list(range(2020, CUR_SEASON + 1)),
            index=len(list(range(2020, CUR_SEASON + 1))) - 1,
        )

    with col2:
        week = st.selectbox("Select Week", list(range(1, 19)), index=0)

    with col3:
        st.write("")  # Add some vertical spacing
        load_button = st.button("Load Games")

if load_button or "games_data" not in st.session_state:
    try:
        with st.spinner("Loading NFL games data..."):
            games_df = get_week_spreads(week, season)
            st.session_state.games_data = games_df
            st.session_state.current_week = week
            st.session_state.current_season = season
            # Clear picks when changing games
            if (
                "last_week_season" not in st.session_state
                or st.session_state.last_week_season != (week, season)
            ):
                st.session_state.picks = {}
                st.session_state.last_week_season = (week, season)
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.stop()


if "games_data" in st.session_state:
    games_df = st.session_state.games_data

    if not games_df.empty:

        # Create centered container with limited width
        col_spacer1, col_content, col_spacer2 = st.columns([2, 6, 2])

        with col_content:
            # Header row
            header_col1, header_col2, header_col3 = st.columns([2, 2, 2])
            with header_col1:
                st.markdown("**Away**")
            with header_col2:
                st.markdown("**Spread / Total**")
            with header_col3:
                st.markdown("**Home**")
            st.markdown("---")

            for _, game in games_df.iterrows():
                game_id = game.name  # This is the game_id from the index

                with st.container():
                    col1, col2, col3 = st.columns([2, 2, 2])

                    with col1:
                        # Away team button
                        away_selected = (
                            st.session_state.picks.get(game_id) == game["away_team"]
                        )

                        away_logo = get_team_logo(game["away_team"])
                        if away_logo:
                            col_logo, col_button = st.columns([1, 3])
                            with col_logo:
                                st.image(away_logo, width=35)
                            with col_button:
                                button_type = (
                                    "primary" if away_selected else "secondary"
                                )
                                if st.button(
                                    f"{game['away_team']}",
                                    key=f"away_{game_id}",
                                    type=button_type,
                                ):
                                    if away_selected:
                                        # Unselect if already selected
                                        if game_id in st.session_state.picks:
                                            del st.session_state.picks[game_id]
                                    else:
                                        st.session_state.picks[game_id] = game[
                                            "away_team"
                                        ]
                                    st.rerun()
                        else:
                            button_type = "primary" if away_selected else "secondary"
                            if st.button(
                                f"{game['away_team']}",
                                key=f"away_{game_id}",
                                type=button_type,
                            ):
                                if away_selected:
                                    # Unselect if already selected
                                    if game_id in st.session_state.picks:
                                        del st.session_state.picks[game_id]
                                else:
                                    st.session_state.picks[game_id] = game["away_team"]
                                st.rerun()

                    with col2:
                        # Show spread exactly as it comes from get_week_spreads()
                        if pd.notna(game["spread_line"]):
                            spread_text = f"{game['spread_line']:+.1f}"
                        else:
                            spread_text = "N/A"

                        total_text = (
                            f"{game['total_line']:.1f}"
                            if pd.notna(game["total_line"])
                            else "N/A"
                        )
                        st.markdown(f"**{spread_text} / {total_text}**")

                    with col3:
                        # Home team button
                        home_selected = (
                            st.session_state.picks.get(game_id) == game["home_team"]
                        )

                        home_logo = get_team_logo(game["home_team"])
                        if home_logo:
                            col_logo, col_button = st.columns([1, 3])
                            with col_logo:
                                st.image(home_logo, width=35)
                            with col_button:
                                button_type = (
                                    "primary" if home_selected else "secondary"
                                )
                                if st.button(
                                    f"{game['home_team']}",
                                    key=f"home_{game_id}",
                                    type=button_type,
                                ):
                                    if home_selected:
                                        # Unselect if already selected
                                        if game_id in st.session_state.picks:
                                            del st.session_state.picks[game_id]
                                    else:
                                        st.session_state.picks[game_id] = game[
                                            "home_team"
                                        ]
                                    st.rerun()
                        else:
                            button_type = "primary" if home_selected else "secondary"
                            if st.button(
                                f"{game['home_team']}",
                                key=f"home_{game_id}",
                                type=button_type,
                            ):
                                if home_selected:
                                    # Unselect if already selected
                                    if game_id in st.session_state.picks:
                                        del st.session_state.picks[game_id]
                                else:
                                    st.session_state.picks[game_id] = game["home_team"]
                                st.rerun()

                # Use a thinner divider
                st.markdown("---")

        st.caption(
            f"📊 Showing {len(games_df)} games for Week {st.session_state.current_week}"
        )

        # Show picks summary
        if st.session_state.picks:
            st.subheader("🎯 Your Picks")
            picks_list = []
            for game_id, team in st.session_state.picks.items():
                if game_id in games_df.index:
                    game = games_df.loc[game_id]
                    # Show spread exactly as it comes from get_week_spreads()
                    spread = (
                        f"{game['spread_line']:+.1f}"
                        if pd.notna(game["spread_line"])
                        else "N/A"
                    )
                    picks_list.append(f"**{team}** ({spread})")

            if picks_list:
                st.write(" • ".join(picks_list))

                if st.button("Clear All Picks", type="secondary"):
                    st.session_state.picks = {}
                    st.rerun()
    else:
        st.warning("No games found for the selected week and season.")
