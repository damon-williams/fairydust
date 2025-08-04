-- Create unified AI usage tracking table for text, image, and video models
-- This replaces the need for separate tables per model type

CREATE TABLE IF NOT EXISTS ai_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    app_id UUID NOT NULL,
    
    -- Model identification
    model_type VARCHAR(20) NOT NULL CHECK (model_type IN ('text', 'image', 'video')),
    provider VARCHAR(50) NOT NULL,
    model_id VARCHAR(200) NOT NULL,
    
    -- Usage metrics (varies by model type)
    -- Text models
    prompt_tokens INTEGER DEFAULT NULL,
    completion_tokens INTEGER DEFAULT NULL,
    total_tokens INTEGER DEFAULT NULL,
    
    -- Image models
    images_generated INTEGER DEFAULT NULL,
    image_dimensions VARCHAR(20) DEFAULT NULL, -- e.g., "1024x1024"
    
    -- Video models (for future use)
    videos_generated INTEGER DEFAULT NULL,
    video_duration_seconds DECIMAL(10,2) DEFAULT NULL,
    video_resolution VARCHAR(20) DEFAULT NULL, -- e.g., "1080p"
    
    -- Common metrics
    cost_usd DECIMAL(12,8) NOT NULL,
    latency_ms INTEGER NOT NULL,
    
    -- Request details
    prompt_hash VARCHAR(64), -- SHA-256 hash of the prompt/request
    finish_reason VARCHAR(50),
    was_fallback BOOLEAN DEFAULT FALSE,
    fallback_reason TEXT,
    
    -- Metadata and context
    request_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (app_id) REFERENCES apps(id) ON DELETE CASCADE
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_user_id ON ai_usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_app_id ON ai_usage_logs(app_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_model_type ON ai_usage_logs(model_type);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_provider ON ai_usage_logs(provider);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_created_at ON ai_usage_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_cost_usd ON ai_usage_logs(cost_usd);

-- Composite indexes for analytics queries
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_analytics ON ai_usage_logs(model_type, provider, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_app_analytics ON ai_usage_logs(app_id, model_type, created_at);

-- Add comments for documentation
COMMENT ON TABLE ai_usage_logs IS 'Unified tracking for all AI model usage (text, image, video)';
COMMENT ON COLUMN ai_usage_logs.model_type IS 'Type of AI model: text, image, or video';
COMMENT ON COLUMN ai_usage_logs.prompt_tokens IS 'Input tokens for text models (NULL for image/video)';
COMMENT ON COLUMN ai_usage_logs.completion_tokens IS 'Output tokens for text models (NULL for image/video)';
COMMENT ON COLUMN ai_usage_logs.images_generated IS 'Number of images generated (NULL for text/video)';
COMMENT ON COLUMN ai_usage_logs.videos_generated IS 'Number of videos generated (NULL for text/image)';
COMMENT ON COLUMN ai_usage_logs.cost_usd IS 'Actual cost at time of generation (never recalculate)';
COMMENT ON COLUMN ai_usage_logs.request_metadata IS 'JSON metadata including action, user context, etc.';

-- Create a view that unions old LLM logs with new AI logs for backward compatibility
CREATE OR REPLACE VIEW unified_ai_usage AS 
SELECT 
    id,
    user_id,
    app_id,
    'text' as model_type,
    provider,
    model_id,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    NULL as images_generated,
    NULL as image_dimensions,
    NULL as videos_generated,
    NULL as video_duration_seconds,
    NULL as video_resolution,
    cost_usd,
    latency_ms,
    prompt_hash,
    finish_reason,
    was_fallback,
    fallback_reason,
    request_metadata,
    created_at
FROM llm_usage_logs
UNION ALL
SELECT 
    id,
    user_id,
    app_id,
    model_type,
    provider,
    model_id,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    images_generated,
    image_dimensions,
    videos_generated,
    video_duration_seconds,
    video_resolution,
    cost_usd,
    latency_ms,
    prompt_hash,
    finish_reason,
    was_fallback,
    fallback_reason,
    request_metadata,
    created_at
FROM ai_usage_logs;

COMMENT ON VIEW unified_ai_usage IS 'Unified view of all AI usage (legacy LLM logs + new AI logs)';