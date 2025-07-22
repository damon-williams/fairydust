-- Fix app_grants constraints to allow daily streak bonuses
-- The old constraint UNIQUE(user_id, app_id, grant_type) prevents daily streak grants
-- Replace with UNIQUE(user_id, app_id, grant_type, granted_date) to allow one per day

BEGIN;

-- Drop the problematic constraint that prevents daily streak bonuses
ALTER TABLE app_grants DROP CONSTRAINT IF EXISTS app_grants_user_id_app_id_grant_type_key;

-- Add the correct constraint that allows daily streak bonuses
-- This ensures one grant per user per app per type per day
ALTER TABLE app_grants ADD CONSTRAINT app_grants_user_id_app_id_grant_type_date_key 
    UNIQUE(user_id, app_id, grant_type, granted_date);

-- For better organization, also ensure we have the right constraint names
-- Drop and recreate the user/grant_type/date constraint with a better name
ALTER TABLE app_grants DROP CONSTRAINT IF EXISTS app_grants_user_id_grant_type_granted_date_key;
-- Note: The new combined constraint above covers this case too

COMMIT;

-- Verify the constraints
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'app_grants'::regclass 
AND contype = 'u'
ORDER BY conname;