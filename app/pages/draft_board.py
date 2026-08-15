"""Fantasy draft board with live league settings (issue #90).

Everything here edits a ``LeagueConfig`` and re-runs the board. The scoring
itself lives in ``g_nfl.fantasy.scoring`` and the replacement-level maths in
``g_nfl.fantasy.projections.board``; this page owns neither.
"""

import os
import sys

import streamlit as st

# Add both parent directory and src directory to path for Streamlit Cloud compatibility
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from g_nfl.fantasy.draft_board import (
    BOARD_COLUMNS,
    DEFAULT_TIER_GAP,
    attach_tiers,
    load_ecr,
)
from g_nfl.fantasy.projections.board import build_board
from g_nfl.fantasy.scoring import PRESETS, LeagueConfig, Scoring, score
from g_nfl.fantasy.sources.espn import fetch_espn_projections

SEASON = 2026

st.set_page_config(page_title="Draft Board - fantasy", layout="wide")


# Cached: both are network calls, and every slider nudge triggers a rerun.
# The board recompute below is deliberately uncached — it's what the sliders do.
@st.cache_data(show_spinner="Fetching ESPN projections...")
def _stat_lines(season: int):
    return fetch_espn_projections(season)


@st.cache_data(show_spinner="Loading FantasyPros ECR...")
def _ecr():
    return load_ecr()


st.title("🏈 Draft Board")

# --- Sidebar: the league ---------------------------------------------------

st.sidebar.markdown("## League")

preset_name = st.sidebar.selectbox(
    "Preset", list(PRESETS), index=list(PRESETS).index("ppr_12")
)
preset = PRESETS[preset_name]

teams = st.sidebar.slider("Teams", 4, 20, preset.teams)

st.sidebar.markdown("### Starting slots")
slot_counts = {}
for slot, default in [
    ("QB", preset.roster_positions.count("QB")),
    ("RB", preset.roster_positions.count("RB")),
    ("WR", preset.roster_positions.count("WR")),
    ("TE", preset.roster_positions.count("TE")),
    ("FLEX", preset.roster_positions.count("FLEX")),
    ("SUPER_FLEX", preset.roster_positions.count("SUPER_FLEX")),
]:
    slot_counts[slot] = st.sidebar.number_input(slot, 0, 4, default, key=f"slot_{slot}")

roster_positions = [slot for slot, n in slot_counts.items() for _ in range(n)]
bench = st.sidebar.number_input("Bench", 0, 15, preset.bench)

with st.sidebar.expander("Scoring"):
    p = preset.scoring
    scoring = Scoring(
        reception=st.number_input("Per reception", 0.0, 2.0, p.reception, 0.5),
        te_premium=st.number_input(
            "TE premium (extra/rec)", 0.0, 2.0, p.te_premium, 0.5
        ),
        rec_yd=st.number_input("Per receiving yard", 0.0, 1.0, p.rec_yd, 0.01),
        rush_yd=st.number_input("Per rushing yard", 0.0, 1.0, p.rush_yd, 0.01),
        pass_yd=st.number_input("Per passing yard", 0.0, 1.0, p.pass_yd, 0.01),
        td=st.number_input("Rush/rec TD", 0.0, 12.0, p.td, 1.0),
        pass_td=st.number_input("Passing TD", 0.0, 12.0, p.pass_td, 1.0),
        interception=st.number_input("Interception", -10.0, 0.0, p.interception, 1.0),
        fumble_lost=st.number_input("Fumble lost", -10.0, 0.0, p.fumble_lost, 1.0),
    )

tier_gap = st.sidebar.slider("Tier gap (ppg)", 0.1, 3.0, DEFAULT_TIER_GAP, 0.05)

config = LeagueConfig(
    teams=teams, roster_positions=roster_positions, bench=bench, scoring=scoring
)
label = preset_name if scoring == preset.scoring else f"{preset_name} (custom scoring)"

if not roster_positions:
    st.warning("Add at least one starting slot.")
    st.stop()

# --- The board -------------------------------------------------------------

stat_lines = _stat_lines(SEASON)
ecr, scrape_date = _ecr()

board = build_board(score(stat_lines, config), config.teams, config.roster_positions)
board = attach_tiers(board.join(ecr, on="gsis_id", how="left"), tier_gap)
board = board.sort("overall_rank").select(BOARD_COLUMNS)

st.caption(
    f"**{label}** — {teams} teams, {'/'.join(roster_positions)}, {bench} bench. "
    f"ESPN {SEASON} projections ({stat_lines.height} players) · "
    f"FantasyPros ECR scraped {scrape_date}. "
    "ECR is expert opinion, not ADP, and the redraft page is PPR-only."
)

positions = st.multiselect(
    "Positions", ["QB", "RB", "WR", "TE"], default=["QB", "RB", "WR", "TE"]
)
shown = board.filter(board["position"].is_in(positions))

st.dataframe(
    shown.to_pandas(),
    width="stretch",
    hide_index=True,
    height=800,
    column_config={
        "overall_rank": st.column_config.NumberColumn("#", width="small"),
        "player_name": st.column_config.TextColumn("Player"),
        "position": st.column_config.TextColumn("Pos", width="small"),
        "pos_rank": st.column_config.NumberColumn("Pos rk", width="small"),
        "team": st.column_config.TextColumn("Team", width="small"),
        "tier": st.column_config.NumberColumn("Tier", width="small"),
        "proj_ppg": st.column_config.NumberColumn("Proj ppg", format="%.2f"),
        "ppgar": st.column_config.ProgressColumn(
            "PPGAR",
            format="%.2f",
            min_value=float(min(0.0, board["ppgar"].min())),
            max_value=float(board["ppgar"].max()),
        ),
        "ecr": st.column_config.NumberColumn("ECR", format="%.1f"),
        "sd": st.column_config.NumberColumn("ECR sd", format="%.1f"),
    },
)

st.download_button(
    "⬇️ Download CSV",
    shown.write_csv(),
    file_name=f"draft_board_{SEASON}_{preset_name}.csv",
    mime="text/csv",
)
