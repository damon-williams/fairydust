-- Fix app_grants constraint to allow daily_bonus
BEGIN;

-- First, let's see what the current constraint allows
-- DROP the existing check constraint 
ALTER TABLE app_grants DROP CONSTRAINT IF EXISTS app_grants_grant_type_check;

-- Update existing 'streak' grant types to 'daily_bonus' 
UPDATE app_grants SET grant_type = 'daily_bonus' WHERE grant_type = 'streak';

-- Add new check constraint that includes daily_bonus
ALTER TABLE app_grants ADD CONSTRAINT app_grants_grant_type_check 
    CHECK (grant_type IN ('initial', 'referral_bonus', 'referee_bonus', 'milestone_bonus', 'promotional', 'daily_bonus'));

-- Also clean up the idempotency keys to remove 'streak' references if any
UPDATE app_grants 
SET idempotency_key = REPLACE(idempotency_key, 'streak', 'daily_bonus') 
WHERE idempotency_key LIKE '%streak%';

COMMIT;

-- Verify the changes
SELECT DISTINCT grant_type FROM app_grants;
SELECT COUNT(*) as daily_bonus_count FROM app_grants WHERE grant_type = 'daily_bonus';