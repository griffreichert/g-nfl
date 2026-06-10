-- Fix pick_type constraint to allow MNF picks
-- Run this in your Supabase SQL editor

-- Drop the existing constraint
ALTER TABLE picks DROP CONSTRAINT IF EXISTS picks_pick_type_check;

-- Add the updated constraint with 'mnf' included
ALTER TABLE picks ADD CONSTRAINT picks_pick_type_check
CHECK (pick_type IN ('regular', 'best_bet', 'underdog', 'survivor', 'mnf'));
