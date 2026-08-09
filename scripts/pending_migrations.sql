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
