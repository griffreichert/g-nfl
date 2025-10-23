import os
import subprocess
import sys

import pandas as pd
import streamlit as st

# Add both parent directory and src directory to path for Streamlit Cloud compatibility
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from g_nfl import CUR_WEEK
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

# Initialize session state for MNF pick
if "mnf_pick" not in st.session_state:
    st.session_state.mnf_pick = None

# Clean up any malformed keys in picks on startup
if "picks" in st.session_state:
    cleaned_picks = {}
    for key, value in st.session_state.picks.items():
        # Only keep properly formatted game_id keys (season_week_away_home format)
        if (
            isinstance(key, str)
            and key.count("_") >= 3
            and not key.endswith("_best")
            and not key.endswith("_regular")
            and not key.endswith("_survivor")
            and not key.endswith("_underdog")
            and not key.endswith("_mnf")
        ):
            cleaned_picks[key] = value
    st.session_state.picks = cleaned_picks


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


def get_next_mnf_pick_state(current_pick, team_name):
    """Get the next state for MNF picks (only regular, no best bet)

    States cycle: unselected -> regular -> unselected
    """
    if not current_pick or current_pick.get("team_picked") != team_name:
        # First click: select as regular
        return {"team_picked": team_name, "pick_type": "regular"}
    else:
        # Second click: unselect
        return None


def get_button_style(is_selected, pick_type, is_disabled):
    """Get button type for styling"""
    if is_disabled:
        return "secondary"
    elif not is_selected:
        return "secondary"
    elif pick_type == "best_bet":
        return "primary"  # We'll handle best_bet with CSS classes
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
- **Monday Night** 🌙: Separate pick, 1 point
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

