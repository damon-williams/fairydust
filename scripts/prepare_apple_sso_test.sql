-- Script to prepare for Apple SSO testing as a new user
-- This removes Apple provider links so SSO will create a fresh account

-- First, check your current OAuth providers
SELECT 
    u.id,
    u.fairyname,
    u.email,
    uap.provider,
    uap.provider_user_id,
    u.is_admin
FROM users u
LEFT JOIN user_auth_providers uap ON u.id = uap.user_id
WHERE u.email = 'YOUR_CURRENT_EMAIL@gmail.com';  -- Update this

-- Option 1: Just remove Apple provider (keeps account, but Apple SSO will create new one)
/*
DELETE FROM user_auth_providers 
WHERE user_id = 'YOUR_USER_ID'  -- Update this
AND provider = 'apple';
*/

-- Option 2: See what would happen if you remove all OAuth providers
/*
SELECT * FROM user_auth_providers 
WHERE user_id = 'YOUR_USER_ID';  -- Update this
*/

-- Option 3: Nuclear option - completely remove Apple traces
/*
BEGIN;
-- Remove Apple provider link
DELETE FROM user_auth_providers 
WHERE user_id = 'YOUR_USER_ID'  -- Update this
AND provider = 'apple';

-- Change email to ensure no email-based matching
UPDATE users 
SET email = 'old.admin@fairydust.archive'  -- Or any non-conflicting email
WHERE id = 'YOUR_USER_ID';  -- Update this

COMMIT;
*/

-- IMPORTANT: Make sure you have another admin account before doing this!
-- Check for other admins:
SELECT fairyname, email, is_admin 
FROM users 
WHERE is_admin = true;