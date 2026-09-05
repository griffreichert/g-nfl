-- gModel's weekly board and the run that produced it (issue #13).
--
-- Two tables because a run is one row of configuration and sixteen rows of
-- numbers. `model_runs` holds what a prediction rebuilds from: feature set,
-- target, hyperparameters, training seasons, code SHA. `model_predictions`
-- holds the board, every game on the slate rather than the seven that became
-- an entry.
--
-- `fingerprint` hashes the predictions and the lines together. A Wednesday
-- and a Saturday run of the same week differ (new injuries, restated
-- play-by-play, a corrected line) and are both kept; a cron retry against
-- unchanged inputs lands on the row already there.
--
-- Run this in your Supabase SQL editor.

CREATE TABLE IF NOT EXISTS model_runs (
    run_id UUID PRIMARY KEY,
    model VARCHAR(30) NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    feature_set VARCHAR(30) NOT NULL,
    target VARCHAR(20) NOT NULL,
    carryover_k NUMERIC,
    train_seasons JSONB NOT NULL,
    params JSONB NOT NULL,
    git_sha VARCHAR(40),
    n_games INTEGER,
    -- whether this run is the one that wrote gModel's picks for the week
    submitted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (season, week, model, fingerprint)
);

CREATE TABLE IF NOT EXISTS model_predictions (
    id SERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES model_runs(run_id) ON DELETE CASCADE,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    home_team VARCHAR(10) NOT NULL,
    away_team VARCHAR(10) NOT NULL,
    -- the model's own line, as a home margin
    pred_margin NUMERIC NOT NULL,
    pool_spread NUMERIC,
    market_spread NUMERIC,
    -- pred_margin minus the line it was graded against; positive favours home
    edge NUMERIC,
    line_source VARCHAR(10),
    home_win_prob NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (run_id, game_id)
);

-- The read the board does: this week's latest run.
CREATE INDEX IF NOT EXISTS idx_model_runs_week
    ON model_runs(model, season, week, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_model_predictions_game
    ON model_predictions(season, week, game_id);

ALTER TABLE model_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_predictions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable all operations for model_runs"
    ON model_runs FOR ALL USING (true);

CREATE POLICY "Enable all operations for model_predictions"
    ON model_predictions FOR ALL USING (true);
