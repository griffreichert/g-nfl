import os
import subprocess
import sys

import pandas as pd
import streamlit as st

# Add both parent directory and src directory to path for Streamlit Cloud compatibility
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from g_nfl.modelling.utils import get_week_spreads
from g_nfl.utils.config import CUR_SEASON
from g_nfl.utils.web_app import (
    get_all_lines_data,
    get_team_logo,
    load_existing_picks,
    save_picks_data,
)


def run_app():
    """Entry point for running the Streamlit app via poetry"""
    app_path = os.path.join(os.path.dirname(__file__), "main.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path])


st.set_page_config(page_title="Make Picks - no-homers", layout="wide")

# Initialize session state for picks
if "picks" not in st.session_state:
    st.session_state.picks = {}

# Initialize session state for survivor pick
if "survivor_pick" not in st.session_state:
    st.session_state.survivor_pick = None

# Initialize session state for underdog pick
if "underdog_pick" not in st.session_state:
    st.session_state.underdog_pick = None


def get_next_pick_state(current_pick, team_name):
    """Get the next state when clicking a team button

    States cycle: unselected -> regular -> best_bet -> unselected
    """
    if not current_pick or current_pick.get("team_picked") != team_name:
        # First click: select as regular
        return {"team_picked": team_name, "pick_type": "regular"}

    current_type = current_pick.get("pick_type", "regular")
    if current_type == "regular":
        # Second click: upgrade to best bet
        return {"team_picked": team_name, "pick_type": "best_bet"}
    elif current_type == "best_bet":
        # Third click: unselect
        return None
    else:
        # Default: select as regular
        return {"team_picked": team_name, "pick_type": "regular"}


def get_button_style(is_selected, pick_type, is_disabled):
    """Get button type for styling"""
    if is_disabled:
        return "secondary"
    elif not is_selected:
        return "secondary"
    else:
        return "primary"


def get_button_label(team_name, pick_type):
    """Get button label with pick type indicator"""
    if pick_type == "best_bet":
        return f"⭐ {team_name}"
    else:
        return team_name


st.title("🎯 Make Picks")

# Sidebar info
st.sidebar.markdown("## 📋 Pick Rules")
st.sidebar.markdown(
    """
- **Regular picks**: 1 point each
- **Best bets** ⭐: 2 points each
- **Survivor** 💀: One per week
- **Underdog** 🐶: One per week
- **Maximum**: 6 regular/best bet picks
"""
)

st.sidebar.markdown("---")
if st.sidebar.button("ℹ️ About"):
    st.sidebar.info(
        """
    **no-homers**

    NFL picks competition with survivor and underdog pools.
    Data saved to cloud database and persists between sessions.

    Made with ❤️ and Streamlit
    """
    )

# Custom CSS for different button states
st.markdown(
    """
<style>
/* Regular selected (green) */
div.stButton > button[kind="primary"] {
    background-color: #28a745 !important;
    border-color: #28a745 !important;
    color: white !important;
}
div.stButton > button[kind="primary"]:hover {
    background-color: #218838 !important;
    border-color: #1e7e34 !important;
}

/* Best bet (light purple) - using custom data attribute */
div.stButton > button[data-best-bet="true"] {
    background-color: #b19cd9 !important;
    border-color: #b19cd9 !important;
    color: #ffffff !important;
    font-weight: bold !important;
}
div.stButton > button[data-best-bet="true"]:hover {
    background-color: #9d84d1 !important;
    border-color: #9d84d1 !important;
}

/* Disabled buttons */
div.stButton > button:disabled {
    background-color: #6c757d !important;
    border-color: #6c757d !important;
    color: #ffffff !important;
    opacity: 0.6 !important;
    cursor: not-allowed !important;
}
div.stButton > button:disabled:hover {
    background-color: #6c757d !important;
    border-color: #6c757d !important;
    color: #ffffff !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# Main controls
st.markdown("### 🎮 Select Your Week & Identity")

col1, col2, col3, col4 = st.columns([1, 1, 2, 1])

with col1:
    season = st.selectbox(
        "Season",
        list(range(2020, CUR_SEASON + 1)),
        index=len(list(range(2020, CUR_SEASON + 1))) - 1,
    )

with col2:
    week = st.selectbox("Week", list(range(1, 19)), index=0)

with col3:
    picker = st.selectbox(
        "Picker",
        [None] + ["Griffin", "Harry", "Ben", "Chuck", "Hunter", "Jacko"],
        index=0,
        format_func=lambda x: "👤 Choose your name..." if x is None else f"👤 {x}",
    )

with col4:
    st.write("")  # Add some vertical spacing
    load_button = st.button("🔄 Load Games", type="primary")

# Auto-load picks when picker changes (even without clicking Load Games)
if (
    "games_data" in st.session_state
    and picker
    and (
        "last_picker" not in st.session_state or st.session_state.last_picker != picker
    )
):
    existing_picks = load_existing_picks(
        st.session_state.current_season, st.session_state.current_week, picker
    )

    # Separate special picks from regular picks
    regular_picks = {}
    survivor_pick = None
    underdog_pick = None

    for game_id, pick_data in existing_picks.items():
        if isinstance(pick_data, dict):
            if pick_data.get("pick_type") == "survivor":
                survivor_pick = pick_data.get("team_picked")
            elif pick_data.get("pick_type") == "underdog":
                underdog_pick = pick_data.get("team_picked")
            else:
                regular_picks[game_id] = pick_data
        else:
            regular_picks[game_id] = pick_data

    st.session_state.picks = regular_picks
    st.session_state.survivor_pick = survivor_pick
    st.session_state.underdog_pick = underdog_pick
    st.session_state.last_picker = picker

    total_picks = (
        len(regular_picks) + (1 if survivor_pick else 0) + (1 if underdog_pick else 0)
    )
    if total_picks > 0:
        st.info(f"✅ Loaded {total_picks} existing picks for {picker}")
        # Debug info
        if regular_picks:
            st.expander("🔍 Debug: Loaded picks").write(regular_picks)
    st.rerun()

if load_button or "games_data" not in st.session_state:
    try:
        with st.spinner("Loading NFL games data..."):
            # Always use database data (deployment-ready)
            try:
                # Check environment variables
                import os

                from g_nfl.utils.database import MarketLinesDatabase

                supabase_url = os.getenv("SUPABASE_URL")
                supabase_key = os.getenv("SUPABASE_ANON_KEY")

                # Debug: Show what we found
                st.write("🔍 Debug environment variables:")
                st.write(f"SUPABASE_URL found: {'✅' if supabase_url else '❌'}")
                st.write(f"SUPABASE_ANON_KEY found: {'✅' if supabase_key else '❌'}")

                # Try streamlit secrets as fallback
                if not supabase_url or not supabase_key:
                    try:
                        if not supabase_url:
                            supabase_url = st.secrets["SUPABASE_URL"]
                        if not supabase_key:
                            supabase_key = st.secrets["SUPABASE_ANON_KEY"]
                        st.info("✅ Found credentials in Streamlit secrets")
                    except:
                        st.error("❌ Missing environment variables and secrets")
                        st.markdown(
                            """
                        **Required environment variables:**
                        - `SUPABASE_URL`: Your Supabase project URL
                        - `SUPABASE_ANON_KEY`: Your Supabase anon/public key

                        Set these in your Streamlit Cloud app settings under 'Secrets management'.
                        """
                        )
                        st.stop()

                market_db = MarketLinesDatabase()
                market_lines = market_db.get_market_lines(season, week)
            except Exception as db_error:
                st.error(f"❌ Database error: {str(db_error)}")
                st.markdown(f"**Error details:** {type(db_error).__name__}")
                st.stop()

            if not market_lines:
                st.error(f"❌ No market data found for Week {week}, Season {season}")
                st.markdown(
                    """
                **To fix this:**
                1. Run locally: `python scripts/update_market_lines.py --season {season} --week {week}`
                2. Or try a different week that has data

                **Note:** This app requires market data to be pre-loaded into the database for deployment.
                """.format(
                        season=season, week=week
                    )
                )
                st.stop()

            st.success(f"✅ Found {len(market_lines)} games in database")

            # Convert market lines to DataFrame
            games_data = []
            for line in market_lines:
                game_id = line["game_id"]
                # Parse game_id: 2025_01_KC_LAC
                parts = game_id.split("_")
                if len(parts) >= 4:
                    away_team = parts[2]
                    home_team = parts[3]
                    games_data.append(
                        {
                            "away_team": away_team,
                            "home_team": home_team,
                            "spread_line": line.get("spread"),
                            "total_line": line.get("total"),
                        }
                    )

            games_df = pd.DataFrame(games_data)
            # Use a composite index similar to nfl_data format
            games_df.index = [
                f"{season}_{week}_{row['away_team']}_{row['home_team']}"
                for _, row in games_df.iterrows()
            ]
            data_source = "database"

            st.session_state.games_data = games_df
            st.session_state.current_week = week
            st.session_state.current_season = season
            st.session_state.data_source = data_source

            # Load market lines and pool spreads
            lines_data = get_all_lines_data(season, week)
            st.session_state.lines_data = lines_data

            # Show data source info
            st.info("📊 Using stored market data from database")

            # Load existing picks if picker is selected and week/season changed
            if (
                "last_week_season_picker" not in st.session_state
                or st.session_state.last_week_season_picker != (week, season, picker)
            ):
                if picker:  # Only load picks if a picker is selected
                    existing_picks = load_existing_picks(season, week, picker)

                    # Separate special picks from regular picks
                    regular_picks = {}
                    survivor_pick = None
                    underdog_pick = None

                    for game_id, pick_data in existing_picks.items():
                        if isinstance(pick_data, dict):
                            if pick_data.get("pick_type") == "survivor":
                                survivor_pick = pick_data.get("team_picked")
                            elif pick_data.get("pick_type") == "underdog":
                                underdog_pick = pick_data.get("team_picked")
                            else:
                                regular_picks[game_id] = pick_data
                        else:
                            regular_picks[game_id] = pick_data

                    st.session_state.picks = regular_picks
                    st.session_state.survivor_pick = survivor_pick
                    st.session_state.underdog_pick = underdog_pick

                    total_picks = (
                        len(regular_picks)
                        + (1 if survivor_pick else 0)
                        + (1 if underdog_pick else 0)
                    )
                    if total_picks > 0:
                        st.info(f"✅ Loaded {total_picks} existing picks for {picker}")
                else:
                    st.session_state.picks = {}
                    st.session_state.survivor_pick = None
                    st.session_state.underdog_pick = None

                st.session_state.last_week_season_picker = (week, season, picker)
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.stop()


if "games_data" in st.session_state:
    games_df = st.session_state.games_data

    if not games_df.empty:
        # Show instruction if no picker selected
        if not picker:
            st.warning("👆 Please select your name above to start making picks")
            st.stop()

        # Games section header
        st.markdown("---")
        st.markdown(f"### 🏈 Week {st.session_state.current_week} Games")

        # Debug: Show data source and first few games
        if st.checkbox("🔍 Debug: Show loaded games"):
            st.write(
                f"**Data source**: {st.session_state.get('data_source', 'unknown')}"
            )
            st.write("**First 5 games loaded:**")
            for game_id in list(games_df.index)[:5]:
                game = games_df.loc[game_id]
                st.text(f"{game['away_team']} @ {game['home_team']} (ID: {game_id})")
            st.write(f"**Total games**: {len(games_df)}")

        # Show current pick counts
        if (
            st.session_state.picks
            or st.session_state.survivor_pick
            or st.session_state.underdog_pick
        ):
            total_regular = len(st.session_state.picks)
            has_survivor = "✅" if st.session_state.survivor_pick else "⬜"
            has_underdog = "✅" if st.session_state.underdog_pick else "⬜"

            st.info(
                f"**Current Picks**: {total_regular}/6 regular • {has_survivor} survivor • {has_underdog} underdog"
            )

            # Debug: Show games available vs picks made
            if st.checkbox("🔍 Debug: Show game ID matching"):
                st.write("**Available games:**")
                for game_id in list(games_df.index)[:5]:  # First 5 games
                    st.text(f"Game: {game_id}")
                st.write("**Your picks:**")
                for pick_id in list(st.session_state.picks.keys())[:5]:  # First 5 picks
                    st.text(f"Pick: {pick_id}")
                st.write("**Matches:**")
                for pick_id, pick_data in st.session_state.picks.items():
                    match = "✅" if pick_id in games_df.index else "❌"
                    st.text(f"{match} {pick_id} -> {pick_data.get('team_picked')}")

        # Create centered container with limited width
        col_spacer1, col_content, col_spacer2 = st.columns([1, 8, 1])

        with col_content:
            # Header row
            header_col1, header_col2, header_col3 = st.columns([2, 2, 2])
            with header_col1:
                st.markdown("**🏃 Away Team**")
            with header_col2:
                st.markdown("**📊 Lines (Pool / Market / Total)**")
            with header_col3:
                st.markdown("**🏠 Home Team**")
            st.markdown("---")

            for _, game in games_df.iterrows():
                game_id = game.name  # This is the game_id from the index

                with st.container():
                    col1, col2, col3 = st.columns([2, 2, 2])

                    # Check pick states for this game
                    max_picks_reached = len(st.session_state.picks) >= 6
                    game_has_selection = game_id in st.session_state.picks

                    current_pick = st.session_state.picks.get(game_id, {})
                    if isinstance(current_pick, str):
                        # Handle legacy format
                        current_pick = {
                            "team_picked": current_pick,
                            "pick_type": "regular",
                        }

                    home_selected = current_pick.get("team_picked") == game["home_team"]
                    away_selected = current_pick.get("team_picked") == game["away_team"]
                    home_pick_type = (
                        current_pick.get("pick_type", "regular")
                        if home_selected
                        else None
                    )
                    away_pick_type = (
                        current_pick.get("pick_type", "regular")
                        if away_selected
                        else None
                    )

                    with col1:
                        # Away team button
                        away_disabled = (
                            (max_picks_reached and not away_selected)
                            or home_selected
                            or not picker
                        )  # Disable if no picker selected

                        away_logo = get_team_logo(game["away_team"])
                        button_type = get_button_style(
                            away_selected, away_pick_type, away_disabled
                        )
                        button_label = get_button_label(
                            game["away_team"], away_pick_type
                        )

                        if away_logo:
                            col_logo, col_button, col_special = st.columns([1, 2, 1])
                            with col_logo:
                                st.image(away_logo, width=35)
                            with col_button:
                                if st.button(
                                    button_label,
                                    key=f"away_{game_id}",
                                    type=button_type,
                                    disabled=away_disabled,
                                ):
                                    next_state = get_next_pick_state(
                                        current_pick, game["away_team"]
                                    )
                                    if next_state is None:
                                        # Remove the pick
                                        if game_id in st.session_state.picks:
                                            del st.session_state.picks[game_id]
                                    else:
                                        # Add spread info
                                        next_state["spread"] = game.get("spread_line")
                                        st.session_state.picks[game_id] = next_state
                                    st.rerun()
                            with col_special:
                                # Put both buttons in a single row
                                col_survivor, col_underdog = st.columns(2)

                                with col_survivor:
                                    # Survivor pick button
                                    survivor_disabled = not picker or (
                                        st.session_state.survivor_pick is not None
                                        and st.session_state.survivor_pick
                                        != game["away_team"]
                                    )
                                    survivor_selected = (
                                        st.session_state.survivor_pick
                                        == game["away_team"]
                                    )

                                    survivor_button_type = (
                                        "primary" if survivor_selected else "secondary"
                                    )
                                    if st.button(
                                        "💀",
                                        key=f"survivor_away_{game_id}",
                                        type=survivor_button_type,
                                        disabled=survivor_disabled,
                                        help="Survivor pick",
                                    ):
                                        if (
                                            st.session_state.survivor_pick
                                            == game["away_team"]
                                        ):
                                            # Deselect survivor pick
                                            st.session_state.survivor_pick = None
                                        else:
                                            # Select survivor pick
                                            st.session_state.survivor_pick = game[
                                                "away_team"
                                            ]
                                        st.rerun()

                                with col_underdog:
                                    # Underdog pick button
                                    underdog_disabled = not picker or (
                                        st.session_state.underdog_pick is not None
                                        and st.session_state.underdog_pick
                                        != game["away_team"]
                                    )
                                    underdog_selected = (
                                        st.session_state.underdog_pick
                                        == game["away_team"]
                                    )

                                    underdog_button_type = (
                                        "primary" if underdog_selected else "secondary"
                                    )
                                    if st.button(
                                        "🐶",
                                        key=f"underdog_away_{game_id}",
                                        type=underdog_button_type,
                                        disabled=underdog_disabled,
                                        help="Underdog pick",
                                    ):
                                        if (
                                            st.session_state.underdog_pick
                                            == game["away_team"]
                                        ):
                                            # Deselect underdog pick
                                            st.session_state.underdog_pick = None
                                        else:
                                            # Select underdog pick
                                            st.session_state.underdog_pick = game[
                                                "away_team"
                                            ]
                                        st.rerun()
                        else:
                            col_button, col_special = st.columns([3, 1])
                            with col_button:
                                if st.button(
                                    button_label,
                                    key=f"away_{game_id}",
                                    type=button_type,
                                    disabled=away_disabled,
                                ):
                                    next_state = get_next_pick_state(
                                        current_pick, game["away_team"]
                                    )
                                    if next_state is None:
                                        # Remove the pick
                                        if game_id in st.session_state.picks:
                                            del st.session_state.picks[game_id]
                                    else:
                                        # Add spread info
                                        next_state["spread"] = game.get("spread_line")
                                        st.session_state.picks[game_id] = next_state
                                    st.rerun()
                            with col_special:
                                # Put both buttons in a single row
                                col_survivor, col_underdog = st.columns(2)

                                with col_survivor:
                                    # Survivor pick button
                                    survivor_disabled = not picker or (
                                        st.session_state.survivor_pick is not None
                                        and st.session_state.survivor_pick
                                        != game["away_team"]
                                    )
                                    survivor_selected = (
                                        st.session_state.survivor_pick
                                        == game["away_team"]
                                    )

                                    survivor_button_type = (
                                        "primary" if survivor_selected else "secondary"
                                    )
                                    if st.button(
                                        "💀",
                                        key=f"survivor_away_nologo_{game_id}",
                                        type=survivor_button_type,
                                        disabled=survivor_disabled,
                                        help="Survivor pick",
                                    ):
                                        if (
                                            st.session_state.survivor_pick
                                            == game["away_team"]
                                        ):
                                            # Deselect survivor pick
                                            st.session_state.survivor_pick = None
                                        else:
                                            # Select survivor pick
                                            st.session_state.survivor_pick = game[
                                                "away_team"
                                            ]
                                        st.rerun()

                                with col_underdog:
                                    # Underdog pick button
                                    underdog_disabled = not picker or (
                                        st.session_state.underdog_pick is not None
                                        and st.session_state.underdog_pick
                                        != game["away_team"]
                                    )
                                    underdog_selected = (
                                        st.session_state.underdog_pick
                                        == game["away_team"]
                                    )

                                    underdog_button_type = (
                                        "primary" if underdog_selected else "secondary"
                                    )
                                    if st.button(
                                        "🐶",
                                        key=f"underdog_away_nologo_{game_id}",
                                        type=underdog_button_type,
                                        disabled=underdog_disabled,
                                        help="Underdog pick",
                                    ):
                                        if (
                                            st.session_state.underdog_pick
                                            == game["away_team"]
                                        ):
                                            # Deselect underdog pick
                                            st.session_state.underdog_pick = None
                                        else:
                                            # Select underdog pick
                                            st.session_state.underdog_pick = game[
                                                "away_team"
                                            ]
                                        st.rerun()

                    with col2:
                        # Get line data for this game
                        lines = st.session_state.get("lines_data", {}).get(game_id, {})

                        # Pool spread
                        pool_spread = lines.get("pool_spread")
                        if pool_spread is not None:
                            pool_text = f"{pool_spread:+g}"
                        else:
                            pool_text = "TBD"

                        # Market spread (fallback to nfl_data)
                        market_spread = lines.get("market_spread")
                        if market_spread is None and pd.notna(game["spread_line"]):
                            market_spread = game["spread_line"]

                        if market_spread is not None:
                            market_spread_text = f"{market_spread:+g}"
                        else:
                            market_spread_text = "N/A"

                        # Market total (fallback to nfl_data)
                        market_total = lines.get("market_total")
                        if market_total is None and pd.notna(game["total_line"]):
                            market_total = game["total_line"]

                        if market_total is not None:
                            market_total_text = f"{market_total:g}"
                        else:
                            market_total_text = "N/A"

                        # Display: Pool / Market / Total on one line with bold pool
                        st.markdown(
                            f"**{pool_text}** / {market_spread_text} / {market_total_text}"
                        )

                    with col3:
                        # Home team button
                        home_disabled = (
                            (max_picks_reached and not home_selected)
                            or away_selected
                            or not picker
                        )  # Disable if no picker selected

                        home_logo = get_team_logo(game["home_team"])
                        button_type = get_button_style(
                            home_selected, home_pick_type, home_disabled
                        )
                        button_label = get_button_label(
                            game["home_team"], home_pick_type
                        )

                        if home_logo:
                            col_logo, col_button, col_special = st.columns([1, 2, 1])
                            with col_logo:
                                st.image(home_logo, width=35)
                            with col_button:
                                if st.button(
                                    button_label,
                                    key=f"home_{game_id}",
                                    type=button_type,
                                    disabled=home_disabled,
                                ):
                                    next_state = get_next_pick_state(
                                        current_pick, game["home_team"]
                                    )
                                    if next_state is None:
                                        # Remove the pick
                                        if game_id in st.session_state.picks:
                                            del st.session_state.picks[game_id]
                                    else:
                                        # Add spread info
                                        next_state["spread"] = game.get("spread_line")
                                        st.session_state.picks[game_id] = next_state
                                    st.rerun()
                            with col_special:
                                # Put both buttons in a single row
                                col_survivor, col_underdog = st.columns(2)

                                with col_survivor:
                                    # Survivor pick button
                                    survivor_disabled = not picker or (
                                        st.session_state.survivor_pick is not None
                                        and st.session_state.survivor_pick
                                        != game["home_team"]
                                    )
                                    survivor_selected = (
                                        st.session_state.survivor_pick
                                        == game["home_team"]
                                    )

                                    survivor_button_type = (
                                        "primary" if survivor_selected else "secondary"
                                    )
                                    if st.button(
                                        "💀",
                                        key=f"survivor_home_{game_id}",
                                        type=survivor_button_type,
                                        disabled=survivor_disabled,
                                        help="Survivor pick",
                                    ):
                                        if (
                                            st.session_state.survivor_pick
                                            == game["home_team"]
                                        ):
                                            # Deselect survivor pick
                                            st.session_state.survivor_pick = None
                                        else:
                                            # Select survivor pick
                                            st.session_state.survivor_pick = game[
                                                "home_team"
                                            ]
                                        st.rerun()

                                with col_underdog:
                                    # Underdog pick button
                                    underdog_disabled = not picker or (
                                        st.session_state.underdog_pick is not None
                                        and st.session_state.underdog_pick
                                        != game["home_team"]
                                    )
                                    underdog_selected = (
                                        st.session_state.underdog_pick
                                        == game["home_team"]
                                    )

                                    underdog_button_type = (
                                        "primary" if underdog_selected else "secondary"
                                    )
                                    if st.button(
                                        "🐶",
                                        key=f"underdog_home_{game_id}",
                                        type=underdog_button_type,
                                        disabled=underdog_disabled,
                                        help="Underdog pick",
                                    ):
                                        if (
                                            st.session_state.underdog_pick
                                            == game["home_team"]
                                        ):
                                            # Deselect underdog pick
                                            st.session_state.underdog_pick = None
                                        else:
                                            # Select underdog pick
                                            st.session_state.underdog_pick = game[
                                                "home_team"
                                            ]
                                        st.rerun()
                        else:
                            col_button, col_special = st.columns([3, 1])
                            with col_button:
                                if st.button(
                                    button_label,
                                    key=f"home_{game_id}",
                                    type=button_type,
                                    disabled=home_disabled,
                                ):
                                    next_state = get_next_pick_state(
                                        current_pick, game["home_team"]
                                    )
                                    if next_state is None:
                                        # Remove the pick
                                        if game_id in st.session_state.picks:
                                            del st.session_state.picks[game_id]
                                    else:
                                        # Add spread info
                                        next_state["spread"] = game.get("spread_line")
                                        st.session_state.picks[game_id] = next_state
                                    st.rerun()
                            with col_special:
                                # Put both buttons in a single row
                                col_survivor, col_underdog = st.columns(2)

                                with col_survivor:
                                    # Survivor pick button
                                    survivor_disabled = not picker or (
                                        st.session_state.survivor_pick is not None
                                        and st.session_state.survivor_pick
                                        != game["home_team"]
                                    )
                                    survivor_selected = (
                                        st.session_state.survivor_pick
                                        == game["home_team"]
                                    )

                                    survivor_button_type = (
                                        "primary" if survivor_selected else "secondary"
                                    )
                                    if st.button(
                                        "💀",
                                        key=f"survivor_home_nologo_{game_id}",
                                        type=survivor_button_type,
                                        disabled=survivor_disabled,
                                        help="Survivor pick",
                                    ):
                                        if (
                                            st.session_state.survivor_pick
                                            == game["home_team"]
                                        ):
                                            # Deselect survivor pick
                                            st.session_state.survivor_pick = None
                                        else:
                                            # Select survivor pick
                                            st.session_state.survivor_pick = game[
                                                "home_team"
                                            ]
                                        st.rerun()

                                with col_underdog:
                                    # Underdog pick button
                                    underdog_disabled = not picker or (
                                        st.session_state.underdog_pick is not None
                                        and st.session_state.underdog_pick
                                        != game["home_team"]
                                    )
                                    underdog_selected = (
                                        st.session_state.underdog_pick
                                        == game["home_team"]
                                    )

                                    underdog_button_type = (
                                        "primary" if underdog_selected else "secondary"
                                    )
                                    if st.button(
                                        "🐶",
                                        key=f"underdog_home_nologo_{game_id}",
                                        type=underdog_button_type,
                                        disabled=underdog_disabled,
                                        help="Underdog pick",
                                    ):
                                        if (
                                            st.session_state.underdog_pick
                                            == game["home_team"]
                                        ):
                                            # Deselect underdog pick
                                            st.session_state.underdog_pick = None
                                        else:
                                            # Select underdog pick
                                            st.session_state.underdog_pick = game[
                                                "home_team"
                                            ]
                                        st.rerun()

                # Use a thinner divider
                st.markdown("---")

        # Show picks summary
        if (
            st.session_state.picks
            or st.session_state.survivor_pick
            or st.session_state.underdog_pick
        ) and picker:
            st.markdown("---")
            st.markdown("### 📋 Pick Summary")
            picks_list = []

            # Add regular/best bet picks
            for game_id, pick_data in st.session_state.picks.items():
                if game_id in games_df.index:
                    game = games_df.loc[game_id]

                    # Handle both old and new pick formats
                    if isinstance(pick_data, str):
                        team = pick_data
                        pick_type = "regular"
                    else:
                        team = pick_data.get("team_picked", "")
                        pick_type = pick_data.get("pick_type", "regular")

                    # Show spread exactly as it comes from get_week_spreads()
                    spread = (
                        f"{game['spread_line']:+.1f}"
                        if pd.notna(game["spread_line"])
                        else "N/A"
                    )

                    # Format pick with type indicator
                    if pick_type == "best_bet":
                        picks_list.append(f"• **{team}** ({spread}) 🌟 **BEST BET**")
                    else:
                        picks_list.append(f"• **{team}** ({spread})")

            # Add survivor pick
            if st.session_state.survivor_pick:
                picks_list.append(
                    f"• **{st.session_state.survivor_pick}** 💀 **SURVIVOR**"
                )

            # Add underdog pick
            if st.session_state.underdog_pick:
                picks_list.append(
                    f"• **{st.session_state.underdog_pick}** 🐶 **UNDERDOG**"
                )

            if picks_list:
                # Display picks in a nice format
                for pick in picks_list:
                    st.markdown(pick)

                st.markdown("---")

                # Action buttons
                col1, col2, col3 = st.columns([2, 1, 2])

                with col1:
                    if st.button(
                        "💾 Save Picks",
                        type="primary",
                        help="Save your picks to the database",
                    ):
                        if not picker:
                            st.error("⚠️ Please select a picker before submitting")
                        elif (
                            st.session_state.picks
                            or st.session_state.survivor_pick
                            or st.session_state.underdog_pick
                        ):
                            # Create combined picks dict including special picks
                            all_picks = dict(
                                st.session_state.picks
                            )  # Copy regular picks

                            # Add survivor pick as a special entry
                            if st.session_state.survivor_pick:
                                survivor_game_id = (
                                    f"survivor_{st.session_state.current_week}"
                                )
                                all_picks[survivor_game_id] = {
                                    "team_picked": st.session_state.survivor_pick,
                                    "pick_type": "survivor",
                                    "spread": None,
                                }

                            # Add underdog pick as a special entry
                            if st.session_state.underdog_pick:
                                underdog_game_id = (
                                    f"underdog_{st.session_state.current_week}"
                                )
                                all_picks[underdog_game_id] = {
                                    "team_picked": st.session_state.underdog_pick,
                                    "pick_type": "underdog",
                                    "spread": None,
                                }

                            filepath = save_picks_data(
                                st.session_state.current_season,
                                st.session_state.current_week,
                                all_picks,
                                picker,
                            )
                            if filepath:
                                st.success(f"✅ Picks saved successfully!")
                            else:
                                st.error("❌ Failed to save picks")
                        else:
                            st.warning("⚠️ No picks to save")

                with col3:
                    if st.button(
                        "🗑️ Clear All", type="secondary", help="Clear all your picks"
                    ):
                        st.session_state.picks = {}
                        st.session_state.survivor_pick = None
                        st.session_state.underdog_pick = None
                        st.success("✅ All picks cleared!")
                        st.rerun()

        # Footer info
        st.markdown("---")
        st.caption(
            f"📊 Showing {len(games_df)} games for Week {st.session_state.current_week} • Season {season}"
        )
    else:
        st.warning("No games found for the selected week and season.")
