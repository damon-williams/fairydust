-- Migration script to create system user and update builder_id references
-- This allows you to safely delete your personal account for Apple SSO testing

BEGIN;

-- Create a system placeholder user (if it doesn't exist)
INSERT INTO users (
    id, 
    fairyname, 
    email, 
    is_builder, 
    is_admin, 
    is_active,
    auth_provider,
    dust_balance,
    created_at,
    updated_at
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'System',
    'system@fairydust.fun',
    true,
    true,
    true,
    'system',
    0,
    NOW(),
    NOW()
) ON CONFLICT (id) DO UPDATE SET
    fairyname = EXCLUDED.fairyname,
    email = EXCLUDED.email,
    is_builder = EXCLUDED.is_builder,
    is_admin = EXCLUDED.is_admin,
    updated_at = NOW();

-- Show current apps and builder info before migration
SELECT 
    a.name,
    a.builder_id,
    u.fairyname as current_builder
FROM apps a 
LEFT JOIN users u ON a.builder_id = u.id
ORDER BY a.name;

-- Update all apps to use the system user as builder
UPDATE apps 
SET builder_id = '00000000-0000-0000-0000-000000000001',
    updated_at = NOW()
WHERE builder_id != '00000000-0000-0000-0000-000000000001';

-- Show apps after migration
SELECT 
    a.name,
    a.builder_id,
    u.fairyname as new_builder
FROM apps a 
LEFT JOIN users u ON a.builder_id = u.id
ORDER BY a.name;

-- Show count of updated records
SELECT COUNT(*) as apps_updated 
FROM apps 
WHERE builder_id = '00000000-0000-0000-0000-000000000001';

COMMIT;