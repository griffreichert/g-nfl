-- Add pick_type column to existing picks table
ALTER TABLE picks
ADD COLUMN pick_type VARCHAR(20) DEFAULT 'regular' CHECK (pick_type IN ('regular', 'best_bet', 'underdog', 'survivor', 'mnf'));

-- Update existing records to have 'regular' pick_type
UPDATE picks SET pick_type = 'regular' WHERE pick_type IS NULL;
