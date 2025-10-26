import os
import sys

import pandas as pd
import streamlit as st

# Add both parent directory and src directory to path for Streamlit Cloud compatibility
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from g_nfl import CUR_WEEK
from g_nfl.modelling.utils import get_week_spreads
from g_nfl.utils.config import CUR_SEASON
from g_nfl.utils.database import PicksDatabase
from g_nfl.utils.teams import standardize_teams
from g_nfl.utils.web_app import get_picks_data, get_team_logo

st.set_page_config(page_title="View Picks - no-homers", layout="wide")

st.title("🔍 View Picks by Week")

# Add controls for selecting week and picker
col_spacer1, col_controls, col_spacer2 = st.columns([2, 6, 2])

# Hardcoded default week for deployment
DEFAULT_WEEK = 8

with col_controls:
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        # Use current_season from main page if available
        default_season_index = len(list(range(2020, CUR_SEASON + 1))) - 1
        if "current_season" in st.session_state:
            try:
                default_season_index = list(range(2020, CUR_SEASON + 1)).index(
                    st.session_state.current_season
                )
            except ValueError:
                pass

        season = st.selectbox(
            "Select Season",
            list(range(2020, CUR_SEASON + 1)),
            index=default_season_index,
            key="view_season",
        )

    with col2:
        # Use current_week from main page if available, otherwise default to week 8
        default_week_index = DEFAULT_WEEK - 1
        if "current_week" in st.session_state:
            try:
                default_week_index = list(range(1, 19)).index(
                    st.session_state.current_week
                )
            except ValueError:
                pass

        week = st.selectbox(
            "Select Week", list(range(1, 19)), index=default_week_index, key="view_week"
        )

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

            # Load pool spreads from database instead of nfl_data_py
            try:
                db = PicksDatabase()
                # Direct query to pool_spreads table
                query = (
                    db.client.table("pool_spreads")
                    .select("*")
                    .eq("season", season)
                    .eq("week", week)
                )
                result = query.execute()
                pool_spreads = result.data

                # Convert pool spreads to DataFrame with game info
                if pool_spreads:
                    games_data = []
                    for spread_entry in pool_spreads:
                        game_id = spread_entry["game_id"]
                        # Parse game_id format: 2024_08_CHI_WAS
                        parts = game_id.split("_")
                        if len(parts) >= 4:
                            _, _, away_team, home_team = (
                                parts[0],
                                parts[1],
                                parts[2],
                                parts[3],
                            )
                            games_data.append(
                                {
                                    "game_id": game_id,
                                    "away_team": away_team,
                                    "home_team": home_team,
                                    "spread_line": spread_entry.get("spread"),
                                }
                            )

                    games_df = pd.DataFrame(games_data)
                    st.session_state.games_data_view = games_df
                else:
                    st.session_state.games_data_view = pd.DataFrame()
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

    # Get all unique pickers
    all_pickers = sorted(list(set(pick["picker"] for pick in picks_data)))

    # Separate picks by type
    regular_picks = [
        p for p in picks_data if p.get("pick_type") not in ["survivor", "underdog"]
    ]
    survivor_picks = [p for p in picks_data if p.get("pick_type") == "survivor"]
    underdog_picks = [p for p in picks_data if p.get("pick_type") == "underdog"]

    def create_special_table_display(pick_data_list, title, emoji, description):
        """Create a table display for survivor/underdog picks"""
        if not pick_data_list:
            st.info(f"No {title.lower()} picks found for this week")
            return

        st.subheader(f"{emoji} {title}")
        st.caption(description)

        # Get teams for this pick type
        teams_in_picks = sorted(
            list(set(pick["team_picked"] for pick in pick_data_list))
        )

        # Create team-picker matrix
        team_data = []
        for team in teams_in_picks:
            row_data = {"Team": team}

            for picker in all_pickers:
                # Find picks for this team by this picker
                team_picks = [
                    p
                    for p in pick_data_list
                    if p["team_picked"] == team and p["picker"] == picker
                ]

                if team_picks:
                    row_data[picker] = "✅"
                else:
                    row_data[picker] = ""

            team_data.append(row_data)

        # Sort alphabetically by team name
        team_data.sort(key=lambda x: x["Team"])

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
        for row_data in team_data:
            team_name = row_data["Team"]
            team_logo = get_team_logo(team_name)

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
                    pick_value = row_data[picker]
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

    # Create regular picks table by game with net scores
    if regular_picks:
        # Get games data if available
        if not games_df.empty:
            # Create game-based view
            game_data = []

            for _, game in games_df.iterrows():
                # Get team names from game data (already standardized in database)
                away_team = game["away_team"]
                home_team = game["home_team"]
                spread_line = game.get("spread_line", None)

                # Calculate points for each team
                away_points = 0
                home_points = 0
                away_best_bets = 0
                home_best_bets = 0

                for picker in all_pickers:
                    # Check away team picks
                    away_team_picks = [
                        p
                        for p in regular_picks
                        if p["team_picked"] == away_team and p["picker"] == picker
                    ]

                    if away_team_picks:
                        has_best_bet = any(
                            pick.get("pick_type") == "best_bet"
                            for pick in away_team_picks
                        )
                        if has_best_bet:
                            away_points += 2
                            away_best_bets += 1
                        else:
                            away_points += 1

                    # Check home team picks
                    home_team_picks = [
                        p
                        for p in regular_picks
                        if p["team_picked"] == home_team and p["picker"] == picker
                    ]

                    if home_team_picks:
                        has_best_bet = any(
                            pick.get("pick_type") == "best_bet"
                            for pick in home_team_picks
                        )
                        if has_best_bet:
                            home_points += 2
                            home_best_bets += 1
                        else:
                            home_points += 1

                # Calculate net score (positive = home favored, negative = away favored)
                net_score = home_points - away_points

                # Determine consensus team and total picks for that team
                if net_score > 0:
                    consensus_team = home_team
                    consensus_points = home_points
                    consensus_best_bets = home_best_bets
                    is_consensus_home = True
                elif net_score < 0:
                    consensus_team = away_team
                    consensus_points = away_points
                    consensus_best_bets = away_best_bets
                    is_consensus_home = False
                else:
                    consensus_team = "EVEN"
                    consensus_points = 0
                    consensus_best_bets = 0
                    is_consensus_home = None

                # Format game matchup with consensus team first
                if consensus_team == "EVEN":
                    # If even, use traditional away at home format
                    if spread_line is not None:
                        # Spread line is for home team, so flip sign for away team
                        away_spread = -spread_line
                        if away_spread >= 0:
                            matchup = (
                                f"{away_team} (+{abs(away_spread)}) at {home_team}"
                            )
                        else:
                            matchup = f"{away_team} ({away_spread}) at {home_team}"
                    else:
                        matchup = f"{away_team} at {home_team}"
                else:
                    # Put consensus team first
                    if is_consensus_home:
                        # Home team is consensus - use "vs"
                        other_team = away_team
                        if spread_line is not None:
                            # Spread line is for home team (consensus team)
                            if spread_line >= 0:
                                matchup = (
                                    f"{consensus_team} (+{spread_line}) vs {other_team}"
                                )
                            else:
                                matchup = (
                                    f"{consensus_team} ({spread_line}) vs {other_team}"
                                )
                        else:
                            matchup = f"{consensus_team} vs {other_team}"
                    else:
                        # Away team is consensus - use "at"
                        other_team = home_team
                        if spread_line is not None:
                            # Spread line is for home team, flip for away team (consensus)
                            away_spread = -spread_line
                            if away_spread >= 0:
                                matchup = (
                                    f"{consensus_team} (+{away_spread}) at {other_team}"
                                )
                            else:
                                matchup = (
                                    f"{consensus_team} ({away_spread}) at {other_team}"
                                )
                        else:
                            matchup = f"{consensus_team} at {other_team}"

                game_data.append(
                    {
                        "matchup": matchup,
                        "away_team": away_team,
                        "home_team": home_team,
                        "consensus_team": consensus_team,
                        "consensus_points": consensus_points,
                        "consensus_best_bets": consensus_best_bets,
                        "net_score": abs(net_score),
                        "spread_line": spread_line,
                    }
                )

            # Sort by absolute value of net score (strongest consensus first)
            game_data.sort(key=lambda x: x["net_score"], reverse=True)

            # Display the regular picks table
            st.subheader("🏆 Picks by Game (Ranked by Consensus)")
            st.caption(
                "Regular pick = 1 point, Best bet = 2 points | Consensus team shown first"
            )

            # Create DataFrame for easier display
            display_df = pd.DataFrame(
                [
                    {
                        "Game": game["matchup"],
                        "Total Picks": (
                            game["consensus_points"]
                            if game["consensus_team"] != "EVEN"
                            else 0
                        ),
                        "Best Bets": (
                            game["consensus_best_bets"]
                            if game["consensus_team"] != "EVEN"
                            else 0
                        ),
                        "Net Picks": (
                            game["net_score"] if game["consensus_team"] != "EVEN" else 0
                        ),
                    }
                    for game in game_data
                ]
            )

            # Display as streamlit dataframe with custom formatting
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Game": st.column_config.TextColumn("Game", width="large"),
                    "Total Picks": st.column_config.NumberColumn(
                        "Total Picks", width="small"
                    ),
                    "Best Bets": st.column_config.NumberColumn(
                        "Best Bets", width="small"
                    ),
                    "Net Picks": st.column_config.NumberColumn(
                        "Net Picks", width="small"
                    ),
                },
            )

            # Add spacing
            st.markdown("---")

            # Display detailed picker table
            st.subheader("📋 Individual Picks by Game")
            st.caption("✅ = Regular pick | ⭐ = Best bet")

            # Build detailed picker data for DataFrame
            picker_table_data = []
            for game in game_data:
                away_team = game["away_team"]
                home_team = game["home_team"]
                spread_line = game["spread_line"]
                is_consensus_home = (
                    game["consensus_team"] == home_team
                    if game["consensus_team"] != "EVEN"
                    else None
                )

                # Format the team column based on consensus team
                if game["consensus_team"] == "EVEN":
                    # Use traditional away at home format
                    if spread_line is not None:
                        away_spread = -spread_line
                        if away_spread >= 0:
                            team_display = f"{away_team} (+{abs(away_spread)})"
                        else:
                            team_display = f"{away_team} ({away_spread})"
                    else:
                        team_display = f"{away_team}"
                elif is_consensus_home:
                    # Home team is consensus
                    if spread_line is not None:
                        if spread_line >= 0:
                            team_display = f"{home_team} (+{spread_line})"
                        else:
                            team_display = f"{home_team} ({spread_line})"
                    else:
                        team_display = f"{home_team}"
                else:
                    # Away team is consensus
                    if spread_line is not None:
                        away_spread = -spread_line
                        if away_spread >= 0:
                            team_display = f"{away_team} (+{away_spread})"
                        else:
                            team_display = f"{away_team} ({away_spread})"
                    else:
                        team_display = f"{away_team}"

                row_data = {"Team": team_display}

                for picker in all_pickers:
                    # Check picks for both teams
                    away_picks = [
                        p
                        for p in regular_picks
                        if p["team_picked"] == away_team and p["picker"] == picker
                    ]
                    home_picks = [
                        p
                        for p in regular_picks
                        if p["team_picked"] == home_team and p["picker"] == picker
                    ]

                    if away_picks:
                        has_best_bet = any(
                            pick.get("pick_type") == "best_bet" for pick in away_picks
                        )
                        row_data[picker] = "⭐" if has_best_bet else "✅"
                    elif home_picks:
                        has_best_bet = any(
                            pick.get("pick_type") == "best_bet" for pick in home_picks
                        )
                        row_data[picker] = "⭐" if has_best_bet else "✅"
                    else:
                        row_data[picker] = "—"

                picker_table_data.append(row_data)

            # Create DataFrame for picker table
            picker_df = pd.DataFrame(picker_table_data)

            # Display as streamlit dataframe
            st.dataframe(
                picker_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Team": st.column_config.TextColumn(
                        "Team", width="medium", pinned=True
                    ),
                    **{
                        picker: st.column_config.TextColumn(picker, width="small")
                        for picker in all_pickers
                    },
                },
            )
        else:
            # Fallback to team view if no games data available
            st.warning("Games data not available. Showing team-based view instead.")
            all_teams = sorted(list(set(pick["team_picked"] for pick in regular_picks)))

            # Create team-picker matrix with points
            team_data = []
            for team in all_teams:
                row_data = {"Team": team}
                total_points = 0

                for picker in all_pickers:
                    # Find picks for this team by this picker
                    team_picks = [
                        p
                        for p in regular_picks
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
                row_data["Team_Logo"] = (
                    team_logo_url  # Store logo URL for potential use
                )
                row_data["_sort_points"] = total_points  # Hidden field for sorting
                team_data.append(row_data)

            # Sort by total points descending
            team_data.sort(key=lambda x: x["_sort_points"], reverse=True)

            # Display the regular picks table
            st.subheader("🏆 Team Picks Ranked by Points")
            st.caption("Regular pick = 1 point (✅), Best bet = 2 points (⭐)")

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
            for row_data in team_data:
                team_name = row_data["Team"]
                # Extract just the team abbreviation (before the parentheses)
                team_abbrev = (
                    team_name.split(" (")[0] if " (" in team_name else team_name
                )
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
                        pick_value = row_data[picker]
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

    # Add spacing between tables
    st.markdown("---")

    # Display survivor picks table
    create_special_table_display(
        survivor_picks, "Survivor Picks", "💀", "One survivor pick per picker per week"
    )

    # Add spacing between tables
    st.markdown("---")

    # Display underdog picks table
    create_special_table_display(
        underdog_picks, "Underdog Picks", "🐶", "One underdog pick per picker per week"
    )

    # Summary statistics
    st.markdown("---")
    st.subheader("📊 Summary")

    total_picks = len(picks_data)
    total_best_bets = len([p for p in picks_data if p.get("pick_type") == "best_bet"])
    total_survivor = len(survivor_picks)
    total_underdog = len(underdog_picks)
    unique_pickers = len(set(p["picker"] for p in picks_data))

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Picks", total_picks)
    with col2:
        st.metric("Best Bets", total_best_bets)
    with col3:
        st.metric("Survivor", total_survivor)
    with col4:
        st.metric("Underdog", total_underdog)
    with col5:
        st.metric("Active Pickers", unique_pickers)

elif "picks_data" in st.session_state and not st.session_state.picks_data:
    st.info(f"No picks found for Week {week}")

else:
    st.info("👆 Click 'Load Picks' to view picks for the selected week")

# Add a note about the data source
st.caption("📊 Picks data loaded from Supabase database")
