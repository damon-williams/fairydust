-- Add unique constraint to prevent duplicate referral redemptions
-- This prevents the same user from redeeming the same referral code multiple times

-- First, check if the constraint already exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_constraint 
        WHERE conname = 'referral_redemptions_referral_code_referee_user_id_key'
    ) THEN
        -- Add the unique constraint
        ALTER TABLE referral_redemptions 
        ADD CONSTRAINT referral_redemptions_referral_code_referee_user_id_key 
        UNIQUE (referral_code, referee_user_id);
        
        RAISE NOTICE 'Added unique constraint on referral_redemptions(referral_code, referee_user_id)';
    ELSE
        RAISE NOTICE 'Unique constraint already exists on referral_redemptions';
    END IF;
END $$;