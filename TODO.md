# NFL Betting & Fantasy Analysis - Project Plan

## Phase 1: Foundation (Priority 1 - Core Infrastructure)

### Data Infrastructure
- [ ] Set up consistent data schema/database structure using CSV/pickle format
- [ ] Build reliable data ingestion for basic team stats (offense/defense yards, points, turnovers)
- [ ] Establish historical data pipeline (3-5 years for model training)
- [ ] Implement current season game results and basic team stats tracking
- [ ] Team name standardization across all data sources (`standardize_teams()`)

### Basic Power Ratings System
- [ ] Simple offensive/defensive ratings using team-level metrics
- [ ] Historical performance weighting (recent games matter more)
- [ ] Home field advantage adjustments (HFA = 1.3)
- [ ] Basic spread prediction model (`percentile_to_spread()`)
- [ ] Validate against historical spreads for accuracy

## Phase 2: Enhanced Betting System (Priority 2)

### Advanced Position-Level Power Ratings
- [ ] **QB Metrics**: EPA per play, CPOE, pressure-to-sack rate, time to throw, rushing (design vs scrambles)
- [ ] **Skill Position Metrics**: YPRR, FDPRR, RYOE, usage/target share, explosive plays, YAC
- [ ] **O-Line Metrics**: Continuity scoring, success rate, rush yards before contact
- [ ] **Pass Rush Metrics**: Pressure rate (adjusted for TTT), sack rate, EPA per pass
- [ ] **Run Defense Metrics**: EPA & success rate (win prob 25-90%), YPA, tackles for loss
- [ ] **Coverage Metrics**: Separation/catch point grades, EPA/SR per pass
- [ ] **Special Teams**: Kicker performance (completed), DVOA ratings

### Composite Rating System
- [ ] Weight positional units appropriately for overall team strength
- [ ] Add situational factors (weather, injuries, rest, coaching decisions)
- [ ] Multi-picker power rating aggregation (`homers.py`)
- [ ] Google Sheets integration for expert ratings pull
- [ ] Composite ranking generation with confidence scoring

### Pick Tracking & Pool Management
- [ ] Database schema for weekly picks storage
- [ ] Performance tracking (win rate, units won/lost, bias analysis)
- [ ] Model vs actual selection comparison tools
- [ ] Weekly schedule sheets with spreads
- [ ] Adjustment tracking and incorporation
- [ ] "Guess the Lines" analysis for value identification

## Phase 3: Fantasy Foundation (Priority 3)

### Player Data Pipeline
- [ ] Individual player stats ingestion (targets, carries, snaps, snap %)
- [ ] Injury reports and status tracking integration
- [ ] Depth chart information and role security scoring
- [ ] Red zone touch tracking and analysis
- [ ] Target distribution post-injury analysis

### Basic Fantasy Projections
- [ ] Expected fantasy points based on usage + matchup (`rb/projector.py`)
- [ ] Season-long value calculations for drafting
- [ ] Simple start/sit recommendation engine
- [ ] Weekly expected fantasy points generation
- [ ] Confidence scoring based on role security and injury risk

### Advanced Fantasy Analytics
- [ ] Pass rate over/under expectation analysis
  - [ ] Break out by early downs
  - [ ] Incorporate into weekly reporting
- [ ] Tempo analysis and pace metrics
- [ ] O-Line continuity impact on skill position players
- [ ] Coaching tendencies and 4th down decision making impact

## Phase 4: Advanced Analytics & Optimization (Priority 4)

### Fantasy Deep Dive
- [ ] Breakout candidate identification (usage trends, target share changes)
- [ ] Underperformer analysis (expected vs actual production)
- [ ] Streaming options and waiver wire target identification
- [ ] Matchup-based projection adjustments using defensive ratings

### Betting Model Refinements
- [ ] Model performance analysis and backtesting
- [ ] Edge case handling (backup QBs, weather games, short weeks)
- [ ] Line movement tracking and optimal bet timing
- [ ] Bias detection and correction in pool selections

### Automation & Reporting
- [ ] Automated weekly report generation for all metrics
- [ ] Data validation and error handling improvements
- [ ] Plotting and visualization standardization
- [ ] Performance dashboard creation

## Phase 5: Polish & Web Interface (Priority 5 - Nice to Have)

### Web Application (Optional)
- [ ] Simple site for cousins to submit weekly picks
- [ ] Dashboard showing model predictions vs actual picks
- [ ] Performance tracking visualization and historical analysis
- [ ] Real-time odds comparison and value betting alerts

## Technical Infrastructure Notes

### Current Architecture
- **Data Storage**: CSV files by source/week in `data/` directory, processed data as pickle
- **Core Config**: `src/utils/config.py` (CUR_SEASON=2024, HFA=1.3, AVG_POINTS=21.5, SPREAD_STDEV=11.5)
- **Key Utilities**: `src/utils/teams.py`, `src/utils/odds.py`, `src/utils/data.py`
- **Analysis Environment**: Jupyter notebooks for weekly analysis and model development

### Data Source Integration
- [x] NFelo scraper
- [x] Unabated scraper
- [x] ESPN scraper
- [x] Inpredictable scraper
- [ ] Sumer Sports integration
- [ ] PFF data incorporation
- [ ] Google Sheets API for power ratings
- [ ] DVOA data pulls

### Immediate Next Steps
1. Complete homers pipeline Google Sheets integration
2. Finalize percentile-to-spread conversion validation
3. Set up weekly automated data pulls for current season
4. Build pick tracking database schema
5. Establish fantasy projection baseline for RB position
