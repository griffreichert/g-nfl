-- Line tables: snapshots on market_lines, and write policies on both (#58).
-- Paste the whole file into the Supabase SQL editor. Idempotent.
--
-- Two problems, one paste.
--
-- 1. `spread_line` from nflverse is the CLOSE for a past game, and during the
--    season this table holds pick-time snapshots. The old key allowed one row
--    per game, so a backfilled close would occupy the slot the Friday and
--    deadline pulls need, and afterwards the two kinds would be
--    indistinguishable. The deadline snapshot is what turns the line-arb result
--    from look-ahead into something measurable (notes/pool-spread-edge.md).
--
-- 2. RLS is enabled on `market_lines` and `pool_spreads` with no policy on
--    either, so Postgres denies every write. The backfill hits
--    "new row violates row-level security policy", and so does
--    `PUT /api/pool-spreads` behind the ManageSpreads page — which means Friday
--    line entry would have failed in week 1.
--
--    The policies below are permissive, matching `picks` and `pool_picks`:
--    anyone holding the publishable key can write. That is the existing
--    posture of this project rather than a new exposure, and the real access
--    control is the PIN/JWT layer at the API (#60). Tighten both together.
--
-- Safe to run: market_lines and pool_spreads are both empty as of 2026-08-31.

-- 1. Snapshots -------------------------------------------------------------

ALTER TABLE market_lines
    ADD COLUMN IF NOT EXISTS snapshot TEXT NOT NULL DEFAULT 'close';

ALTER TABLE market_lines DROP CONSTRAINT IF EXISTS market_lines_snapshot_check;
ALTER TABLE market_lines ADD CONSTRAINT market_lines_snapshot_check
    CHECK (snapshot IN ('open', 'friday', 'deadline', 'close'));

-- Old key: UNIQUE(season, week, game_id). Supabase names it after the columns.
ALTER TABLE market_lines DROP CONSTRAINT IF EXISTS market_lines_season_week_game_id_key;

DO $$
BEGIN
    ALTER TABLE market_lines ADD CONSTRAINT market_lines_snapshot_key
        UNIQUE (season, week, game_id, snapshot);
EXCEPTION
    WHEN duplicate_table THEN NULL;
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_market_lines_snapshot
    ON market_lines(season, week, snapshot);

-- 2. Write policies --------------------------------------------------------

ALTER TABLE market_lines ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Enable all operations for market_lines" ON market_lines;
CREATE POLICY "Enable all operations for market_lines" ON market_lines
    FOR ALL USING (true) WITH CHECK (true);

ALTER TABLE pool_spreads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Enable all operations for pool_spreads" ON pool_spreads;
CREATE POLICY "Enable all operations for pool_spreads" ON pool_spreads
    FOR ALL USING (true) WITH CHECK (true);
