-- Migration: Add question history tracking for Would You Rather duplicates
-- Run this with: psql $DATABASE_URL -f scripts/add_question_history.sql

BEGIN;

-- Create table for tracking user's question history
CREATE TABLE IF NOT EXISTS user_question_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    question_hash TEXT NOT NULL,
    question_content JSONB NOT NULL,
    game_session_id UUID REFERENCES wyr_game_sessions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_user_question_hash ON user_question_history(user_id, question_hash);
CREATE INDEX IF NOT EXISTS idx_user_question_created ON user_question_history(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_question_history_session ON user_question_history(game_session_id);

-- Verify table was created
SELECT 'user_question_history table created successfully' as status;

COMMIT;