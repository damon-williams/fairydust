-- SQL to populate fairydust apps and LLM configurations
-- Run this in your production database

-- First, let's see what users exist to use as builders
-- SELECT id, fairyname, email, is_builder FROM users WHERE is_builder = true LIMIT 5;

-- Create some sample apps if they don't exist
-- You'll need to replace 'your-builder-user-id' with an actual UUID from your users table

-- fairydust-inspire app
INSERT INTO apps (
    id,
    builder_id,
    name,
    slug,
    description,
    icon_url,
    dust_per_use,
    status,
    category,
    website_url,
    demo_url,
    callback_url,
    is_active,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    (SELECT id FROM users WHERE is_builder = true LIMIT 1), -- Use first builder user
    'fairydust inspire',
    'fairydust-inspire',
    'Get inspired with personalized creative suggestions and ideas tailored to your interests and goals.',
    'https://via.placeholder.com/64x64?text=✨',
    5,
    'approved',
    'creative',
    'https://fairydust.ai/inspire',
    'https://demo.fairydust.ai/inspire',
    'https://api.fairydust.ai/inspire/callback',
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
) ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

-- fairydust-recipe app  
INSERT INTO apps (
    id,
    builder_id,
    name,
    slug,
    description,
    icon_url,
    dust_per_use,
    status,
    category,
    website_url,
    demo_url,
    callback_url,
    is_active,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    (SELECT id FROM users WHERE is_builder = true LIMIT 1), -- Use first builder user
    'fairydust recipe',
    'fairydust-recipe',
    'Discover personalized recipes based on your dietary preferences, available ingredients, and cooking skill level.',
    'https://via.placeholder.com/64x64?text=🍳',
    8,
    'approved', 
    'productivity',
    'https://fairydust.ai/recipe',
    'https://demo.fairydust.ai/recipe',
    'https://api.fairydust.ai/recipe/callback',
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
) ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

-- Sample third-party app
INSERT INTO apps (
    id,
    builder_id,
    name,
    slug,
    description,
    icon_url,
    dust_per_use,
    status,
    category,
    website_url,
    demo_url,
    callback_url,
    is_active,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    (SELECT id FROM users WHERE is_builder = true LIMIT 1), -- Use first builder user
    'Smart Study Assistant',
    'smart-study-assistant',
    'AI-powered study companion that creates personalized study plans and quizzes based on your learning style.',
    'https://via.placeholder.com/64x64?text=📚',
    6,
    'pending',
    'education',
    'https://studyassistant.ai',
    'https://demo.studyassistant.ai',
    'https://api.studyassistant.ai/callback',
    false,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
) ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;

-- Now create LLM model configurations for the apps
-- This will use the existing logic from shared/database.py but with explicit UUIDs

-- Configuration for fairydust-inspire
INSERT INTO app_model_configs (
    id,
    app_id,
    primary_provider,
    primary_model_id,
    primary_parameters,
    fallback_models,
    cost_limits,
    feature_flags,
    created_at,
    updated_at
)
SELECT 
    gen_random_uuid(),
    a.id,
    'anthropic',
    'claude-3-5-haiku-20241022',
    '{"temperature": 0.8, "max_tokens": 150, "top_p": 0.9}'::jsonb,
    '[{
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "trigger": "provider_error",
        "parameters": {"temperature": 0.8, "max_tokens": 150}
    }]'::jsonb,
    '{"per_request_max": 0.05, "daily_max": 10.0, "monthly_max": 100.0}'::jsonb,
    '{"streaming_enabled": true, "cache_responses": true, "log_prompts": false}'::jsonb,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM apps a
WHERE a.slug = 'fairydust-inspire'
ON CONFLICT (app_id) DO UPDATE SET
    primary_provider = EXCLUDED.primary_provider,
    primary_model_id = EXCLUDED.primary_model_id,
    primary_parameters = EXCLUDED.primary_parameters,
    fallback_models = EXCLUDED.fallback_models,
    cost_limits = EXCLUDED.cost_limits,
    feature_flags = EXCLUDED.feature_flags,
    updated_at = CURRENT_TIMESTAMP;

-- Configuration for fairydust-recipe
INSERT INTO app_model_configs (
    id,
    app_id,
    primary_provider,
    primary_model_id,
    primary_parameters,
    fallback_models,
    cost_limits,
    feature_flags,
    created_at,
    updated_at
)
SELECT 
    gen_random_uuid(),
    a.id,
    'anthropic',
    'claude-3-5-sonnet-20241022',
    '{"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}'::jsonb,
    '[{
        "provider": "openai",
        "model_id": "gpt-4o",
        "trigger": "provider_error",
        "parameters": {"temperature": 0.7, "max_tokens": 1000}
    }, {
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "trigger": "cost_threshold_exceeded",
        "parameters": {"temperature": 0.7, "max_tokens": 1000}
    }]'::jsonb,
    '{"per_request_max": 0.15, "daily_max": 25.0, "monthly_max": 200.0}'::jsonb,
    '{"streaming_enabled": true, "cache_responses": true, "log_prompts": false}'::jsonb,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM apps a
WHERE a.slug = 'fairydust-recipe'
ON CONFLICT (app_id) DO UPDATE SET
    primary_provider = EXCLUDED.primary_provider,
    primary_model_id = EXCLUDED.primary_model_id,
    primary_parameters = EXCLUDED.primary_parameters,
    fallback_models = EXCLUDED.fallback_models,
    cost_limits = EXCLUDED.cost_limits,
    feature_flags = EXCLUDED.feature_flags,
    updated_at = CURRENT_TIMESTAMP;

-- Configuration for third-party app (basic config)
INSERT INTO app_model_configs (
    id,
    app_id,
    primary_provider,
    primary_model_id,
    primary_parameters,
    fallback_models,
    cost_limits,
    feature_flags,
    created_at,
    updated_at
)
SELECT 
    gen_random_uuid(),
    a.id,
    'anthropic',
    'claude-3-5-haiku-20241022',
    '{"temperature": 0.8, "max_tokens": 200, "top_p": 0.9}'::jsonb,
    '[{
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "trigger": "provider_error",
        "parameters": {"temperature": 0.8, "max_tokens": 200}
    }]'::jsonb,
    '{"per_request_max": 0.05, "daily_max": 15.0, "monthly_max": 150.0}'::jsonb,
    '{"streaming_enabled": true, "cache_responses": true, "log_prompts": false}'::jsonb,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM apps a
WHERE a.slug = 'smart-study-assistant'
ON CONFLICT (app_id) DO UPDATE SET
    primary_provider = EXCLUDED.primary_provider,
    primary_model_id = EXCLUDED.primary_model_id,
    primary_parameters = EXCLUDED.primary_parameters,
    fallback_models = EXCLUDED.fallback_models,
    cost_limits = EXCLUDED.cost_limits,
    feature_flags = EXCLUDED.feature_flags,
    updated_at = CURRENT_TIMESTAMP;

-- Verify the data was created
SELECT 
    a.name,
    a.slug,
    a.status,
    a.is_active,
    c.primary_provider,
    c.primary_model_id
FROM apps a
LEFT JOIN app_model_configs c ON a.id = c.app_id
ORDER BY a.name;

-- Show the JSON configurations
SELECT 
    a.name,
    c.primary_parameters,
    c.fallback_models,
    c.cost_limits,
    c.feature_flags
FROM apps a
JOIN app_model_configs c ON a.id = c.app_id
ORDER BY a.name;