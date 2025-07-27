# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an NFL betting and fantasy football analysis project that combines data science, web scraping, and betting strategy. The core focus is building power ratings systems, generating betting picks, and analyzing NFL team/player performance using advanced metrics.

**Philosophy**: "The Cleveland Browns can stay irrational longer than I can stay solvent"

## Key Architecture Components

### Data Pipeline
- **External Data Sources**: Multiple scraped sources including NFelo, PFF, Unabated, ESPN, Inpredictable, and Sumer Sports
- **NFL Data**: Primary data source is `nfl_data_py` for play-by-play and statistical data
- **Storage**: CSV files organized by source and week in `data/` directory, with some processed data as pickle files

### Core Modules

**Power Ratings Engine** (`src/modelling/`):
- `homers.py`: Multi-picker power rating system with Google Sheets integration
- `utils.py`: Core betting utilities including spread prediction and line conversion
- `metrics.py`: Advanced NFL metrics and success rate calculations

**Data Processing** (`src/utils/`):
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
- RB projection system in `src/fantasy/projections/rb/projector.py`
- Usage-based projections incorporating team pace, touch share, and matchup data
- Confidence scoring based on role security and historical performance

## Development Commands

**Environment Setup**:
```bash
poetry install          # Install dependencies
poetry shell           # Activate virtual environment
```

**Data Analysis**:
```bash
jupyter lab            # Start Jupyter for notebook analysis
python src/fantasy/projections/rb/projector.py  # Run RB projections
```

**Key Constants** (src/utils/config.py):
- `CUR_SEASON = 2024`: Current NFL season
- `HFA = 1.3`: Home field advantage in points
- `AVG_POINTS = 21.5`: League average team points per game
- `SPREAD_STDEV = 11.5`: Standard deviation for spread calculations

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
