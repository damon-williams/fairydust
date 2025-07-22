-- Add timezone support to users table
-- This allows streak calculations to be done in user's local timezone

BEGIN;

-- Add timezone column to users table
-- Default to 'America/Los_Angeles' for existing users (can be updated later)
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'America/Los_Angeles';

-- Create index for timezone queries if needed
CREATE INDEX IF NOT EXISTS idx_users_timezone ON users(timezone);

-- Update existing users based on their last login patterns if possible
-- For now, we'll keep the default and let users update it themselves

COMMIT;

-- Verify the change
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'users' AND column_name = 'timezone';