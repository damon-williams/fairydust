-- Migration: Create video generation jobs table for async processing
-- Run this with: psql $DATABASE_URL -f scripts/create_video_jobs_table.sql

BEGIN;

-- Create video generation jobs table
CREATE TABLE IF NOT EXISTS video_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    generation_type VARCHAR(20) NOT NULL, -- 'text_to_video' | 'image_to_video'
    
    -- Input parameters (stored as JSONB for flexibility)
    input_parameters JSONB NOT NULL,
    
    -- Progress tracking
    replicate_prediction_id VARCHAR(100),
    replicate_status VARCHAR(20), -- 'starting' | 'processing' | 'succeeded' | 'failed'
    estimated_completion_seconds INT DEFAULT 180,
    
    -- Results
    video_id UUID, -- FK to user_videos table when completed
    video_url TEXT,
    thumbnail_url TEXT,
    generation_metadata JSONB,
    
    -- Error handling
    error_code VARCHAR(50),
    error_message TEXT,
    error_details JSONB,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('queued', 'starting', 'processing', 'completed', 'failed', 'cancelled')),
    CONSTRAINT valid_generation_type CHECK (generation_type IN ('text_to_video', 'image_to_video'))
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_video_jobs_user_id ON video_generation_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_video_jobs_status ON video_generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_video_jobs_created_at ON video_generation_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_video_jobs_replicate_id ON video_generation_jobs(replicate_prediction_id);
CREATE INDEX IF NOT EXISTS idx_video_jobs_user_status ON video_generation_jobs(user_id, status);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to auto-update updated_at
CREATE TRIGGER update_video_jobs_updated_at 
    BEFORE UPDATE ON video_generation_jobs 
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

-- Verify table was created
SELECT 'video_generation_jobs table created successfully' as status;

COMMIT;