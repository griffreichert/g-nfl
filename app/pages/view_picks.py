import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from g_nfl.modelling.utils import get_week_spreads
from g_nfl.utils.config import CUR_SEASON
from g_nfl.utils.web_app import get_picks_data, get_team_logo

st.set_page_config(page_title="View Picks - no-homers", layout="wide")

st.title("🔍 View Picks by Week")

# Add controls for selecting week and picker
col_spacer1, col_controls, col_spacer2 = st.columns([2, 6, 2])

with col_controls:
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        season = st.selectbox(
            "Select Season",
            list(range(2020, CUR_SEASON + 1)),
            index=len(list(range(2020, CUR_SEASON + 1))) - 1,
            key="view_season",
        )

    with col2:
        week = st.selectbox("Select Week", list(range(1, 19)), index=0, key="view_week")

    with col3:
        st.write("")  # Empty space where picker filter was

    with col4:
        st.write("")  # Add some vertical spacing
        load_picks_button = st.button("Load Picks", key="load_picks_btn")

# Load picks data
if load_picks_button or "picks_data" not in st.session_state:
    try:
        with st.spinner("Loading picks data..."):
            # Always load all pickers (no filter)
            picks_data = get_picks_data(season, week, None)
            st.session_state.picks_data = picks_data
            st.session_state.current_view_season = season
            st.session_state.current_view_week = week

            # Also load games data for spread information
            try:
                games_df = get_week_spreads(week, season)
                st.session_state.games_data_view = games_df
            except Exception as e:
                st.warning(f"Could not load games data: {e}")
                st.session_state.games_data_view = pd.DataFrame()

    except Exception as e:
        st.error(f"Error loading picks data: {str(e)}")
        st.stop()

# Display picks if data is loaded
if "picks_data" in st.session_state and st.session_state.picks_data:
    picks_data = st.session_state.picks_data
    games_df = st.session_state.get("games_data_view", pd.DataFrame())

    st.success(
        f"✅ Loaded {len(picks_data)} picks for Week {st.session_state.current_view_week}"
    )

    # Get all unique pickers and teams
    all_pickers = sorted(list(set(pick["picker"] for pick in picks_data)))
    all_teams = sorted(list(set(pick["team_picked"] for pick in picks_data)))

    # Create team-picker matrix with points
    team_data = []
    for team in all_teams:
        row_data = {"Team": team}
        total_points = 0

        for picker in all_pickers:
            # Find picks for this team by this picker
            team_picks = [
                p
                for p in picks_data
                if p["team_picked"] == team and p["picker"] == picker
            ]

            if team_picks:
                # Determine display symbol and points
                has_best_bet = any(
                    pick.get("pick_type") == "best_bet" for pick in team_picks
                )

                if has_best_bet:
                    row_data[picker] = "⭐"
                    total_points += 2
                else:
                    row_data[picker] = "✅"
                    total_points += 1
            else:
                row_data[picker] = ""

        # Get team logo and format team name with points
        team_logo_url = get_team_logo(team)
        if total_points > 0:
            team_display = f"{team} ({total_points})"
        else:
            team_display = team

        row_data["Team"] = team_display
        row_data["Team_Logo"] = team_logo_url  # Store logo URL for potential use
        row_data["_sort_points"] = total_points  # Hidden field for sorting
        team_data.append(row_data)

    # Sort by total points descending
    team_data.sort(key=lambda x: x["_sort_points"], reverse=True)

    # Create DataFrame with columns in desired order: Team, then pickers (no Total Points column)
    column_order = ["Team"] + all_pickers
    df = pd.DataFrame(team_data)[column_order]

    # Display the table
    st.subheader("🏆 Team Picks Ranked by Points")
    st.caption("Regular pick = 1 point (✅), Best bet = 2 points (⭐)")

    # Create a custom display with logos
    st.markdown("### Team Rankings")

    # Add header row
    header_cols = st.columns([0.5, 2] + [1] * len(all_pickers))
    with header_cols[1]:
        st.markdown("**Team**")
    for i, picker in enumerate(all_pickers):
        with header_cols[i + 2]:
            st.markdown(f"**{picker}**")

    st.markdown(
        "<hr style='margin: 8px 0; border: none; height: 2px; background-color: rgba(128, 128, 128, 0.5);'>",
        unsafe_allow_html=True,
    )

    # Display each team with logo and picker data
    for _, row in df.iterrows():
        team_name = row["Team"]
        # Extract just the team abbreviation (before the parentheses)
        team_abbrev = team_name.split(" (")[0] if " (" in team_name else team_name
        team_logo = get_team_logo(team_abbrev)

        # Create columns for this row
        cols = st.columns([0.5, 2] + [1] * len(all_pickers))

        # Logo column
        with cols[0]:
            if team_logo:
                st.image(team_logo, width=25)

        # Team name column
        with cols[1]:
            st.markdown(f"**{team_name}**")

        # Picker columns
        for i, picker in enumerate(all_pickers):
            with cols[i + 2]:
                pick_value = row[picker]
                if pick_value:
                    st.markdown(
                        f"<div style='text-align: center; font-size: 18px;'>{pick_value}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        "<div style='text-align: center;'>—</div>",
                        unsafe_allow_html=True,
                    )

        # Add a subtle divider
        st.markdown(
            "<hr style='margin: 8px 0; border: none; height: 1px; background-color: rgba(128, 128, 128, 0.3);'>",
            unsafe_allow_html=True,
        )

    # Summary statistics
    st.subheader("📊 Summary")

    total_picks = len(picks_data)
    total_best_bets = len([p for p in picks_data if p.get("pick_type") == "best_bet"])
    unique_pickers = len(set(p["picker"] for p in picks_data))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Picks", total_picks)
    with col2:
        st.metric("Best Bets", total_best_bets)
    with col3:
        st.metric("Active Pickers", unique_pickers)

elif "picks_data" in st.session_state and not st.session_state.picks_data:
    st.info(f"No picks found for Week {week}")

else:
    st.info("👆 Click 'Load Picks' to view picks for the selected week")

# Add a note about the data source
st.caption("📊 Picks data loaded from Supabase database")
