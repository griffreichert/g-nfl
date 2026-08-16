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

import polars as pl

from g_nfl.fantasy.draft_board import (
    BOARD_COLUMNS,
    DEFAULT_TIER_SENSITIVITY,
    SORTS,
    attach_next_turn_value,
    attach_tiers,
    attach_vs_ecr,
    load_ecr,
    picks_until_next_turn,
    snake_picks,
    sort_board,
)
from g_nfl.fantasy.draft_state import load_drafted, save_drafted
from g_nfl.fantasy.outcomes import (
    attach_outcomes,
    build_history,
    load_adp,
    residuals,
)
from g_nfl.fantasy.projections.board import build_board
from g_nfl.fantasy.scoring import PRESETS, LeagueConfig, Scoring, score
from g_nfl.fantasy.sources.espn import fetch_espn_projections
from g_nfl.fantasy.survival import consensus_pick, survival
from g_nfl.utils.web_app import get_team_logo

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


@st.cache_data(show_spinner="Loading ADP...")
def _adp(season: int):
    return load_adp(season)


# Keyed on the scoring config: role ratios are near scale-free, but luck is
# measured in points, so it has to be rebuilt when the scoring changes.
@st.cache_data(show_spinner="Measuring historical outcomes (this takes a minute)...")
def _residuals(config_json: str):
    config = LeagueConfig.model_validate_json(config_json)
    return residuals(build_history(list(range(2019, 2026)), config))


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

tier_sensitivity = st.sidebar.slider(
    "Tier sensitivity",
    1.0,
    4.0,
    DEFAULT_TIER_SENSITIVITY,
    0.05,
    help="A tier break is a drop this many times the local median gap. "
    "Lower means more, smaller tiers.",
)

show_outcomes = st.sidebar.checkbox(
    "Outcome range (slow)",
    help="Floor and ceiling from historical role and luck residuals, 2019-2025 (#86).",
)

st.sidebar.markdown("### Draft state")
st.sidebar.caption(
    f"{len(load_drafted())} players struck. Saved to disk, so a refresh keeps them."
)
if st.sidebar.button("Clear draft", width="stretch"):
    save_drafted(set())
    st.rerun()

st.sidebar.markdown("### Your turn")
slot = st.sidebar.number_input("Draft slot", 1, teams, min(1, teams))
rounds = len(roster_positions) + bench if roster_positions else 1
current_round = st.sidebar.number_input("Round", 1, max(rounds - 1, 1), 1)

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

# Drafted players come out of the pool *before* build_board, so replacement
# level is derived from who is actually left. That is the whole point of #79
# option 2: positional scarcity is dynamic, and a board that ignores it keeps
# telling you RBs are valuable long after the RB run has ended.
drafted = load_drafted()
available = stat_lines.filter(~pl.col("gsis_id").is_in(list(drafted)))

board = build_board(score(available, config), config.teams, config.roster_positions)
board = attach_tiers(board.join(ecr, on="gsis_id", how="left"), tier_sensitivity)
board = attach_vs_ecr(board)
board = board.sort("overall_rank").select(["gsis_id", *BOARD_COLUMNS])

picks_between = picks_until_next_turn(slot, teams, current_round)
next_pick = snake_picks(slot, teams, current_round + 1)[current_round]
board = consensus_pick(board, _adp(SEASON))
board, outlook = attach_next_turn_value(board, picks_between, next_pick)
board = survival(board, next_pick)

outcome_columns: list[str] = []
if show_outcomes:
    board = attach_outcomes(board, _residuals(config.model_dump_json()), SEASON)
    outcome_columns = ["floor", "ceiling"]

board = board.with_columns(
    pl.col("team").map_elements(get_team_logo, return_dtype=pl.Utf8).alias("logo")
).select(
    ["gsis_id", "logo", *BOARD_COLUMNS, "vs_next_turn", "p_available", *outcome_columns]
)

