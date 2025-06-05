-- Add admin support to fairydust
-- Run this in Railway production database

-- 1. Add is_admin column if it doesn't exist
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

-- 2. Create index for admin users
CREATE INDEX IF NOT EXISTS idx_users_admin ON users(is_admin) WHERE is_admin = TRUE;

-- 3. Make your account admin
UPDATE users 
SET is_admin = TRUE 
WHERE id = '9b061774-85a0-4d5a-9a6a-bb81dc6ac61b';

-- 4. Grant you 100 DUST while we're at it
INSERT INTO dust_transactions (user_id, amount, type, description, status, created_at)
VALUES ('9b061774-85a0-4d5a-9a6a-bb81dc6ac61b', 100, 'grant', 'Admin account setup', 'completed', CURRENT_TIMESTAMP);

UPDATE users 
SET dust_balance = dust_balance + 100 
WHERE id = '9b061774-85a0-4d5a-9a6a-bb81dc6ac61b';

-- 5. Verify admin status and balance
SELECT 
    fairyname,
    email,
    is_admin,
    is_builder,
    dust_balance,
    'Admin setup complete!' as status
FROM users 
WHERE id = '9b061774-85a0-4d5a-9a6a-bb81dc6ac61b';