-- Script to register yoga-playlist-agents app in fairydust
-- This simulates the app registration and approval process

-- First, let's create a builder user for the yoga app (if not exists)
INSERT INTO users (
    id,
    fairyname,
    email,
    is_builder,
    is_active,
    dust_balance,
    auth_provider,
    created_at,
    updated_at
) VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,  -- Fixed UUID for the builder
    'yoga-playlist-builder',
    'builder@yoga-playlist.app',
    true,  -- is_builder
    true,  -- is_active
    1000,  -- Initial DUST balance for testing
    'email',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
) ON CONFLICT (id) DO NOTHING;

-- Now register the yoga-playlist-agents app
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
    admin_notes,
    created_at,
    updated_at
) VALUES (
    '7f3e4d2c-1a5b-4c3d-8e7f-9b8a7c6d5e4f'::uuid,  -- Fixed UUID for the app
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,  -- Builder ID from above
    'Yoga Playlist Generator',
    'yoga-playlist-generator',
    'AI-powered yoga playlist generator that creates custom Spotify playlists matching your yoga flow. Choose between basic flows (5 DUST) or extended sessions (8 DUST) with perfectly synchronized music.',
    'https://yoga-playlist.app/icon.png',
    5,  -- Default dust_per_use (will be overridden by button config)
    'approved',  -- Pre-approved for immediate use
    'creative',  -- App category
    'https://yoga-playlist.app',
    'https://yoga-playlist.app/demo',
    'https://yoga-playlist.app/api/fairydust-webhook',  -- For future webhooks
    true,  -- is_active
    'Pre-approved app for fairydust integration demo. Variable pricing: 5 DUST for basic, 8 DUST for extended.',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
) ON CONFLICT (id) DO UPDATE SET
    status = 'approved',
    is_active = true,
    admin_notes = 'Pre-approved app for fairydust integration demo. Variable pricing: 5 DUST for basic, 8 DUST for extended.',
    updated_at = CURRENT_TIMESTAMP;

-- Output the app details
SELECT 
    'App registered successfully!' as message,
    id as app_id,
    name,
    slug,
    status,
    is_active
FROM apps 
WHERE id = '7f3e4d2c-1a5b-4c3d-8e7f-9b8a7c6d5e4f'::uuid;