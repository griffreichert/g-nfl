# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an NFL betting and fantasy football analysis project that combines data science, web scraping, and betting strategy. The core focus is building power ratings systems, generating betting picks, and analyzing NFL team/player performance using advanced metrics.

**Philosophy**: "The Cleveland Browns can stay irrational longer than I can stay solvent"

> **Pool scoring is the north star.** The model and analysis exist to assist
> **Team Reichert's** weekly picks in the Cville 16 pool. Always keep the pool
> format in mind — slots (Best Bet 2pts, 5× Regular 1pt, MNF, Underdog, Survivor)
> and that ATS picks grade against the **pool spread**, not the market line.
> Full format: **`notes/SCORING.md`** (read it before any pool/model pick work).

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

### One-off analysis scripts — no `scratch/` folder

There is no in-repo scratch/scratchpad directory (removed 2026-08-09 — it had
become a dumping ground for sweep/backtest scripts whose findings never made it
into `notes/`). Disposition for a throwaway script:

- **Write it to the session scratchpad** (outside the repo, e.g.
  `/private/tmp/claude-*/.../scratchpad`), not into a repo folder.
- **The moment it produces a finding**, write that finding into the relevant
  `notes/*.md` file — table, verdict, and enough method detail to rebuild
  (see `notes/pick-analytics.md`'s "Corrected board constants" section for the
  pattern). The note is the record; the script is disposable.
- **If the script turns out to be a reusable tool** (something you'll run
  again, not a one-shot diagnostic for a single issue), it belongs under
  `src/g_nfl/`, not as a loose script.
- Never leave a script as the only copy of a result — if the repo restarted
  today, `notes/` should already have everything worth keeping.

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
- **Never commit directly to `dev` or `main`** — always go through an issue branch
- **Claude may handle git when asked** — push, open PRs, and merge issue branches into `dev` are fine on request. Otherwise commit locally only.
- **Merging to `main` is Griffin's alone** — Claude never merges (or PRs) into `main`, even if asked

**Commits**:
- Follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`, `docs:`, etc.
- Include the issue number in the commit message, e.g. `feat(api): add picks endpoint (#12)`

## Development Commands

**Environment Setup**:
```bash
uv sync                # Install all dependencies (core + dev + analysis groups)
cp .env.example .env   # Then fill in Supabase keys (dashboard → Settings → API Keys)
```

**Python version**: `>=3.11` (3.13 supported). `nfl-data-py` was the blocker (pinned `numpy<2`/`pandas<2`); it has been replaced by `nflreadpy` (#23).

**Running the apps**:
```bash
make api               # FastAPI backend (src/g_nfl/api/) on :8000
make web               # React frontend (web/) on :5173, proxies /api to :8000
make run               # Streamlit fantasy draft board (app/main.py)
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

**ML training & evaluation** (`src/g_nfl/ml/`):
```bash
make train ARGS="--seasons 2023 2024"                 # Train spread model, artifact in data/ml_models/
make backtest ARGS="--output data/ml_reports/x.md"    # Walk-forward backtest with betting metrics
```

**Backtest report policy** — do NOT commit generated report files to git:
- Full reports are scratch: write them to `data/ml_reports/` (gitignored), regenerable from code
- `reports/BASELINES.md` is the one tracked file: a curated table of benchmark models (date, git SHA, feature set, headline metrics). Append a row **only** when a model becomes the new number to beat — not for every experiment
- Full run history belongs in MLflow once #12 lands; markdown in git is not an experiment tracker

**Key Constants** (`src/g_nfl/utils/config.py` — always check this file for current values rather than trusting docs):
- `CUR_SEASON`: Current NFL season
- `HFA = 1.5`: Home field advantage in points
- `AVG_POINTS = 21.5`: League average team points per game
- `SPREAD_STDEV = 13.5`: Std of home margin (realized ~14, ~13.3 trimmed)

## Deployment

- **Backend**: FastAPI on Render (`render.yaml`); build installs from `requirements.txt`, which is generated from `uv.lock` via `make deploy-prep` — regenerate it whenever core deps change
- **Frontend**: React app (`web/`) on Vercel
- Full details in `DEPLOYMENT.md`

## Related Docs

- `DEPLOYMENT.md` — Render/Vercel deployment setup and steps
- `DATA.md` — data sources and schema notes
- `RESOURCES.md` — external links and references
- `TODO.md` — long-term project roadmap (phased plan)
- `notes/SCORING.md` — Cville 16 pool format & scoring (the north star for model/pick work)
- `notes/` — in-flight task tracking (see Task Tracking section above)

## Code Conventions

**Prefer polars over pandas.** New data code uses polars; Griffin is deliberately
leveling up polars. Keep DataFrames in polars end-to-end and only `.to_pandas()` at a
hard boundary where a consumer genuinely requires it (and prefer porting that consumer).

**Data loading: `nflreadpy`, not `nfl_data_py`.** `nfl_data_py` is deprecated by nflverse
and is being removed (see #23). Use `nflreadpy` loaders (`load_schedules`, `load_pbp`,
`load_teams`, `load_player_stats`, `load_rosters`, …) — they return polars natively.

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
