# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an NFL betting and fantasy football analysis project that combines data science, web scraping, and betting strategy. The core focus is building power ratings systems, generating betting picks, and analyzing NFL team/player performance using advanced metrics.

**Philosophy**: "The Cleveland Browns can stay irrational longer than I can stay solvent"

## Task Tracking & Session Continuity (`notes/`)

The `notes/` folder is the source of truth for in-flight, multi-session work. Use it to resume tasks across sessions.

**At the start of a session** (before starting any non-trivial task):
1. List `notes/` and read any note relevant to the current task
2. If a note exists for the task, resume from its "Status" / remaining-work section rather than re-planning from scratch

**During work on any multi-session or multi-step task**:
- Maintain one markdown file per task in `notes/`, named after the task (kebab-case, e.g. `deployment-refactor.md`)
- Use frontmatter:
  ```markdown
  ---
  author: claude
  date: YYYY-MM-DD
  ---
  ```
- Track tasks at a **high level**: goal, current state, key decisions made (and why), and remaining steps. Do not log every edit — capture enough that a fresh session can pick up where this one left off.
- Update the note **before ending a session** or whenever a major milestone or decision lands (mark completed steps, record what's next)

**When a task is fully complete**: mark the note as done at the top (or summarize the outcome) so future sessions know it's closed.

## Key Architecture Components

### Data Pipeline
- **External Data Sources**: Multiple scraped sources including NFelo, PFF, Unabated, ESPN, Inpredictable, and Sumer Sports
- **NFL Data**: Primary data source is `nfl_data_py` for play-by-play and statistical data
- **Storage**: CSV files organized by source and week in `data/` directory, with some processed data as pickle files

### Core Modules

**Power Ratings Engine** (`src/g_nfl/modelling/`):
- `homers.py`: Multi-picker power rating system with Google Sheets integration
- `utils.py`: Core betting utilities including spread prediction and line conversion
- `metrics.py`: Advanced NFL metrics and success rate calculations

**Data Processing** (`src/g_nfl/utils/`):
- `config.py`: Global constants (current season, HFA, thresholds)
- `teams.py`: Team name standardization across data sources
- `odds.py`: Betting odds and line manipulation
- `data.py`: Data loading and processing utilities

**Analysis Notebooks**:
- `notebooks/picks/pick-pipeline.ipynb`: Main weekly betting picks generation
- `notebooks/ratings/`: Weekly team performance analysis
- `notebooks/fantasy/`: Player projection and fantasy analysis

### Key Workflows

**Power Ratings to Picks Pipeline**:
1. Aggregate multiple expert power ratings from Google Sheets
2. Convert percentile rankings to adjusted point spreads using `calc_percentile_to_gpf()`
3. Generate composite rankings across multiple pickers
4. Compare predicted lines vs actual spreads to identify betting value
5. Output ranked picks with confidence levels

**Fantasy Projections**:
- RB projection system in `src/g_nfl/fantasy/projections/rb/projector.py`
- Usage-based projections incorporating team pace, touch share, and matchup data
- Confidence scoring based on role security and historical performance

## Git Workflow

**Branch strategy**:
- Work happens on **issue branches**, named with the issue number prefix (e.g. `6-deployment-refactor-fastapi-backend`)
- Issue branches merge into `dev` (via PR)
- `dev` merges into `main` for releases
- **Never commit or merge directly to `dev` or `main`** — always go through an issue branch

**Commits**:
- Follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`, `docs:`, etc.
- Include the issue number in the commit message, e.g. `feat(api): add picks endpoint (#12)`

## Development Commands

**Environment Setup**:
```bash
uv sync                # Install all dependencies (core + dev + analysis groups)
cp .env.example .env   # Then fill in Supabase keys (dashboard → Settings → API Keys)
```

**Python version**: pinned to `>=3.11,<3.13`. Python 3.13 is blocked because `nfl-data-py` pins `numpy<2` and `pandas<2`, neither of which support 3.13. Revisit when that changes (or if `nflreadpy` fully replaces it).

**Running the apps**:
```bash
make api               # FastAPI backend (src/g_nfl/api/) on :8000
make web               # React frontend (web/) on :5173, proxies /api to :8000
make run               # Legacy Streamlit app
```

**Data Analysis**:
```bash
uv run jupyter lab     # Start Jupyter for notebook analysis
```

**Linting**:
```bash
make lint              # ruff check
make format            # ruff format + autofix
```

**Data Management**:
```bash
make update-lines      # Update market lines for current week
make verify-db         # Verify database tables exist
```

**Key Constants** (`src/g_nfl/utils/config.py` — always check this file for current values rather than trusting docs):
- `CUR_SEASON`: Current NFL season
- `HFA = 1.3`: Home field advantage in points
- `AVG_POINTS = 21.5`: League average team points per game
- `SPREAD_STDEV = 11.5`: Standard deviation for spread calculations

## Deployment

- **Backend**: FastAPI on Render (`render.yaml`); build installs from `requirements.txt`, which is generated from `uv.lock` via `make deploy-prep` — regenerate it whenever core deps change
- **Frontend**: React app (`web/`) on Vercel
- Full details in `DEPLOYMENT.md`

## Related Docs

- `DEPLOYMENT.md` — Render/Vercel deployment setup and steps
- `DATA.md` — data sources and schema notes
- `RESOURCES.md` — external links and references
- `TODO.md` — long-term project roadmap (phased plan)
- `notes/` — in-flight task tracking (see Task Tracking section above)

## Data Integration Notes

**Google Sheets Integration**:
- Power ratings are maintained in shared Google Sheets by multiple contributors
- Service account authentication via `google_config.json`
- Automated pull and ranking generation in homers pipeline

**Team Name Standardization**:
Always use `standardize_teams()` when working with team data from external sources to ensure consistency with NFL data py conventions.

**Betting Line Conversion**:
- Use `percentile_to_spread()` to convert power rating percentiles to point spreads
- `guess_the_lines_ovr()` generates predicted spreads and identifies value bets
- Rankings determine pick confidence with higher differentials indicating stronger plays

## Weekly Analysis Process

1. Update week number in pick pipeline notebook
2. Run composite power ratings aggregation
3. Generate "guess the lines" analysis comparing predictions to market
4. Review ranked picks for highest value opportunities
5. Update fantasy projections for key positional matchups

The system emphasizes quantitative analysis over subjective evaluation, with composite rankings reducing individual bias and mathematical models driving betting recommendations.