/* Save Picks button - make it green */
div.stButton > button[kind="primary"]:has-text("💾 Save Picks") {
    background-color: #28a745 !important;
    border-color: #28a745 !important;
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

/* JavaScript to style best bet and MNF buttons */
</style>
<script>
// Wait for page to load, then style special buttons
setTimeout(function() {
    // Find all buttons with star emoji (best bets) and moon emoji (MNF)
    const buttons = document.querySelectorAll('button[kind="primary"]');
    buttons.forEach(button => {
        if (button.textContent.includes('⭐')) {
            // Best bet styling (purple)
            button.style.backgroundColor = '#b19cd9';
            button.style.borderColor = '#b19cd9';
            button.style.color = '#ffffff';
            button.style.fontWeight = 'bold';

            // Add hover effect
            button.addEventListener('mouseenter', function() {
                this.style.backgroundColor = '#9d84d1';
                this.style.borderColor = '#9d84d1';
            });
            button.addEventListener('mouseleave', function() {
                this.style.backgroundColor = '#b19cd9';
                this.style.borderColor = '#b19cd9';
            });
        } else if (button.textContent.includes('🌙')) {
            // MNF styling (custom purple)
            button.style.backgroundColor = '#C576F6';
            button.style.borderColor = '#C576F6';
            button.style.color = '#ffffff';
            button.style.fontWeight = 'bold';

            // Add hover effect
            button.addEventListener('mouseenter', function() {
                this.style.backgroundColor = '#B765E8';
                this.style.borderColor = '#B765E8';
            });
            button.addEventListener('mouseleave', function() {
                this.style.backgroundColor = '#C576F6';
                this.style.borderColor = '#C576F6';
            });
        }
    });
}, 100);

// Re-run the styling when content changes
const observer = new MutationObserver(function() {
    setTimeout(function() {
        const buttons = document.querySelectorAll('button[kind="primary"]');
        buttons.forEach(button => {
            if (button.textContent.includes('⭐') && button.style.backgroundColor !== 'rgb(177, 156, 217)') {
                button.style.backgroundColor = '#b19cd9';
                button.style.borderColor = '#b19cd9';
                button.style.color = '#ffffff';
                button.style.fontWeight = 'bold';
            } else if (button.textContent.includes('🌙') && button.style.backgroundColor !== 'rgb(197, 118, 246)') {
                button.style.backgroundColor = '#C576F6';
                button.style.borderColor = '#C576F6';
                button.style.color = '#ffffff';
                button.style.fontWeight = 'bold';
            }
        });
    }, 100);
});
observer.observe(document.body, { childList: true, subtree: true });
</script>
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
    # Get available weeks from database for the selected season
    try:
        from g_nfl.utils.database import MarketLinesDatabase

        market_db = MarketLinesDatabase()
        available_weeks = market_db.get_available_weeks(season)
        max_week = market_db.get_max_week_for_season(season)

        if available_weeks:
            # Use available weeks from database
            week_options = available_weeks
            # Set default to max week if it exists, otherwise first available week
            if max_week and max_week in available_weeks:
                default_week_index = available_weeks.index(max_week)
            else:
                default_week_index = (
                    len(available_weeks) - 1
                )  # Last week in available list
        else:
            # Fallback to full range if no data in database
            week_options = list(range(1, 19))
            default_week_index = CUR_WEEK - 1 if CUR_WEEK <= 18 else 0
    except Exception as e:
        # Fallback to full range if database access fails
        week_options = list(range(1, 19))
        default_week_index = CUR_WEEK - 1 if CUR_WEEK <= 18 else 0

    week = st.selectbox("Week", week_options, index=default_week_index)

with col3:
    picker = st.selectbox(
        "Picker",
        [None] + ["TEAM", "Griffin", "Harry", "Ben", "Chuck", "Hunter", "Jacko"],
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
    # Load all picks from database
    from g_nfl.utils.database import PicksDatabase

    db = PicksDatabase()
    all_picks_list = db.get_picks(
        st.session_state.current_season, st.session_state.current_week, picker
    )

    # Separate picks by type
    regular_picks = {}
    survivor_pick = None
    underdog_pick = None
    mnf_pick = None

    for pick in all_picks_list:
        game_id = pick["game_id"]
        pick_type = pick.get("pick_type", "regular")
        team_picked = pick["team_picked"]

        if pick_type in ["regular", "best_bet"]:
            regular_picks[game_id] = {
                "team_picked": team_picked,
                "pick_type": pick_type,
                "spread": pick.get("spread"),
            }
        elif pick_type == "survivor":
            survivor_pick = team_picked
        elif pick_type == "underdog":
            underdog_pick = team_picked
        elif pick_type == "mnf":
            mnf_pick = team_picked

    st.session_state.picks = regular_picks
    st.session_state.survivor_pick = survivor_pick
    st.session_state.underdog_pick = underdog_pick
    st.session_state.mnf_pick = mnf_pick
    st.session_state.last_picker = picker

    total_picks = (
        len(regular_picks)
        + (1 if survivor_pick else 0)
        + (1 if underdog_pick else 0)
        + (1 if mnf_pick else 0)
    )
    if total_picks > 0:
        st.info(f"✅ Loaded {total_picks} existing picks for {picker}")
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
            game_ids = []
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
                    # Use the original game_id from database to ensure consistency
                    game_ids.append(game_id)

            games_df = pd.DataFrame(games_data)
            # Use the original game_ids from the database to ensure picks match
            games_df.index = game_ids
            data_source = "database"

            st.session_state.games_data = games_df
            st.session_state.current_week = week
            st.session_state.current_season = season
            st.session_state.data_source = data_source

            # Load market lines and pool spreads
            lines_data = get_all_lines_data(season, week)
            st.session_state.lines_data = lines_data

            # Debug: show lines data structure
            # with st.expander("🔍 Debug: Show lines data", expanded=False):
            #     st.write("**Games DataFrame game IDs:**")
            #     st.write(list(games_df.index))
            #     st.write("**Lines data game IDs:**")
            #     st.write(list(lines_data.keys()))
            #     st.write("**Sample lines data:**")
            #     if lines_data:
            #         sample_key = list(lines_data.keys())[0]
            #         st.json({sample_key: lines_data[sample_key]})

            # Show data source info
            st.info("📊 Using stored market data from database")

            # Load existing picks if picker is selected and week/season changed
            if (
                "last_week_season_picker" not in st.session_state
                or st.session_state.last_week_season_picker != (week, season, picker)
            ):
                if picker:  # Only load picks if a picker is selected
                    # Load all picks from database
                    from g_nfl.utils.database import PicksDatabase

                    db = PicksDatabase()
                    all_picks_list = db.get_picks(season, week, picker)

                    # Separate picks by type
                    regular_picks = {}
                    survivor_pick = None
                    underdog_pick = None
                    mnf_pick = None

                    for pick in all_picks_list:
                        game_id = pick["game_id"]
                        pick_type = pick.get("pick_type", "regular")
                        team_picked = pick["team_picked"]

                        if pick_type in ["regular", "best_bet"]:
                            regular_picks[game_id] = {
                                "team_picked": team_picked,
                                "pick_type": pick_type,
                                "spread": pick.get("spread"),
                            }
                        elif pick_type == "survivor":
                            survivor_pick = team_picked
                        elif pick_type == "underdog":
                            underdog_pick = team_picked
                        elif pick_type == "mnf":
                            mnf_pick = team_picked

                    st.session_state.picks = regular_picks
                    st.session_state.survivor_pick = survivor_pick
                    st.session_state.underdog_pick = underdog_pick
                    st.session_state.mnf_pick = mnf_pick

                    total_picks = (
                        len(regular_picks)
                        + (1 if survivor_pick else 0)
                        + (1 if underdog_pick else 0)
                        + (1 if mnf_pick else 0)
                    )
                    if total_picks > 0:
                        st.info(f"✅ Loaded {total_picks} existing picks for {picker}")
                else:
                    st.session_state.picks = {}
                    st.session_state.survivor_pick = None
                    st.session_state.underdog_pick = None
                    st.session_state.mnf_pick = None

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

        # Show current pick counts
        if (
            st.session_state.picks
            or st.session_state.survivor_pick
            or st.session_state.underdog_pick
            or st.session_state.mnf_pick
        ):
            total_regular = len(st.session_state.picks)
            has_survivor = "✅" if st.session_state.survivor_pick else "⬜"
            has_underdog = "✅" if st.session_state.underdog_pick else "⬜"
            has_mnf = "✅" if st.session_state.mnf_pick else "⬜"

            st.info(
                f"**Current Picks**: {total_regular}/6 regular • {has_survivor} survivor • {has_underdog} underdog • {has_mnf} MNF"
            )

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

            # Prepare games with spread data for sorting
            games_with_spreads = []
            for game_index, (_, game) in enumerate(games_df.iterrows()):
                game_id = game.name
                is_mnf = game_index == len(games_df) - 1

                # Get spread (pool preferred, fallback to market)
                lines = st.session_state.get("lines_data", {}).get(game_id, {})
                pool_spread = lines.get("pool_spread")
                market_spread = lines.get("market_spread")
                if market_spread is None and pd.notna(game["spread_line"]):
                    market_spread = game["spread_line"]

                effective_spread = (
                    pool_spread if pool_spread is not None else market_spread
                )

                games_with_spreads.append(
                    {
                        "game": game,
                        "game_id": game_id,
                        "game_index": game_index,
                        "is_mnf": is_mnf,
                        "spread": effective_spread,
                    }
                )

            # Render regular/best bet games (including MNF)
            for game_data in games_with_spreads:
                game = game_data["game"]
                game_id = game_data["game_id"]
                is_mnf = game_data["is_mnf"]

                with st.container():
                    if is_mnf:
                        # MNF game uses separate state
                        mnf_selected_team = st.session_state.mnf_pick
                        home_selected = mnf_selected_team == game["home_team"]
                        away_selected = mnf_selected_team == game["away_team"]
                        current_pick = None
                        home_pick_type = "mnf" if home_selected else None
                        away_pick_type = "mnf" if away_selected else None
                        max_picks_reached = (
                            False  # MNF doesn't count toward 6-pick limit
                        )
                    else:
                        # Regular game logic
                        max_picks_reached = len(st.session_state.picks) >= 6
                        game_has_selection = game_id in st.session_state.picks

                        current_pick = st.session_state.picks.get(game_id, {})
                        if isinstance(current_pick, str):
                            # Handle legacy format
                            current_pick = {
                                "team_picked": current_pick,
                                "pick_type": "regular",
                            }

                        home_selected = (
                            current_pick.get("team_picked") == game["home_team"]
                        )
                        away_selected = (
                            current_pick.get("team_picked") == game["away_team"]
                        )

                        # Regular game pick types
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

                    # Create flexible mobile-responsive layout
                    col1, col2, col3 = st.columns([3, 2, 3])

                    with col1:
                        # Away team button
                        away_disabled = (
                            (max_picks_reached and not away_selected)
                            or home_selected
                            or not picker
                        )
                        button_type = get_button_style(
                            away_selected, away_pick_type, away_disabled
                        )

                        # Add MNF emoji if this is MNF game
                        if is_mnf:
                            button_label = f"🌙 {game['away_team']}"
                        else:
                            button_label = get_button_label(
                                game["away_team"], away_pick_type
                            )

                        away_logo = get_team_logo(game["away_team"])

                        # Mobile-responsive: logo and button on same line
                        if away_logo:
                            col_logo, col_button = st.columns([1, 4])
                            with col_logo:
                                st.image(away_logo, width=35)
                            with col_button:
                                if st.button(
                                    button_label,
                                    key=f"away_{game_id}",
                                    type=button_type,
                                    disabled=away_disabled,
                                    use_container_width=True,
                                ):
                                    if is_mnf:
                                        # MNF pick logic
                                        if away_selected:
                                            st.session_state.mnf_pick = None
                                        else:
                                            st.session_state.mnf_pick = game[
                                                "away_team"
                                            ]
                                    else:
                                        # Regular game pick logic
                                        next_state = get_next_pick_state(
                                            current_pick, game["away_team"]
                                        )
                                        if next_state is None:
                                            # Remove the pick
                                            if game_id in st.session_state.picks:
                                                del st.session_state.picks[game_id]
                                        else:
                                            # Add spread info
                                            next_state["spread"] = game.get(
                                                "spread_line"
                                            )
                                            st.session_state.picks[game_id] = next_state
                                    st.rerun()
                        else:
                            if st.button(
                                button_label,
                                key=f"away_{game_id}",
                                type=button_type,
                                disabled=away_disabled,
                                use_container_width=True,
                            ):
                                if is_mnf:
                                    # MNF pick logic
                                    if away_selected:
                                        st.session_state.mnf_pick = None
                                    else:
                                        st.session_state.mnf_pick = game["away_team"]
                                else:
                                    # Regular game pick logic
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
                        )
                        button_type = get_button_style(
                            home_selected, home_pick_type, home_disabled
                        )

                        # Add MNF emoji if this is MNF game
                        if is_mnf:
                            button_label = f"🌙 {game['home_team']}"
                        else:
                            button_label = get_button_label(
                                game["home_team"], home_pick_type
                            )

                        home_logo = get_team_logo(game["home_team"])

                        # Mobile-responsive: logo and button on same line
                        if home_logo:
                            col_logo, col_button = st.columns([1, 4])
                            with col_logo:
                                st.image(home_logo, width=35)
                            with col_button:
                                if st.button(
                                    button_label,
                                    key=f"home_{game_id}",
                                    type=button_type,
                                    disabled=home_disabled,
                                    use_container_width=True,
                                ):
                                    if is_mnf:
                                        # MNF pick logic
                                        if home_selected:
                                            st.session_state.mnf_pick = None
                                        else:
                                            st.session_state.mnf_pick = game[
                                                "home_team"
                                            ]
                                    else:
                                        # Regular game pick logic
                                        next_state = get_next_pick_state(
                                            current_pick, game["home_team"]
                                        )
                                        if next_state is None:
                                            # Remove the pick
                                            if game_id in st.session_state.picks:
                                                del st.session_state.picks[game_id]
                                        else:
                                            # Add spread info
                                            next_state["spread"] = game.get(
                                                "spread_line"
                                            )
                                            st.session_state.picks[game_id] = next_state
                                    st.rerun()
                        else:
                            if st.button(
                                button_label,
                                key=f"home_{game_id}",
                                type=button_type,
                                disabled=home_disabled,
                                use_container_width=True,
                            ):
                                if is_mnf:
                                    # MNF pick logic
                                    if home_selected:
                                        st.session_state.mnf_pick = None
                                    else:
                                        st.session_state.mnf_pick = game["home_team"]
                                else:
                                    # Regular game pick logic
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

                    # Use a thinner divider
                    st.markdown("---")

            # Survivor Section (Favorites)
            st.markdown("### 💀 Survivor Pool")
            st.markdown("Pick ONE favorite (lowest spread) for the week")

            # Sort games by spread (most negative = biggest favorite)
            favorites = []
            for game_data in games_with_spreads:
                if game_data["spread"] is not None:
                    game = game_data["game"]
                    spread = game_data["spread"]
                    game_id = game_data["game_id"]

                    # Determine favorite (negative spread = away favorite, positive = home favorite)
                    if spread < 0:
                        favorite_team = game["away_team"]
                        opponent_team = game["home_team"]
                        favorite_spread = spread
                    else:
                        favorite_team = game["home_team"]
                        opponent_team = game["away_team"]
                        favorite_spread = -spread

                    favorites.append(
                        {
                            "team": favorite_team,
                            "opponent": opponent_team,
                            "spread": favorite_spread,
                            "game_id": game_id,
                            "game": game,
                        }
                    )

            # Sort by spread (most negative first = biggest favorite)
            favorites.sort(key=lambda x: x["spread"])

            # Display favorites
            for fav_data in favorites:
                survivor_selected = st.session_state.survivor_pick == fav_data["team"]
                survivor_disabled = not picker or (
                    st.session_state.survivor_pick is not None
                    and st.session_state.survivor_pick != fav_data["team"]
                )

                col1, col2 = st.columns([4, 1])

                with col1:
                    team_logo = get_team_logo(fav_data["team"])

                    if team_logo:
                        col_logo, col_info = st.columns([1, 6])
                        with col_logo:
                            st.image(team_logo, width=35)
                        with col_info:
                            st.markdown(
                                f"**{fav_data['team']}** ({fav_data['spread']:+.1f}) vs {fav_data['opponent']}"
                            )
                    else:
                        st.markdown(
                            f"**{fav_data['team']}** ({fav_data['spread']:+.1f}) vs {fav_data['opponent']}"
                        )

                with col2:
                    button_type = "primary" if survivor_selected else "secondary"
                    button_text = (
                        f"💀 {fav_data['team']}"
                        if survivor_selected
                        else fav_data["team"]
                    )
                    if st.button(
                        button_text,
                        key=f"survivor_{fav_data['game_id']}_{fav_data['team']}",
                        type=button_type,
                        disabled=survivor_disabled,
                        use_container_width=True,
                    ):
                        if survivor_selected:
                            st.session_state.survivor_pick = None
                        else:
                            st.session_state.survivor_pick = fav_data["team"]
                        st.rerun()

            st.markdown("---")

            # Underdog Section
            st.markdown("### 🐶 Underdog Pool")
            st.markdown("Pick ONE underdog (highest spread) for the week")

            # Sort games by spread (most positive = biggest underdog)
            underdogs = []
            for game_data in games_with_spreads:
                if game_data["spread"] is not None:
                    game = game_data["game"]
                    spread = game_data["spread"]
                    game_id = game_data["game_id"]

                    # Determine underdog (negative spread = home underdog, positive = away underdog)
                    if spread < 0:
                        underdog_team = game["home_team"]
                        opponent_team = game["away_team"]
                        underdog_spread = -spread  # Flip to positive
                    else:
                        underdog_team = game["away_team"]
                        opponent_team = game["home_team"]
                        underdog_spread = spread

                    underdogs.append(
                        {
                            "team": underdog_team,
                            "opponent": opponent_team,
                            "spread": underdog_spread,
                            "game_id": game_id,
                            "game": game,
                        }
                    )

            # Sort by spread (most positive first = biggest underdog)
            underdogs.sort(key=lambda x: x["spread"], reverse=True)

            # Display underdogs
            for dog_data in underdogs:
                underdog_selected = st.session_state.underdog_pick == dog_data["team"]
                underdog_disabled = not picker or (
                    st.session_state.underdog_pick is not None
                    and st.session_state.underdog_pick != dog_data["team"]
                )

                col1, col2 = st.columns([4, 1])

                with col1:
                    team_logo = get_team_logo(dog_data["team"])

                    if team_logo:
                        col_logo, col_info = st.columns([1, 6])
                        with col_logo:
                            st.image(team_logo, width=35)
                        with col_info:
                            st.markdown(
                                f"**{dog_data['team']}** (+{dog_data['spread']:.1f}) vs {dog_data['opponent']}"
                            )
                    else:
                        st.markdown(
                            f"**{dog_data['team']}** (+{dog_data['spread']:.1f}) vs {dog_data['opponent']}"
                        )

                with col2:
                    button_type = "primary" if underdog_selected else "secondary"
                    button_text = (
                        f"🐶 {dog_data['team']}"
                        if underdog_selected
                        else dog_data["team"]
                    )
                    if st.button(
                        button_text,
                        key=f"underdog_{dog_data['game_id']}_{dog_data['team']}",
                        type=button_type,
                        disabled=underdog_disabled,
                        use_container_width=True,
                    ):
                        if underdog_selected:
                            st.session_state.underdog_pick = None
                        else:
                            st.session_state.underdog_pick = dog_data["team"]
                        st.rerun()

            st.markdown("---")

        # Show picks summary
        if (
            st.session_state.picks
            or st.session_state.survivor_pick
            or st.session_state.underdog_pick
            or st.session_state.mnf_pick
        ) and picker:
            st.markdown("---")
            st.markdown("### 📋 Pick Summary")

            # Build structured picks list with opponent info
            best_bets = []
            regular_picks = []
            mnf_pick_line = None
            survivor_pick_line = None
            underdog_pick_line = None

            # Process regular/best bet picks
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

                    # Determine opponent and location
                    if team == game["away_team"]:
                        opponent = game["home_team"]
                        location = "at"
                    else:
                        opponent = game["away_team"]
                        location = "vs"

                    # Show spread - flip for home teams
                    if pd.notna(game["spread_line"]):
                        base_spread = game["spread_line"]
                        # If picked team is home team, flip the spread
                        if team == game["home_team"]:
                            display_spread = -base_spread
                        else:
                            display_spread = base_spread
                        spread = f"({display_spread:+.1f})"
                    else:
                        spread = ""

                    # Format: TEAM (SPREAD) at/vs OPPONENT
                    pick_line = f"{team} {spread} {location} {opponent}"

                    # Add emoji prefix for best bets
                    if pick_type == "best_bet":
                        best_bets.append(f"⭐️ {pick_line}")
                    else:
                        regular_picks.append(pick_line)

            # Process MNF pick
            if st.session_state.mnf_pick:
                # Find the MNF game to get opponent
                for game_id, game in games_df.iterrows():
                    if st.session_state.mnf_pick in [
                        game["away_team"],
                        game["home_team"],
                    ]:
                        team = st.session_state.mnf_pick
                        if team == game["away_team"]:
                            opponent = game["home_team"]
                            location = "at"
                        else:
                            opponent = game["away_team"]
                            location = "vs"

                        # Show spread
                        if pd.notna(game["spread_line"]):
                            base_spread = game["spread_line"]
                            if team == game["home_team"]:
                                display_spread = -base_spread
                            else:
                                display_spread = base_spread
                            spread = f"({display_spread:+.1f})"
                        else:
                            spread = ""

                        mnf_pick_line = f"🌙 {team} {spread} {location} {opponent}"
                        break

            # Process Survivor pick
            if st.session_state.survivor_pick:
                # Find the game to get opponent
                for game_id, game in games_df.iterrows():
                    if st.session_state.survivor_pick in [
                        game["away_team"],
                        game["home_team"],
                    ]:
                        team = st.session_state.survivor_pick
                        if team == game["away_team"]:
                            opponent = game["home_team"]
                            location = "at"
                        else:
                            opponent = game["away_team"]
                            location = "vs"

                        # Show spread
                        if pd.notna(game["spread_line"]):
                            base_spread = game["spread_line"]
                            if team == game["home_team"]:
                                display_spread = -base_spread
                            else:
                                display_spread = base_spread
                            spread = f"({display_spread:+.1f})"
                        else:
                            spread = ""

                        survivor_pick_line = f"💀 {team} {spread} {location} {opponent}"
                        break

            # Process Underdog pick
            if st.session_state.underdog_pick:
                # Find the game to get opponent
                for game_id, game in games_df.iterrows():
                    if st.session_state.underdog_pick in [
                        game["away_team"],
                        game["home_team"],
                    ]:
                        team = st.session_state.underdog_pick
                        if team == game["away_team"]:
                            opponent = game["home_team"]
                            location = "at"
                        else:
                            opponent = game["away_team"]
                            location = "vs"

                        # Show spread
                        if pd.notna(game["spread_line"]):
                            base_spread = game["spread_line"]
                            if team == game["home_team"]:
                                display_spread = -base_spread
                            else:
                                display_spread = base_spread
                            spread = f"({display_spread:+.1f})"
                        else:
                            spread = ""

                        underdog_pick_line = f"🐶 {team} {spread} {location} {opponent}"
                        break

            # Combine in order: Best Bets, Regular Picks, MNF, Survivor, Underdog
            picks_display = []
            picks_display.extend(best_bets)
            picks_display.extend(regular_picks)
            if mnf_pick_line:
                picks_display.append(mnf_pick_line)
            if survivor_pick_line:
                picks_display.append(survivor_pick_line)
            if underdog_pick_line:
                picks_display.append(underdog_pick_line)

            if picks_display:
                # Create picks text with header
                picks_header = f"{picker}'s Week {st.session_state.current_week} Picks"
                picks_body = "\n".join(picks_display)
                picks_text = f"{picks_header}\n\n{picks_body}"

                # Display picks in a code block for easy copying
                st.code(picks_text, language=None)

                st.markdown("---")

                # Action buttons
                col1, col2, col3 = st.columns([2, 1, 2])

                with col1:
                    # Save button with clipboard copy
                    save_button_clicked = st.button(
                        "💾 Save Picks",
                        type="primary",
                        help="Save your picks to the database and copy to clipboard",
                        key="save_picks_btn",
                    )

                    if save_button_clicked:
                        if not picker:
                            st.error("⚠️ Please select a picker before submitting")
                        elif (
                            st.session_state.picks
                            or st.session_state.survivor_pick
                            or st.session_state.underdog_pick
                            or st.session_state.mnf_pick
                        ):
                            # Create combined picks dict - maintain original structure but allow multi-pick save
                            # Clean up any malformed keys in session state first
                            cleaned_picks = {}
                            for key, value in st.session_state.picks.items():
                                # Only keep properly formatted game_id keys (season_week_away_home format)
                                if (
                                    key.count("_") >= 3
                                    and not key.endswith("_best")
                                    and not key.endswith("_regular")
                                ):
                                    cleaned_picks[key] = value

                            # Update session state with cleaned data
                            st.session_state.picks = cleaned_picks
                            all_picks = dict(cleaned_picks)  # Copy regular picks

                            # Add survivor pick using actual game ID
                            if st.session_state.survivor_pick:
                                # Find the game ID for the survivor pick
                                survivor_game_id = None
                                survivor_spread = None
                                for _, game in games_df.iterrows():
                                    if (
                                        game["away_team"]
                                        == st.session_state.survivor_pick
                                        or game["home_team"]
                                        == st.session_state.survivor_pick
                                    ):
                                        survivor_game_id = game.name
                                        survivor_spread = game.get("spread_line")
                                        break

                                if survivor_game_id:
                                    # Use special key for survivor pick to allow combo with regular pick
                                    all_picks[f"survivor_{survivor_game_id}"] = {
                                        "team_picked": st.session_state.survivor_pick,
                                        "pick_type": "survivor",
                                        "spread": survivor_spread,
                                        "game_id": survivor_game_id,
                                    }

                            # Add underdog pick using actual game ID
                            if st.session_state.underdog_pick:
                                # Find the game ID for the underdog pick
                                underdog_game_id = None
                                underdog_spread = None
                                for _, game in games_df.iterrows():
                                    if (
                                        game["away_team"]
                                        == st.session_state.underdog_pick
                                        or game["home_team"]
                                        == st.session_state.underdog_pick
                                    ):
                                        underdog_game_id = game.name
                                        underdog_spread = game.get("spread_line")
                                        break

                                if underdog_game_id:
                                    # Use special key for underdog pick to allow combo with regular pick
                                    all_picks[f"underdog_{underdog_game_id}"] = {
                                        "team_picked": st.session_state.underdog_pick,
                                        "pick_type": "underdog",
                                        "spread": underdog_spread,
                                        "game_id": underdog_game_id,
                                    }

                            # Add MNF pick using actual game ID (last game in list)
                            if st.session_state.mnf_pick:
                                # Find the MNF game (last game) and its spread
                                if len(games_df) > 0:
                                    mnf_game = games_df.iloc[-1]  # Last game is MNF
                                    mnf_game_id = mnf_game.name  # Use actual game ID

                                    # Use special key for MNF pick to allow combo with regular pick
                                    all_picks[f"mnf_{mnf_game_id}"] = {
                                        "team_picked": st.session_state.mnf_pick,
                                        "pick_type": "mnf",
                                        "spread": mnf_game.get("spread_line"),
                                        "game_id": mnf_game_id,
                                    }

                            # Debug: show what we're trying to save
                            # with st.expander(
                            #     "🔍 Debug: Show picks data being saved", expanded=False
                            # ):
                            #     st.write("**Session State Picks:**")
                            #     st.json(dict(st.session_state.picks))
                            #     st.write("**Special Picks:**")
                            #     st.write(f"Survivor: {st.session_state.survivor_pick}")
                            #     st.write(f"Underdog: {st.session_state.underdog_pick}")
                            #     st.write(f"MNF: {st.session_state.mnf_pick}")
                            #     st.write("**Combined All Picks:**")
                            #     st.json(
                            #         {
                            #             "season": st.session_state.current_season,
                            #             "week": st.session_state.current_week,
                            #             "picker": picker,
                            #             "picks": all_picks,
                            #         }
                            #     )

                            # Add more debugging for the save process
                            # st.write(
                            #     f"**Attempting to save {len(all_picks)} picks...**"
                            # )

                            result = save_picks_data(
                                st.session_state.current_season,
                                st.session_state.current_week,
                                all_picks,
                                picker,
                            )

                            # Debug the result
                            # st.write(f"**Save result:** `{repr(result)}`")

                            if result and not result.startswith("ERROR:"):
                                st.success(f"✅ {result}")

                                # Copy picks to clipboard using JavaScript
                                clipboard_html = f"""
                                <script>
                                    navigator.clipboard.writeText(`{picks_text}`).then(function() {{
                                        console.log('Picks copied to clipboard!');
                                    }}, function(err) {{
                                        console.error('Could not copy text: ', err);
                                    }});
                                </script>
                                """
                                st.markdown(clipboard_html, unsafe_allow_html=True)
                                st.info("📋 Picks copied to clipboard!")
                            elif result and result.startswith("ERROR:"):
                                st.error(
                                    f"❌ Failed to save picks: {result[7:]}"
                                )  # Remove "ERROR: " prefix
                            elif result is None:
                                st.error(
                                    "❌ Failed to save picks: save_picks_data returned None"
                                )
                            else:
                                st.error(
                                    f"❌ Failed to save picks: Unexpected result type: {type(result)} - {result}"
                                )
                        else:
                            st.warning("⚠️ No picks to save")

                with col3:
                    if st.button(
                        "🗑️ Clear All", type="secondary", help="Clear all your picks"
                    ):
                        st.session_state.picks = {}
                        st.session_state.survivor_pick = None
                        st.session_state.underdog_pick = None
                        st.session_state.mnf_pick = None
                        st.success("✅ All picks cleared!")
                        st.rerun()

        # Footer info
        st.markdown("---")
        st.caption(
            f"📊 Showing {len(games_df)} games for Week {st.session_state.current_week} • Season {season}"
        )
    else:
        st.warning("No games found for the selected week and season.")
