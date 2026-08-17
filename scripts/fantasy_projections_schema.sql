-- Season-total fantasy stat-line projections (issue #81).
--
-- Filled by `make ingest-fantasy` (g_nfl.fantasy.ingest), which Griffin runs
-- by hand. The API never scrapes: a broken source leaves the last good
-- snapshot serving, and there is no scrape in the request path to blow a
-- Render cold start.
--
-- (snapshot_date, source) is the natural version. Keeping every snapshot
-- rather than overwriting gives projection history for free, and lets a second
-- source land beside ESPN with no migration.
--
-- Run this in your Supabase SQL editor.

CREATE TABLE IF NOT EXISTS fantasy_projections (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    source VARCHAR(30) NOT NULL,
    season INTEGER NOT NULL,
    -- nflverse gsis_id: the join key every other fantasy table uses.
    player_id VARCHAR(20) NOT NULL,
    player_name VARCHAR(80),
    position VARCHAR(5),
    team VARCHAR(10),
    -- Stat line, season totals. Rushing and receiving touchdowns stay
    -- separate: #81's sketch collapsed them into one `td`, but scoring.py
    -- prices them independently and a TE-premium league prices receptions
    -- against them, so collapsing here would lose information the board needs.
    pass_yd NUMERIC,
    pass_td NUMERIC,
    ints NUMERIC,
    rush_yd NUMERIC,
    rush_td NUMERIC,
    rec NUMERIC,
    rec_yd NUMERIC,
    rec_td NUMERIC,
    fum NUMERIC,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (snapshot_date, source, player_id)
);

-- The read the board does: newest snapshot for a source and season.
CREATE INDEX IF NOT EXISTS idx_fantasy_projections_snapshot
    ON fantasy_projections(source, season, snapshot_date DESC);

ALTER TABLE fantasy_projections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable all operations for fantasy_projections"
    ON fantasy_projections FOR ALL USING (true);
