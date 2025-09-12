import os
import sys
from typing import Dict, Optional

import pandas as pd
import streamlit as st

# Add both parent directory and src directory to path for Streamlit Cloud compatibility
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from g_nfl import CUR_WEEK
from g_nfl.modelling.utils import get_week_spreads
from g_nfl.utils.config import CUR_SEASON
from g_nfl.utils.database import MarketLinesDatabase, PoolSpreadsDatabase
from g_nfl.utils.web_app import get_team_logo

st.set_page_config(page_title="Manage Pool Spreads - no-homers", layout="wide")

st.title("🎯 Manage Pool Spreads")

# Add controls for selecting week
col_spacer1, col_controls, col_spacer2 = st.columns([2, 6, 2])

with col_controls:
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        season = st.selectbox(
            "Select Season",
            list(range(2020, CUR_SEASON + 1)),
            index=len(list(range(2020, CUR_SEASON + 1))) - 1,
            key="manage_season",
        )

    with col2:
        week = st.selectbox(
            "Select Week", list(range(1, 19)), index=CUR_WEEK - 1, key="manage_week"
        )

    with col3:
        st.write("")  # Add some vertical spacing
        load_games_button = st.button("Load Games", key="load_games_btn")


def get_games_with_lines(season: int, week: int) -> pd.DataFrame:
    """Get games with market and pool spreads - database only for deployment"""
    try:
        # Always use database for games data (deployment-ready)
        market_db = MarketLinesDatabase()
        market_lines = market_db.get_market_lines(season, week)

        if not market_lines:
            return pd.DataFrame(), "No games found - run update_market_lines.py first"

        # Convert market lines to DataFrame
        games_data = []
        for line in market_lines:
            game_id = line["game_id"]
            # Parse game_id: 2025_1_KC_LAC
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
        games_source = "database"

        if games_df.empty:
            return pd.DataFrame(), "No games found"

        # Get pool spreads from database
        pool_db = PoolSpreadsDatabase()
        pool_spreads = pool_db.get_pool_spreads(season, week)
        pool_spreads_dict = {p["game_id"]: p["spread"] for p in pool_spreads}

        # Add pool spreads to games DataFrame
        games_df["pool_spread"] = games_df.index.map(pool_spreads_dict)

        return games_df, games_source

    except Exception as e:
        st.error(f"Error loading games: {e}")
        return pd.DataFrame(), "error"


# Load games data
if load_games_button or "games_spreads_data" not in st.session_state:
    with st.spinner("Loading games data..."):
        games_df, source = get_games_with_lines(season, week)
        st.session_state.games_spreads_data = games_df
        st.session_state.games_source = source
        st.session_state.current_manage_season = season
        st.session_state.current_manage_week = week