st.caption(
    f"**{label}** — {teams} teams, {'/'.join(roster_positions)}, {bench} bench. "
    f"ESPN {SEASON} projections ({stat_lines.height} players) · "
    f"FantasyPros ECR scraped {scrape_date}. "
    "ECR is expert opinion, not ADP, and the redraft page is PPR-only."
)

my_picks = snake_picks(slot, teams, current_round + 1)
st.subheader(
    f"Pick {my_picks[current_round - 1]}, then pick {my_picks[current_round]} — "
    f"{picks_between} picks in between"
)
st.dataframe(
    outlook.to_pandas(),
    width="stretch",
    hide_index=True,
    column_config={
        "position": st.column_config.TextColumn("Pos", width="small"),
        "best_now": st.column_config.TextColumn("Best now"),
        "ppgar_now": st.column_config.NumberColumn("PPGAR", format="%.2f"),
        "best_next_turn": st.column_config.TextColumn("Best at next turn"),
        "ppgar_next_turn": st.column_config.NumberColumn("PPGAR", format="%.2f"),
        "cost_of_waiting": st.column_config.NumberColumn(
            "Cost of waiting", format="%.2f"
        ),
    },
)
st.caption(
    f"Survival is modelled from ADP: a player lasts to pick {next_pick} if his draft "
    "position, normal around his ADP with the spread from min/max pick, falls after "
    "it. QBs use ECR instead, since MFL pools superflex rooms into one ADP feed."
)

left, right = st.columns([2, 1])
with left:
    positions = st.multiselect(
        "Positions", ["QB", "RB", "WR", "TE"], default=["QB", "RB", "WR", "TE"]
    )
with right:
    available = [s for s in SORTS if s in board.columns]
    sort_by = st.selectbox(
        "Rank by",
        available,
        format_func=lambda s: SORTS[s],
        help="The # column stays PPGAR rank whatever you sort by, so it reads as "
        "a fixed reference. Early rounds are where the floor is worth paying for; "
        "by the last few, a bust gets dropped and the ceiling is nearly free.",
    )
shown = sort_board(board.filter(board["position"].is_in(positions)), sort_by)

edited = st.data_editor(
    shown.with_columns(pl.lit(False).alias("drafted")).to_pandas(),
    width="stretch",
    hide_index=True,
    height=800,
    disabled=[c for c in shown.columns if c != "drafted"],
    column_config={
        "drafted": st.column_config.CheckboxColumn(
            "Drafted", help="Tick to take the player off the board.", width="small"
        ),
        "gsis_id": None,
        "logo": st.column_config.ImageColumn("", width="small"),
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
        "vs_ecr": st.column_config.NumberColumn(
            "vs ECR",
            format="%+.0f",
            help="ECR minus our rank. Positive = this league likes him more than "
            "the room does. A very large delta is usually a projection problem, "
            "not an edge.",
        ),
        "floor": st.column_config.NumberColumn(
            "Floor",
            format="%.1f",
            help="10th percentile ppg from historical role and luck residuals.",
        ),
        "ceiling": st.column_config.NumberColumn(
            "Ceiling", format="%.1f", help="90th percentile ppg."
        ),
        "p_available": st.column_config.NumberColumn(
            "Still there?",
            format="percent",
            help="Chance he lasts to your next pick, from ADP spread. "
            "QBs use FantasyPros ECR instead: MFL pools superflex rooms into one "
            "ADP feed, which takes quarterbacks far too early for a 1QB league.",
        ),
        "vs_next_turn": st.column_config.NumberColumn(
            "vs next turn",
            format="%.2f",
            help="PPGAR over the best player at this position expected to survive "
            "to your next pick.",
        ),
    },
)

struck = set(edited.loc[edited["drafted"], "gsis_id"])
if struck:
    save_drafted(drafted | struck)
    st.rerun()

st.download_button(
    "⬇️ Download CSV",
    shown.write_csv(),
    file_name=f"draft_board_{SEASON}_{preset_name}.csv",
    mime="text/csv",
)
