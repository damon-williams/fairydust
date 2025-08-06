-- Cleanup script to drop llm_usage_logs table after migration is complete
-- Run this ONLY after:
-- 1. Running migrate_llm_to_ai_logs.sql
-- 2. Verifying all data is in ai_usage_logs
-- 3. Testing that analytics work correctly

-- First, verify the migration was successful
DO $$
DECLARE
    llm_count integer;
    ai_text_count integer;
BEGIN
    -- Check if llm_usage_logs table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_name = 'llm_usage_logs' AND table_schema = 'public') THEN
        
        SELECT COUNT(*) INTO llm_count FROM llm_usage_logs;
        SELECT COUNT(*) INTO ai_text_count FROM ai_usage_logs WHERE model_type = 'text';
        
        RAISE NOTICE 'Current state:';
        RAISE NOTICE '- Records in llm_usage_logs: %', llm_count;
        RAISE NOTICE '- Text records in ai_usage_logs: %', ai_text_count;
        
        -- Safety check: don't drop if ai_usage_logs is empty but llm_usage_logs has data
        IF llm_count > 0 AND ai_text_count = 0 THEN
            RAISE EXCEPTION 'SAFETY CHECK FAILED: llm_usage_logs has data but ai_usage_logs has no text records. Migration may not have completed.';
        END IF;
        
        -- Warn if we're about to lose data
        IF llm_count > ai_text_count THEN
            RAISE WARNING 'WARNING: llm_usage_logs has % records but ai_usage_logs only has % text records. Some data may be lost.', llm_count, ai_text_count;
        END IF;
        
    ELSE
        RAISE NOTICE 'llm_usage_logs table does not exist - cleanup already complete';
        RETURN;
    END IF;
END $$;

-- Create a backup of the table structure (just in case)
CREATE TABLE IF NOT EXISTS llm_usage_logs_backup_schema AS 
SELECT * FROM llm_usage_logs WHERE 1=0;

-- Drop the old table and its indexes
DROP TABLE IF EXISTS llm_usage_logs CASCADE;

-- Also drop any related views or functions that might reference the old table
-- (Add any specific cleanup here if needed)

-- Confirm cleanup
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables 
                   WHERE table_name = 'llm_usage_logs' AND table_schema = 'public') THEN
        RAISE NOTICE 'SUCCESS: llm_usage_logs table has been dropped';
        RAISE NOTICE 'All AI usage logging now uses the unified ai_usage_logs table';
    ELSE
        RAISE NOTICE 'ERROR: llm_usage_logs table still exists';
    END IF;
END $$;