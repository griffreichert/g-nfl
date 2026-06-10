-- Fix the database constraint to allow 'mnf' as a valid pick_type
-- Run this in your Supabase SQL editor to fix the constraint violation

-- First, drop the existing constraint
ALTER TABLE picks DROP CONSTRAINT IF EXISTS picks_pick_type_check;

-- Add the updated constraint that includes 'mnf'
ALTER TABLE picks ADD CONSTRAINT picks_pick_type_check
CHECK (pick_type IN ('regular', 'best_bet', 'underdog', 'survivor', 'mnf'));

-- Verify the constraint was added correctly
SELECT constraint_name, check_clause
FROM information_schema.check_constraints
WHERE constraint_name = 'picks_pick_type_check';
