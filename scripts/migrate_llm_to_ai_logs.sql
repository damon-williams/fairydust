-- Migration script to move all llm_usage_logs data to ai_usage_logs
-- Run this once to consolidate all AI model usage tracking into a single table

-- First, let's see what we're working with
DO $$
DECLARE
    llm_count integer;
    ai_count integer;
BEGIN
    SELECT COUNT(*) INTO llm_count FROM llm_usage_logs;
    SELECT COUNT(*) INTO ai_count FROM ai_usage_logs WHERE model_type = 'text';
    
    RAISE NOTICE 'Records in llm_usage_logs: %', llm_count;
    RAISE NOTICE 'Text records in ai_usage_logs: %', ai_count;
END $$;

-- Migrate all llm_usage_logs to ai_usage_logs with model_type = 'text'
INSERT INTO ai_usage_logs (
    id,
    user_id, 
    app_id,
    model_type,
    provider,
    model_id,
    prompt_tokens,
    completion_tokens,
    cost_usd,
    latency_ms,
    was_fallback,
    fallback_reason,
    request_metadata,
    created_at,
    images_generated,
    videos_generated
)
SELECT 
    id,
    user_id,
    app_id,
    'text' as model_type,  -- Set model_type for all LLM logs
    provider,
    model_id,
    prompt_tokens,
    completion_tokens,
    cost_usd,
    latency_ms,
    was_fallback,
    fallback_reason,
    request_metadata,
    created_at,
    0 as images_generated,  -- LLM logs don't generate images
    0 as videos_generated   -- LLM logs don't generate videos
FROM llm_usage_logs
WHERE id NOT IN (
    -- Avoid duplicates if migration was run partially before
    SELECT id FROM ai_usage_logs WHERE model_type = 'text'
);

-- Report migration results
DO $$
DECLARE
    migrated_count integer;
    total_ai_count integer;
BEGIN
    SELECT COUNT(*) INTO migrated_count FROM ai_usage_logs WHERE model_type = 'text';
    SELECT COUNT(*) INTO total_ai_count FROM ai_usage_logs;
    
    RAISE NOTICE 'Migration completed!';
    RAISE NOTICE 'Text records now in ai_usage_logs: %', migrated_count;
    RAISE NOTICE 'Total records in ai_usage_logs: %', total_ai_count;
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '1. Verify data looks correct in ai_usage_logs';
    RAISE NOTICE '2. Update all services to log to ai_usage_logs only';
    RAISE NOTICE '3. Test analytics thoroughly';
    RAISE NOTICE '4. Drop llm_usage_logs table when ready';
END $$;