-- Simple Supabase schema for NFL picks
-- Run this in your Supabase SQL editor

CREATE TABLE picks (
    id SERIAL PRIMARY KEY,
    picker VARCHAR(100) NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    team_picked VARCHAR(10) NOT NULL,
    spread DECIMAL(5,1),
    season INTEGER DEFAULT 2024,
    week INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX idx_picks_picker_week ON picks(picker, season, week);
CREATE INDEX idx_picks_game ON picks(game_id);

-- Enable RLS (optional)
ALTER TABLE picks ENABLE ROW LEVEL SECURITY;

-- Allow all operations for now (adjust based on your auth needs)
CREATE POLICY "Enable all operations for picks" ON picks FOR ALL USING (true);
