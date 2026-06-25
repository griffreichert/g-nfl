-- Final game results, populated by scripts/update_results.py from nflverse.
-- The deployed API can't fetch nflverse data (nflreadpy is an analysis-group
-- dep), so results are pushed here and standings are graded from this table.
-- Run this in your Supabase SQL editor.

CREATE TABLE IF NOT EXISTS game_results (
    id SERIAL PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL UNIQUE,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    away_team VARCHAR(10) NOT NULL,
    home_team VARCHAR(10) NOT NULL,
    away_score INTEGER,
    home_score INTEGER,
    -- home margin: home_score - away_score (nflverse `result`)
    result INTEGER,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_game_results_season_week ON game_results(season, week);

ALTER TABLE game_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable all operations for game_results" ON game_results FOR ALL USING (true);
