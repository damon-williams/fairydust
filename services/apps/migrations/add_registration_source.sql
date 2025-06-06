-- Add registration source tracking to apps table
ALTER TABLE apps 
ADD COLUMN registration_source VARCHAR(50) DEFAULT 'web',
ADD COLUMN registered_by_service UUID,
ADD COLUMN registration_metadata JSONB DEFAULT '{}';

-- Add index for querying by registration source
CREATE INDEX idx_apps_registration_source ON apps(registration_source);
CREATE INDEX idx_apps_registered_by_service ON apps(registered_by_service);

-- Add comments for clarity
COMMENT ON COLUMN apps.registration_source IS 'Source of registration: web, mcp, api, admin';
COMMENT ON COLUMN apps.registered_by_service IS 'Service account ID if registered via service token';
COMMENT ON COLUMN apps.registration_metadata IS 'Additional metadata about registration (MCP version, etc.)';