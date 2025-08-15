-- Add retry metadata columns to story_images table
-- This enables front-end visibility into retry attempts for better UX

ALTER TABLE story_images 
ADD COLUMN IF NOT EXISTS attempt_number INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 3,
ADD COLUMN IF NOT EXISTS retry_reason TEXT DEFAULT NULL;

-- Add comment explaining the columns
COMMENT ON COLUMN story_images.attempt_number IS 'Current attempt number (1, 2, 3, etc.)';
COMMENT ON COLUMN story_images.max_attempts IS 'Maximum number of attempts allowed (default 3)';
COMMENT ON COLUMN story_images.retry_reason IS 'Reason for retry: nsfw, replicate_error, transient, etc.';

-- Create index for better query performance when filtering by status and retry info
CREATE INDEX IF NOT EXISTS idx_story_images_status_attempts 
ON story_images (status, attempt_number) 
WHERE status IN ('generating', 'retrying', 'failed');