# Display games if data is loaded
if (
    "games_spreads_data" in st.session_state
    and not st.session_state.games_spreads_data.empty
):
    games_df = st.session_state.games_spreads_data
    source = st.session_state.games_source

    st.success(
        f"✅ Loaded {len(games_df)} games for Week {st.session_state.current_manage_week} (Source: {source})"
    )

    st.markdown("---")
    st.subheader("📊 Pool Spread Management")
    st.caption(
        "Set the spreads that will be used for your competition. Market spreads shown for reference."
    )

    # Create a form for updating spreads
    with st.form("update_spreads_form"):
        st.markdown("### Edit Pool Spreads")

        updated_spreads = {}

        # Create centered container
        col_spacer1, col_content, col_spacer2 = st.columns([1, 8, 1])

        with col_content:
            # Header row
            header_col1, header_col2, header_col3, header_col4 = st.columns(
                [2, 2, 2, 2]
            )
            with header_col1:
                st.markdown("**Away Team**")
            with header_col2:
                st.markdown("**Home Team**")
            with header_col3:
                st.markdown("**Market Spread**")
            with header_col4:
                st.markdown("**Pool Spread**")
            st.markdown("---")

            for game_id, game in games_df.iterrows():
                col1, col2, col3, col4 = st.columns([2, 2, 2, 2])

                with col1:
                    # Away team with logo
                    away_logo = get_team_logo(game["away_team"])
                    if away_logo:
                        logo_col, name_col = st.columns([0.3, 1.7])
                        with logo_col:
                            st.image(away_logo, width=25)
                        with name_col:
                            st.markdown(f"**{game['away_team']}**")
                    else:
                        st.markdown(f"**{game['away_team']}**")

                with col2:
                    # Home team with logo
                    home_logo = get_team_logo(game["home_team"])
                    if home_logo:
                        logo_col, name_col = st.columns([0.3, 1.7])
                        with logo_col:
                            st.image(home_logo, width=25)
                        with name_col:
                            st.markdown(f"**{game['home_team']}**")
                    else:
                        st.markdown(f"**{game['home_team']}**")

                with col3:
                    # Market spread (read-only)
                    market_spread = game.get("spread_line")
                    if pd.notna(market_spread):
                        st.markdown(f"**{market_spread:+.1f}**")
                    else:
                        st.markdown("**N/A**")

                with col4:
                    # Pool spread (editable)
                    current_pool = game.get("pool_spread")
                    default_value = (
                        current_pool
                        if pd.notna(current_pool)
                        else (market_spread if pd.notna(market_spread) else 0.0)
                    )

                    new_spread = st.number_input(
                        "Pool Spread",
                        value=float(default_value),
                        step=0.5,
                        format="%.1f",
                        key=f"spread_{game_id}",
                        label_visibility="collapsed",
                    )
                    updated_spreads[game_id] = new_spread

                # Add a subtle divider
                st.markdown(
                    "<hr style='margin: 8px 0; border: none; height: 1px; background-color: rgba(128, 128, 128, 0.3);'>",
                    unsafe_allow_html=True,
                )

        # Submit button
        col1, col2, col3 = st.columns([3, 2, 3])
        with col2:
            submitted = st.form_submit_button("💾 Save Pool Spreads", type="primary")

        if submitted:
            try:
                # Save to database
                pool_db = PoolSpreadsDatabase()
                saved_count = pool_db.save_pool_spreads(
                    st.session_state.current_manage_season,
                    st.session_state.current_manage_week,
                    updated_spreads,
                )

                st.success(f"✅ Successfully saved {saved_count} pool spreads!")

                # Refresh the data
                st.rerun()

            except Exception as e:
                st.error(f"❌ Error saving spreads: {e}")

elif (
    "games_spreads_data" in st.session_state
    and st.session_state.games_spreads_data.empty
):
    st.info(
        f"No games found for Week {week}. Make sure market lines have been loaded for this week."
    )

    st.markdown("---")
    st.subheader("📝 How to Load Market Lines")
    st.markdown(
        """
    To manage pool spreads, you first need market line data. Run this command locally:

    ```bash
    python scripts/update_market_lines.py --season {season} --week {week}
    ```

    Or for multiple weeks:
    ```bash
    python scripts/update_market_lines.py --season {season} --weeks 1-18
    ```
    """.format(
            season=season, week=week
        )
    )

else:
    st.info("👆 Click 'Load Games' to start managing pool spreads")

# Add usage instructions
st.markdown("---")
st.subheader("ℹ️ How to Use")
st.markdown(
    """
1. **Load Games**: Select season/week and click 'Load Games'
2. **Review Market Spreads**: See the current market spreads for reference
3. **Set Pool Spreads**: Enter your competition's spreads (defaults to market spreads)
4. **Save Changes**: Click 'Save Pool Spreads' to store in database

**Note**: Pool spreads are used across all pickers in your competition.
"""
)

# Add a note about the data source
st.caption("📊 Market lines loaded from database | Pool spreads saved to Supabase")
