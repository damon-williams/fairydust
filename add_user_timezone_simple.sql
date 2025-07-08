-- Add timezone to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'America/Los_Angeles';

-- Common US timezones for reference:
-- 'America/New_York' (Eastern)
-- 'America/Chicago' (Central)
-- 'America/Denver' (Mountain)
-- 'America/Los_Angeles' (Pacific)
-- 'America/Phoenix' (Arizona)
-- 'Pacific/Honolulu' (Hawaii)