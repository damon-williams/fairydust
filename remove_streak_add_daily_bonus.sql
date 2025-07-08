-- Remove streak logic and add daily bonus configuration
BEGIN;

-- Remove streak_days column from users table (keep last_login_date for daily bonus)
ALTER TABLE users DROP COLUMN IF EXISTS streak_days;
ALTER TABLE users DROP COLUMN IF EXISTS timezone;

-- Create system configuration table for admin-configurable values
CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert default daily bonus configuration
INSERT INTO system_config (key, value, description) 
VALUES ('daily_login_bonus_amount', '5', 'Amount of DUST granted for daily login bonus')
ON CONFLICT (key) DO NOTHING;

-- Update app_grants table constraint to only check daily grants (remove streak)
-- First drop the old constraint
ALTER TABLE app_grants DROP CONSTRAINT IF EXISTS app_grants_user_id_app_id_grant_type_date_key;
ALTER TABLE app_grants DROP CONSTRAINT IF EXISTS app_grants_user_id_app_id_grant_type_key;
ALTER TABLE app_grants DROP CONSTRAINT IF EXISTS app_grants_user_id_grant_type_granted_date_key;

-- Add new constraint for daily bonuses only
ALTER TABLE app_grants ADD CONSTRAINT app_grants_daily_unique 
    UNIQUE(user_id, app_id, grant_type, granted_date)
    WHERE grant_type = 'daily_bonus';

COMMIT;

-- Verify changes
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'users' AND column_name IN ('streak_days', 'timezone', 'last_login_date');

SELECT * FROM system_config WHERE key = 'daily_login_bonus_amount';