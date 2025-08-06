-- Migration: Refactor app_model_configs to support multi-model architecture
-- Date: 2025-08-05
-- Description: Split model configurations by type and add global fallback support

BEGIN;

-- 1. Create new tables
-- ===================

-- Create new app_model_configs table with model_type
CREATE TABLE IF NOT EXISTS app_model_configs_new (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id UUID NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    model_type VARCHAR(20) NOT NULL CHECK (model_type IN ('text', 'image', 'video')),
    provider VARCHAR(50) NOT NULL,
    model_id VARCHAR(200) NOT NULL,
    parameters JSONB DEFAULT '{}',
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(app_id, model_type)
);

-- Create indexes
CREATE INDEX idx_app_model_configs_new_app_id ON app_model_configs_new(app_id);
CREATE INDEX idx_app_model_configs_new_model_type ON app_model_configs_new(model_type);

-- Create global fallback models table
CREATE TABLE IF NOT EXISTS global_fallback_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_type VARCHAR(20) NOT NULL CHECK (model_type IN ('text', 'image', 'video')),
    primary_provider VARCHAR(50) NOT NULL,
    primary_model_id VARCHAR(200) NOT NULL,
    fallback_provider VARCHAR(50) NOT NULL,
    fallback_model_id VARCHAR(200) NOT NULL,
    trigger_condition VARCHAR(50) NOT NULL, -- 'provider_error', 'rate_limit', 'cost_threshold'
    priority INTEGER DEFAULT 1, -- For multiple fallbacks
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(model_type, primary_provider, primary_model_id, fallback_provider, fallback_model_id)
);

-- Create index
CREATE INDEX idx_global_fallback_models_type ON global_fallback_models(model_type, is_active);

-- 2. Migrate existing data
-- ========================

-- Migrate text model configurations
INSERT INTO app_model_configs_new (app_id, model_type, provider, model_id, parameters, is_enabled)
SELECT 
    app_id,
    'text' as model_type,
    primary_provider,
    primary_model_id,
    jsonb_build_object(
        'temperature', COALESCE(primary_parameters->>'temperature', '0.7')::float,
        'max_tokens', COALESCE(primary_parameters->>'max_tokens', '1000')::int,
        'top_p', COALESCE(primary_parameters->>'top_p', '0.9')::float
    ),
    true
FROM app_model_configs
WHERE primary_provider IS NOT NULL AND primary_model_id IS NOT NULL;

-- Migrate image model configurations
INSERT INTO app_model_configs_new (app_id, model_type, provider, model_id, parameters, is_enabled)
SELECT 
    app_id,
    'image' as model_type,
    'replicate' as provider, -- Default provider for images
    COALESCE(primary_parameters->'image_models'->>'standard_model', 'black-forest-labs/flux-1.1-pro'),
    jsonb_build_object(
        'standard_model', COALESCE(primary_parameters->'image_models'->>'standard_model', 'black-forest-labs/flux-1.1-pro'),
        'reference_model', COALESCE(primary_parameters->'image_models'->>'reference_model', 'runwayml/gen4-image')
    ),
    primary_parameters->'image_models' IS NOT NULL
FROM app_model_configs
WHERE primary_parameters->'image_models' IS NOT NULL;

-- Migrate video model configurations
INSERT INTO app_model_configs_new (app_id, model_type, provider, model_id, parameters, is_enabled)
SELECT 
    app_id,
    'video' as model_type,
    'runwayml' as provider, -- Default provider for videos
    COALESCE(primary_parameters->'video_models'->>'standard_model', 'runwayml/gen4-video'),
    jsonb_build_object(
        'standard_model', COALESCE(primary_parameters->'video_models'->>'standard_model', 'runwayml/gen4-video')
    ),
    primary_parameters->'video_models' IS NOT NULL
FROM app_model_configs
WHERE primary_parameters->'video_models' IS NOT NULL;

-- 3. Create default global fallbacks
-- ==================================

-- Text model fallbacks
INSERT INTO global_fallback_models (model_type, primary_provider, primary_model_id, fallback_provider, fallback_model_id, trigger_condition, priority)
VALUES 
    ('text', 'anthropic', 'claude-3-5-sonnet-20241022', 'anthropic', 'claude-3-5-haiku-20241022', 'provider_error', 1),
    ('text', 'anthropic', 'claude-3-5-sonnet-20241022', 'openai', 'gpt-4o', 'provider_error', 2),
    ('text', 'anthropic', 'claude-3-5-haiku-20241022', 'openai', 'gpt-4o-mini', 'provider_error', 1),
    ('text', 'openai', 'gpt-4o', 'anthropic', 'claude-3-5-sonnet-20241022', 'provider_error', 1),
    ('text', 'openai', 'gpt-4o-mini', 'anthropic', 'claude-3-5-haiku-20241022', 'provider_error', 1);

-- Image model fallbacks
INSERT INTO global_fallback_models (model_type, primary_provider, primary_model_id, fallback_provider, fallback_model_id, trigger_condition, priority)
VALUES 
    ('image', 'replicate', 'black-forest-labs/flux-1.1-pro', 'replicate', 'black-forest-labs/flux-schnell', 'provider_error', 1),
    ('image', 'replicate', 'runwayml/gen4-image', 'replicate', 'black-forest-labs/flux-1.1-pro', 'provider_error', 1);

-- 4. Rename tables
-- ================

ALTER TABLE app_model_configs RENAME TO app_model_configs_old;
ALTER TABLE app_model_configs_new RENAME TO app_model_configs;

-- 5. Create helper view for easy querying
-- =======================================

CREATE OR REPLACE VIEW app_model_summary AS
SELECT 
    a.id as app_id,
    a.name as app_name,
    a.slug as app_slug,
    COALESCE(
        jsonb_object_agg(
            amc.model_type, 
            jsonb_build_object(
                'provider', amc.provider,
                'model_id', amc.model_id,
                'parameters', amc.parameters,
                'is_enabled', amc.is_enabled
            )
        ) FILTER (WHERE amc.model_type IS NOT NULL),
        '{}'::jsonb
    ) as model_configs
FROM apps a
LEFT JOIN app_model_configs amc ON a.id = amc.app_id AND amc.is_enabled = true
GROUP BY a.id, a.name, a.slug;

COMMIT;

-- To rollback if needed:
-- BEGIN;
-- DROP VIEW IF EXISTS app_model_summary;
-- DROP TABLE IF EXISTS app_model_configs;
-- ALTER TABLE app_model_configs_old RENAME TO app_model_configs;
-- DROP TABLE IF EXISTS global_fallback_models;
-- COMMIT;