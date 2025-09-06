# NFL Betting & Fantasy Analysis

*The Cleveland Browns can stay irrational longer than I can stay solvent*

## Overview

A comprehensive NFL analysis system combining power ratings for spread betting and fantasy football player evaluation. The project focuses on building robust, position-level team ratings to identify betting value and optimize fantasy lineup decisions across multiple leagues. The system emphasizes data reliability and quantitative analysis over subjective evaluation.

## Setup

This project uses Python with Poetry for dependency management:

```bash
poetry install          # Install dependencies
poetry shell           # Activate virtual environment
jupyter lab            # Start Jupyter for analysis notebooks
```

Key dependencies include `nfl_data_py` for NFL data, pandas/numpy for analysis, and various scraping libraries for external data sources.

## Modelling / Picks

The betting system centers around multi-layered power ratings that convert team strength into spread predictions:

**Power Ratings Pipeline:**
- **Basic Level**: Team offensive/defensive ratings using historical performance data
- **Advanced Level**: Position-group breakdowns (QB, skill positions, O-line, pass rush, run defense, coverage)
- **Integration**: Composite rankings from multiple expert sources via Google Sheets

**Pick Generation:**
- Convert power rating percentiles to predicted spreads using `calc_percentile_to_gpf()`
- Compare model predictions against actual betting lines to identify value
- Track pool performance and identify biases in selection patterns
- Generate confidence-ranked weekly picks for spread betting contests

**Key Components:**
- `src/modelling/homers.py`: Multi-picker power rating aggregation
- `src/modelling/utils.py`: Spread prediction and line conversion utilities
- `notebooks/picks/pick-pipeline.ipynb`: Weekly picks generation workflow

## Fantasy

The fantasy analysis system provides player evaluation and projection tools across multiple league formats:

**Player Projections:**
- Usage-based projections incorporating target share, snap counts, and touch distribution
- Matchup analysis using team defensive ratings and pace metrics
- Confidence scoring based on role security and injury risk

**Analysis Focus:**
- **Season Value**: Draft rankings with upside/risk assessment
- **Weekly Optimization**: Start/sit recommendations and streaming options
- **Breakout Identification**: Usage trend analysis and target share changes
- **Value Detection**: Expected vs actual fantasy point analysis

**Key Components:**
- `src/fantasy/projections/rb/projector.py`: Running back projection engine
- Position-specific notebooks for weekly analysis and player evaluation
- Integration with power ratings for defensive matchup assessment


Update market lines
```zsh
python scripts/update_market_lines.py --season 2025 --week 1
```
