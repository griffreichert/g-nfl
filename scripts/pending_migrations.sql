-- Pending migrations for the new Supabase project (cnisbhql…).
-- Run the whole file in the SQL editor; every statement is idempotent.
-- Written 2026-08-09.

-- 1. Pick notes (#65 follow-up): why a pick was made, so it can be
--    reviewed later. Applies to individual and TEAM picks alike.
ALTER TABLE picks ADD COLUMN IF NOT EXISTS note TEXT;

-- 2. pool_picks — the one table scripts/*.sql defines that this project
--    is missing. Body is scripts/pool_picks_schema.sql, inlined here so
--    this is a single paste. Holds the official pool record parsed from
--    the Cville standings workbook.
-- Pool picks: every picker's picks per week from the Cville standings workbook (#20)
-- Run this in your Supabase SQL editor

CREATE TABLE IF NOT EXISTS pool_picks (
    id SERIAL PRIMARY KEY,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,              -- 1-18 regular, 19=WC, 20=DIV, 21=CONF, 22=SB
    week_label VARCHAR(20) NOT NULL,    -- sheet name: 'Week 1', 'Wild Card', ...
    picker VARCHAR(100) NOT NULL,
    slot VARCHAR(20) NOT NULL,          -- 'bb', '2'..'6', 'udog', 'sd', 'mnf', playoff slots
    pick_type VARCHAR(20) NOT NULL CHECK (
        pick_type IN ('regular', 'best_bet', 'mnf', 'underdog', 'survivor', 'total')
    ),
    team_picked VARCHAR(10) NOT NULL,   -- team abbreviation, or OVER/UNDER for totals
    spread DECIMAL(5,1),                -- picked team's pool spread (o/u line for totals)
    game_id VARCHAR(50),                -- nflverse style: 2025_01_KC_LAC
    result VARCHAR(5),                  -- W/L/T as graded in the pool sheet
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (season, week, picker, slot)
);

CREATE INDEX IF NOT EXISTS idx_pool_picks_season_week ON pool_picks(season, week);
CREATE INDEX IF NOT EXISTS idx_pool_picks_team ON pool_picks(season, team_picked);
CREATE INDEX IF NOT EXISTS idx_pool_picks_picker ON pool_picks(picker, season);

ALTER TABLE pool_picks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Enable all operations for pool_picks" ON pool_picks;
CREATE POLICY "Enable all operations for pool_picks" ON pool_picks FOR ALL USING (true);

-- 3. Game detail page (#71). The deployed API cannot fetch nflverse
--    (nflreadpy is analysis-group only), so context is pushed here by
--    scripts/update_game_context.py, same pattern as update_results.py.

CREATE TABLE IF NOT EXISTS team_week_stats (
    id SERIAL PRIMARY KEY,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    team VARCHAR(10) NOT NULL,
    plays INTEGER,
    off_epa_play REAL,
    def_epa_play REAL,
    off_success_rate REAL,
    def_success_rate REAL,
    off_explosive_rate REAL,
    def_explosive_rate REAL,
    off_pass_epa REAL,
    off_rush_epa REAL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (season, week, team)
);

CREATE INDEX IF NOT EXISTS idx_team_week_stats_team ON team_week_stats(season, team);

ALTER TABLE team_week_stats ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Enable all operations for team_week_stats" ON team_week_stats;
CREATE POLICY "Enable all operations for team_week_stats" ON team_week_stats FOR ALL USING (true);

CREATE TABLE IF NOT EXISTS game_context (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL UNIQUE,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    away_team VARCHAR(10) NOT NULL,
    home_team VARCHAR(10) NOT NULL,
    gameday DATE,
    gametime VARCHAR(10),
    roof VARCHAR(20),
    surface VARCHAR(30),
    temp INTEGER,
    wind INTEGER,
    stadium VARCHAR(100),
    div_game BOOLEAN,
    away_rest INTEGER,
    home_rest INTEGER,
    away_qb VARCHAR(80),
    home_qb VARCHAR(80),
    away_coach VARCHAR(80),
    home_coach VARCHAR(80),
    referee VARCHAR(80),
    -- [{team, name, position, status, practice}], report_status Out/Doubtful/
    -- Questionable only. Nested because nothing queries a single injury row.
    injuries JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_game_context_season_week ON game_context(season, week);

ALTER TABLE game_context ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Enable all operations for game_context" ON game_context;
CREATE POLICY "Enable all operations for game_context" ON game_context FOR ALL USING (true);
