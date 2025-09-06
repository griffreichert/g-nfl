-- SQL script to create the required tables for market lines and pool spreads
-- Run this directly in your Supabase SQL Editor

-- Create market_lines table
CREATE TABLE IF NOT EXISTS market_lines (
    id BIGSERIAL PRIMARY KEY,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    game_id TEXT NOT NULL,
    spread DECIMAL(4,1),
    total DECIMAL(4,1),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(season, week, game_id)
);

-- Create indexes for better query performance on market_lines
CREATE INDEX IF NOT EXISTS idx_market_lines_season_week ON market_lines(season, week);
CREATE INDEX IF NOT EXISTS idx_market_lines_game_id ON market_lines(game_id);

-- Create pool_spreads table
CREATE TABLE IF NOT EXISTS pool_spreads (
    id BIGSERIAL PRIMARY KEY,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    game_id TEXT NOT NULL,
    spread DECIMAL(4,1) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(season, week, game_id)
);

-- Create indexes for better query performance on pool_spreads
CREATE INDEX IF NOT EXISTS idx_pool_spreads_season_week ON pool_spreads(season, week);
CREATE INDEX IF NOT EXISTS idx_pool_spreads_game_id ON pool_spreads(game_id);

-- Enable Row Level Security (RLS) if you want to restrict access
-- ALTER TABLE market_lines ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE pool_spreads ENABLE ROW LEVEL SECURITY;

-- Create policies if you enabled RLS (uncomment and modify as needed)
-- CREATE POLICY "Public read access" ON market_lines FOR SELECT USING (true);
-- CREATE POLICY "Public insert access" ON market_lines FOR INSERT WITH CHECK (true);
-- CREATE POLICY "Public update access" ON market_lines FOR UPDATE USING (true);
-- CREATE POLICY "Public delete access" ON market_lines FOR DELETE USING (true);

-- CREATE POLICY "Public read access" ON pool_spreads FOR SELECT USING (true);
-- CREATE POLICY "Public insert access" ON pool_spreads FOR INSERT WITH CHECK (true);
-- CREATE POLICY "Public update access" ON pool_spreads FOR UPDATE USING (true);
-- CREATE POLICY "Public delete access" ON pool_spreads FOR DELETE USING (true);
