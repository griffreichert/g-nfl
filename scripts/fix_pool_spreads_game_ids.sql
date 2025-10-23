-- Fix pool_spreads game_id format to use zero-padded weeks
-- This migration updates game_ids from format '2025_1_KC_LAC' to '2025_01_KC_LAC'
-- Run this in your Supabase SQL Editor

-- Step 1: Add a temporary column to store the updated game_id
ALTER TABLE pool_spreads ADD COLUMN IF NOT EXISTS game_id_new TEXT;

-- Step 2: Update the new column with zero-padded week format
-- This handles weeks 1-9 that need padding
UPDATE pool_spreads
SET game_id_new =
    CASE
        -- For single-digit weeks (1-9), add zero padding
        WHEN game_id ~ '^[0-9]{4}_[0-9]_[A-Z]+_[A-Z]+$' THEN
            REGEXP_REPLACE(game_id, '^([0-9]{4})_([0-9])_([A-Z]+)_([A-Z]+)$', '\1_0\2_\3_\4')
        -- For double-digit weeks (10-18), keep as is
        ELSE game_id
    END;

-- Step 3: Verify the update (optional - run separately to check)
-- SELECT game_id AS old_id, game_id_new AS new_id
-- FROM pool_spreads
-- WHERE game_id != game_id_new;

-- Step 4: Drop the old game_id column
ALTER TABLE pool_spreads DROP COLUMN game_id;

-- Step 5: Rename the new column to game_id
ALTER TABLE pool_spreads RENAME COLUMN game_id_new TO game_id;

-- Step 6: Recreate the unique constraint
ALTER TABLE pool_spreads DROP CONSTRAINT IF EXISTS pool_spreads_season_week_game_id_key;
ALTER TABLE pool_spreads ADD CONSTRAINT pool_spreads_season_week_game_id_key UNIQUE(season, week, game_id);

-- Step 7: Recreate the index
DROP INDEX IF EXISTS idx_pool_spreads_game_id;
CREATE INDEX idx_pool_spreads_game_id ON pool_spreads(game_id);

-- Done! All pool_spreads game_ids should now use zero-padded week format
