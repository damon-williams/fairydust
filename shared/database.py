# shared/database.py
import os
import ssl
from contextlib import asynccontextmanager
from typing import Any, Optional

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Build from individual components if DATABASE_URL not provided
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "fairydust")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    # Fix Railway's postgres:// to postgresql:// for asyncpg compatibility
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Connection pool
_pool: Optional[asyncpg.Pool] = None


class Database:
    """Database wrapper for asyncpg with connection pooling"""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_one(self, query: str, *args) -> Optional[dict[str, Any]]:
        """Fetch a single row"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetch_all(self, query: str, *args) -> list[dict[str, Any]]:
        """Fetch multiple rows"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def execute_schema(self, query: str, *args) -> str:
        """Execute a schema/DDL query with extended timeout"""
        async with self.pool.acquire() as conn:
            # Use 5 minute timeout for schema operations
            return await conn.execute(query, *args, timeout=300)

    async def execute_many(self, query: str, args_list: list[tuple]) -> None:
        """Execute a query multiple times with different arguments"""
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args_list)

    @asynccontextmanager
    async def transaction(self):
        """Context manager for database transactions"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn


async def init_db():
    """Initialize database connection pool"""
    import logging

    logger = logging.getLogger(__name__)
    global _pool

    try:
        logger.info("Starting database initialization...")

        # Configure SSL for production environments
        ssl_context = None
        environment = os.getenv("ENVIRONMENT", "development")

        if environment in ["production", "staging"]:
            # Create SSL context for production/staging (Railway requires this)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        # Service-specific connection pool configuration
        # These can be overridden via environment variables
        default_min_size = 3
        default_max_size = 8

        # Service-specific defaults based on usage patterns
        service_name = os.getenv("SERVICE_NAME", "unknown")
        if service_name == "identity":
            default_min_size = 5  # High frequency auth requests
            default_max_size = 15
        elif service_name == "content":
            default_min_size = 3  # Fewer but longer operations (story generation)
            default_max_size = 10
        elif service_name == "apps":
            default_min_size = 2  # Moderate usage
            default_max_size = 8
        elif service_name == "ledger":
            default_min_size = 4  # Frequent small transactions
            default_max_size = 12
        elif service_name in ["admin", "builder"]:
            default_min_size = 1  # Low usage, occasional access
            default_max_size = 3

        # Allow environment variable overrides
        min_size = int(os.getenv("DB_POOL_MIN_SIZE", default_min_size))
        max_size = int(os.getenv("DB_POOL_MAX_SIZE", default_max_size))

        logger.info(
            f"Creating database connection pool for {service_name} service (min: {min_size}, max: {max_size})..."
        )
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            ssl=ssl_context,
            min_size=min_size,
            max_size=max_size,
            max_queries=50000,
            max_cached_statement_lifetime=300,
            command_timeout=30,  # Reduced default timeout to fail faster
            max_inactive_connection_lifetime=300,  # Close inactive connections
        )
        logger.info("Database connection pool created successfully")

        # Create tables if they don't exist (skip in production if SKIP_SCHEMA_INIT is set)
        skip_schema_init = os.getenv("SKIP_SCHEMA_INIT", "false").lower() == "true"
        if not skip_schema_init:
            logger.info("Starting schema creation/update...")
            await create_tables()
            logger.info("Schema creation/update completed")
        else:
            logger.info("Skipping schema initialization (SKIP_SCHEMA_INIT=true)")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        if _pool:
            await _pool.close()
            _pool = None
        raise


async def close_db():
    """Close database connection pool"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_db() -> Database:
    """Dependency to get database instance"""
    if not _pool:
        await init_db()
    return Database(_pool)


async def create_tables():
    """Create database tables if they don't exist"""
    import logging

    logger = logging.getLogger(__name__)

    # Use a longer timeout for schema operations but with progress logging
    db = await get_db()
    logger.info("Starting database schema creation/update...")

    # Test connection first
    await db.execute("SELECT 1")
    logger.info("Database connection verified")

    # Users table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            fairyname VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE,
            phone VARCHAR(20) UNIQUE,
            avatar_url TEXT,
            is_builder BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            dust_balance INTEGER DEFAULT 0,
            auth_provider VARCHAR(50) NOT NULL,
            first_name VARCHAR(100),
            birth_date DATE,
            city VARCHAR(100),
            country VARCHAR(100) DEFAULT 'US',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT check_contact CHECK (email IS NOT NULL OR phone IS NOT NULL)
        );

        CREATE INDEX IF NOT EXISTS idx_users_fairyname ON users(fairyname);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
        CREATE INDEX IF NOT EXISTS idx_users_login ON users(id, last_login_date);
    """
    )

    # Add new profile columns to existing users table
    await db.execute_schema(
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(100);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date DATE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(100);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS country VARCHAR(100) DEFAULT 'US';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_date TIMESTAMP WITH TIME ZONE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_onboarding_completed BOOLEAN DEFAULT FALSE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_uploaded_at TIMESTAMP WITH TIME ZONE;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_size_bytes INTEGER;

        -- Drop old age_range column (replaced with birth_date)
        ALTER TABLE users DROP COLUMN IF EXISTS age_range;
        
        -- Drop old profiling columns (no longer used)
        ALTER TABLE users DROP COLUMN IF EXISTS last_profiling_session;
        ALTER TABLE users DROP COLUMN IF EXISTS total_profiling_sessions;
    """
    )

    # User auth providers table (for OAuth)
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_auth_providers (
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL,
            provider_user_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, provider)
        );

        CREATE INDEX IF NOT EXISTS idx_auth_providers_lookup
        ON user_auth_providers(provider, provider_user_id);
    """
    )

    # DUST transactions table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS dust_transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL,
            type VARCHAR(50) NOT NULL,
            description TEXT,
            app_id UUID,
            idempotency_key VARCHAR(255) UNIQUE,
            status VARCHAR(50) DEFAULT 'completed',
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_dust_transactions_user
        ON dust_transactions(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_dust_transactions_app
        ON dust_transactions(app_id, created_at DESC);
    """
    )

    # Apps table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS apps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            builder_id UUID REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(255) UNIQUE NOT NULL,
            description TEXT NOT NULL,
            icon_url TEXT,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            category VARCHAR(100) NOT NULL,
            is_active BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_apps_builder ON apps(builder_id);
        CREATE INDEX IF NOT EXISTS idx_apps_slug ON apps(slug);
        CREATE INDEX IF NOT EXISTS idx_apps_status ON apps(status);
        CREATE INDEX IF NOT EXISTS idx_apps_category ON apps(category);
        
        -- Remove unused columns from apps table
        ALTER TABLE apps DROP COLUMN IF EXISTS dust_per_use;
        ALTER TABLE apps DROP COLUMN IF EXISTS website_url;
        ALTER TABLE apps DROP COLUMN IF EXISTS demo_url;
        ALTER TABLE apps DROP COLUMN IF EXISTS callback_url;
        ALTER TABLE apps DROP COLUMN IF EXISTS admin_notes;
        ALTER TABLE apps DROP COLUMN IF EXISTS is_approved;
        ALTER TABLE apps DROP COLUMN IF EXISTS registration_source;
        ALTER TABLE apps DROP COLUMN IF EXISTS registered_by_service;
        ALTER TABLE apps DROP COLUMN IF EXISTS registration_metadata;
    """
    )

    # Hourly analytics aggregation table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS hourly_app_stats (
            app_id UUID REFERENCES apps(id) ON DELETE CASCADE,
            hour TIMESTAMP WITH TIME ZONE NOT NULL,
            unique_users INTEGER NOT NULL DEFAULT 0,
            transactions INTEGER NOT NULL DEFAULT 0,
            dust_consumed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (app_id, hour)
        );

        CREATE INDEX IF NOT EXISTS idx_hourly_stats_hour
        ON hourly_app_stats(hour DESC);
    """
    )

    # Progressive Profiling Tables
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_profile_data (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category VARCHAR(50) NOT NULL,
            field_name VARCHAR(100) NOT NULL,
            field_value JSONB NOT NULL,
            confidence_score FLOAT DEFAULT 1.0,
            source VARCHAR(50) DEFAULT 'user_input',
            app_context VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, field_name),
            CONSTRAINT check_confidence_score CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
        );

        CREATE INDEX IF NOT EXISTS idx_user_profile_data_user_id ON user_profile_data(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_profile_data_category ON user_profile_data(category);
        CREATE INDEX IF NOT EXISTS idx_user_profile_data_field_name ON user_profile_data(field_name);
        CREATE INDEX IF NOT EXISTS idx_user_profile_data_composite ON user_profile_data(user_id, category, field_name);
        CREATE INDEX IF NOT EXISTS idx_user_profile_data_updated_at ON user_profile_data(updated_at);
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS people_in_my_life (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            birth_date DATE,
            relationship VARCHAR(100),
            photo_url TEXT,
            photo_uploaded_at TIMESTAMP WITH TIME ZONE,
            photo_size_bytes INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_people_in_my_life_user_id ON people_in_my_life(user_id);

        -- Add birth_date column to existing people_in_my_life table
        ALTER TABLE people_in_my_life ADD COLUMN IF NOT EXISTS birth_date DATE;

        -- Add photo-related columns to existing people_in_my_life table
        ALTER TABLE people_in_my_life ADD COLUMN IF NOT EXISTS photo_url TEXT;
        ALTER TABLE people_in_my_life ADD COLUMN IF NOT EXISTS photo_uploaded_at TIMESTAMP WITH TIME ZONE;
        ALTER TABLE people_in_my_life ADD COLUMN IF NOT EXISTS photo_size_bytes INTEGER;

        -- Drop old age_range column from people_in_my_life (replaced with birth_date)
        ALTER TABLE people_in_my_life DROP COLUMN IF EXISTS age_range;
    """
    )

    # User onboard tracking table - app milestones and UI tip tracking
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_onboard_tracking (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            has_used_inspire BOOLEAN DEFAULT FALSE,
            has_completed_first_inspiration BOOLEAN DEFAULT FALSE,
            onboarding_step VARCHAR(50),
            has_seen_inspire_tip BOOLEAN DEFAULT FALSE,
            has_seen_inspire_result_tip BOOLEAN DEFAULT FALSE,
            has_seen_onboarding_complete_tip BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_onboard_tracking_step ON user_onboard_tracking(onboarding_step);
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS person_profile_data (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            person_id UUID NOT NULL REFERENCES people_in_my_life(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category VARCHAR(50) NOT NULL,
            field_name VARCHAR(100) NOT NULL,
            field_value JSONB NOT NULL,
            confidence_score FLOAT DEFAULT 1.0,
            source VARCHAR(50) DEFAULT 'user_input',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(person_id, field_name)
        );

        CREATE INDEX IF NOT EXISTS idx_person_profile_data_user_id ON person_profile_data(user_id);
        CREATE INDEX IF NOT EXISTS idx_person_profile_data_person_id ON person_profile_data(person_id);
    """
    )

    # Performance indexes
    await db.execute_schema(
        """
        CREATE INDEX IF NOT EXISTS idx_dust_tx_user_type_created
        ON dust_transactions(user_id, type, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_dust_tx_idempotency
        ON dust_transactions(idempotency_key)
        WHERE idempotency_key IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_dust_tx_pending
        ON dust_transactions(status, created_at)
        WHERE status = 'pending';
    """
    )

    # LLM Architecture Tables
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS app_model_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            app_id UUID NOT NULL REFERENCES apps(id) ON DELETE CASCADE,

            -- Primary model configuration
            primary_provider VARCHAR(50) NOT NULL,
            primary_model_id VARCHAR(100) NOT NULL,
            primary_parameters JSONB DEFAULT '{}',

            -- Fallback models (array of objects)
            fallback_models JSONB DEFAULT '[]',

            -- Cost and usage limits
            cost_limits JSONB DEFAULT '{}',

            -- Feature flags
            feature_flags JSONB DEFAULT '{}',

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(app_id)
        );

        CREATE INDEX IF NOT EXISTS idx_app_model_configs_app_id ON app_model_configs(app_id);
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS llm_usage_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            app_id UUID NOT NULL REFERENCES apps(id) ON DELETE CASCADE,

            -- Model information
            provider VARCHAR(50) NOT NULL,
            model_id VARCHAR(100) NOT NULL,

            -- Usage metrics
            prompt_tokens INTEGER NOT NULL,
            completion_tokens INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,

            -- Cost and performance
            cost_usd DECIMAL(10, 6) NOT NULL,
            latency_ms INTEGER NOT NULL,

            -- Request metadata
            prompt_hash VARCHAR(64),
            finish_reason VARCHAR(50),
            was_fallback BOOLEAN DEFAULT FALSE,
            fallback_reason VARCHAR(100),

            -- Context
            request_metadata JSONB DEFAULT '{}',

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_user_id ON llm_usage_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_app_id ON llm_usage_logs(app_id);
        CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_created_at ON llm_usage_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_cost ON llm_usage_logs(cost_usd);
        CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_provider_model ON llm_usage_logs(provider, model_id);
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS llm_cost_tracking (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            app_id UUID REFERENCES apps(id) ON DELETE CASCADE,

            -- Time period
            tracking_date DATE NOT NULL,
            tracking_month VARCHAR(7) NOT NULL,

            -- Aggregated metrics
            total_requests INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            total_cost_usd DECIMAL(10, 6) DEFAULT 0,

            -- Model breakdown
            model_usage JSONB DEFAULT '{}',

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(user_id, app_id, tracking_date)
        );

        CREATE INDEX IF NOT EXISTS idx_llm_cost_tracking_user_date ON llm_cost_tracking(user_id, tracking_date);
        CREATE INDEX IF NOT EXISTS idx_llm_cost_tracking_month ON llm_cost_tracking(tracking_month);
        CREATE INDEX IF NOT EXISTS idx_llm_cost_tracking_app_date ON llm_cost_tracking(app_id, tracking_date);
    """
    )

    # Insert default model configurations for existing apps
    # First, try to insert configurations for apps that exist
    await db.execute_schema(
        """
        INSERT INTO app_model_configs (
            app_id, primary_provider, primary_model_id, primary_parameters,
            fallback_models, cost_limits, feature_flags
        )
        SELECT
            a.id,
            CASE
                WHEN a.slug = 'fairydust-inspire' THEN 'anthropic'
                WHEN a.slug = 'fairydust-recipe' THEN 'anthropic'
                WHEN a.slug = 'fairydust-fortune-teller' THEN 'anthropic'
                ELSE 'anthropic'
            END,
            CASE
                WHEN a.slug = 'fairydust-inspire' THEN 'claude-3-5-haiku-20241022'
                WHEN a.slug = 'fairydust-recipe' THEN 'claude-3-5-sonnet-20241022'
                WHEN a.slug = 'fairydust-fortune-teller' THEN 'claude-3-5-sonnet-20241022'
                ELSE 'claude-3-5-haiku-20241022'
            END,
            CASE
                WHEN a.slug = 'fairydust-inspire' THEN '{"temperature": 0.8, "max_tokens": 150, "top_p": 0.9}'::jsonb
                WHEN a.slug = 'fairydust-recipe' THEN '{"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}'::jsonb
                WHEN a.slug = 'fairydust-fortune-teller' THEN '{"temperature": 0.8, "max_tokens": 400, "top_p": 0.9}'::jsonb
                ELSE '{"temperature": 0.8, "max_tokens": 150, "top_p": 0.9}'::jsonb
            END,
            CASE
                WHEN a.slug = 'fairydust-inspire' THEN '[
                    {
                        "provider": "openai",
                        "model_id": "gpt-4o-mini",
                        "trigger": "provider_error",
                        "parameters": {"temperature": 0.8, "max_tokens": 150}
                    }
                ]'::jsonb
                WHEN a.slug = 'fairydust-recipe' THEN '[
                    {
                        "provider": "openai",
                        "model_id": "gpt-4o",
                        "trigger": "provider_error",
                        "parameters": {"temperature": 0.7, "max_tokens": 1000}
                    },
                    {
                        "provider": "openai",
                        "model_id": "gpt-4o-mini",
                        "trigger": "cost_threshold_exceeded",
                        "parameters": {"temperature": 0.7, "max_tokens": 1000}
                    }
                ]'::jsonb
                WHEN a.slug = 'fairydust-fortune-teller' THEN '[
                    {
                        "provider": "openai",
                        "model_id": "gpt-4o",
                        "trigger": "provider_error",
                        "parameters": {"temperature": 0.8, "max_tokens": 400}
                    }
                ]'::jsonb
                ELSE '[]'::jsonb
            END,
            CASE
                WHEN a.slug = 'fairydust-inspire' THEN '{"per_request_max": 0.05, "daily_max": 10.0, "monthly_max": 100.0}'::jsonb
                WHEN a.slug = 'fairydust-recipe' THEN '{"per_request_max": 0.15, "daily_max": 25.0, "monthly_max": 200.0}'::jsonb
                WHEN a.slug = 'fairydust-fortune-teller' THEN '{"per_request_max": 0.10, "daily_max": 15.0, "monthly_max": 150.0}'::jsonb
                ELSE '{"per_request_max": 0.05, "daily_max": 10.0, "monthly_max": 100.0}'::jsonb
            END,
            '{"streaming_enabled": true, "cache_responses": true, "log_prompts": false}'::jsonb
        FROM apps a
        WHERE a.slug IN ('fairydust-inspire', 'fairydust-recipe', 'fairydust-fortune-teller')
        ON CONFLICT (app_id) DO UPDATE SET
            primary_provider = EXCLUDED.primary_provider,
            primary_model_id = EXCLUDED.primary_model_id,
            primary_parameters = EXCLUDED.primary_parameters,
            fallback_models = EXCLUDED.fallback_models,
            cost_limits = EXCLUDED.cost_limits,
            feature_flags = EXCLUDED.feature_flags,
            updated_at = CURRENT_TIMESTAMP;
    """
    )

    # User Recipes table for app-specific content storage
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_recipes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            app_id VARCHAR(255) NOT NULL,
            title VARCHAR(500),
            content TEXT NOT NULL,
            category VARCHAR(255),
            metadata JSONB DEFAULT '{}',
            is_favorited BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_recipes_user_id ON user_recipes(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_recipes_created_at ON user_recipes(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_user_recipes_app_id ON user_recipes(app_id);
        CREATE INDEX IF NOT EXISTS idx_user_recipes_favorited ON user_recipes(user_id, is_favorited) WHERE is_favorited = TRUE;
        CREATE INDEX IF NOT EXISTS idx_user_recipes_user_app ON user_recipes(user_id, app_id);
    """
    )

    # User Stories table for story app (genre column removed for simplification)
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_stories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            story_length VARCHAR(20) NOT NULL,
            characters_involved JSONB DEFAULT '[]',
            metadata JSONB DEFAULT '{}',
            is_favorited BOOLEAN DEFAULT FALSE,
            word_count INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_stories_user_id ON user_stories(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_stories_created_at ON user_stories(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_user_stories_favorited ON user_stories(user_id, is_favorited) WHERE is_favorited = TRUE;
        CREATE INDEX IF NOT EXISTS idx_user_stories_story_length ON user_stories(story_length);
    """
    )

    # Add target_audience column to user_stories table
    await db.execute_schema(
        """
        ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS target_audience VARCHAR(20) DEFAULT 'kids';
        """
    )

    # Create index for target_audience after column is added
    await db.execute_schema(
        """
        CREATE INDEX IF NOT EXISTS idx_user_stories_target_audience ON user_stories(target_audience);
        """
    )

    # Remove genre column and index (story app simplification)
    try:
        # Check if genre column exists before trying to drop it
        genre_exists = await db.fetch_one(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'user_stories' AND column_name = 'genre'
            """
        )

        if genre_exists:
            await db.execute_schema(
                """
                DROP INDEX IF EXISTS idx_user_stories_genre;
                ALTER TABLE user_stories DROP COLUMN genre;
                """
            )
            logger.info("Removed genre column from user_stories table")
        else:
            logger.info("Genre column already removed from user_stories table")
    except Exception as e:
        logger.warning(f"Genre column migration failed: {e}")

    # Remove dust_cost column (content service should not handle DUST)
    try:
        # Check if dust_cost column exists before trying to drop it
        dust_cost_exists = await db.fetch_one(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'user_stories' AND column_name = 'dust_cost'
            """
        )

        if dust_cost_exists:
            await db.execute_schema(
                """
                ALTER TABLE user_stories DROP COLUMN dust_cost;
                """
            )
            logger.info("Removed dust_cost column from user_stories table")
        else:
            logger.info("dust_cost column already removed from user_stories table")
    except Exception as e:
        logger.warning(f"dust_cost column migration failed: {e}")

    # Allow target_person_id to be NULL for self-readings
    try:
        await db.execute_schema(
            """
            ALTER TABLE fortune_readings ALTER COLUMN target_person_id DROP NOT NULL;
            """
        )
        logger.info("Made target_person_id nullable in fortune_readings table")
    except Exception as e:
        logger.warning(f"Fortune readings target_person_id migration failed: {e}")

    # Drop old columns that are no longer needed
    try:
        # Drop age_range from users table if it exists
        await db.execute_schema(
            """
            ALTER TABLE users DROP COLUMN IF EXISTS age_range;
            ALTER TABLE users DROP COLUMN IF EXISTS fortune_profile;
            """
        )
        logger.info("Dropped age_range and fortune_profile columns from users table")
    except Exception as e:
        logger.warning(f"Failed to drop old columns from users table: {e}")

    try:
        # Drop age_range from people_in_my_life table if it exists
        await db.execute_schema(
            """
            ALTER TABLE people_in_my_life DROP COLUMN IF EXISTS age_range;
            """
        )
        logger.info("Dropped age_range column from people_in_my_life table")
    except Exception as e:
        logger.warning(f"Failed to drop age_range from people_in_my_life table: {e}")

    # Story generation logs table for analytics and debugging
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS story_generation_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            story_id UUID REFERENCES user_stories(id) ON DELETE SET NULL,
            generation_prompt TEXT NOT NULL,
            llm_model VARCHAR(100),
            tokens_used INTEGER,
            generation_time_ms INTEGER,
            success BOOLEAN NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_story_logs_user_id ON story_generation_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_story_logs_created_at ON story_generation_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_story_logs_success ON story_generation_logs(success, created_at DESC);
    """
    )

    # Restaurant App Tables - Execute each statement separately for better error handling
    try:
        await db.execute_schema(
            """
            CREATE TABLE IF NOT EXISTS restaurant_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                session_data JSONB DEFAULT '{}',
                excluded_restaurants TEXT[] DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL
            );
        """
        )

        await db.execute_schema(
            """
            CREATE INDEX IF NOT EXISTS idx_restaurant_sessions_user_expires
            ON restaurant_sessions(user_id, expires_at);
        """
        )

        await db.execute_schema(
            """
            CREATE INDEX IF NOT EXISTS idx_restaurant_sessions_expires
            ON restaurant_sessions(expires_at);
        """
        )
    except Exception as e:
        logger.warning(f"Restaurant sessions table creation failed (may already exist): {e}")

    try:
        await db.execute_schema(
            """
            CREATE TABLE IF NOT EXISTS restaurant_cache (
                place_id VARCHAR(255) PRIMARY KEY,
                restaurant_data JSONB NOT NULL,
                location_hash VARCHAR(64) NOT NULL,
                search_params_hash VARCHAR(64),
                cached_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL
            );
        """
        )

        await db.execute_schema(
            """
            CREATE INDEX IF NOT EXISTS idx_restaurant_cache_location
            ON restaurant_cache(location_hash, expires_at);
        """
        )

        await db.execute_schema(
            """
            CREATE INDEX IF NOT EXISTS idx_restaurant_cache_expires
            ON restaurant_cache(expires_at);
        """
        )
    except Exception as e:
        logger.warning(f"Restaurant cache table creation failed (may already exist): {e}")

    # Insert restaurant app if it doesn't exist
    try:
        await db.execute_schema(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url,
                status, category, is_active, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Restaurant',
                'fairydust-restaurant',
                'Find restaurants based on your group''s preferences',
                NULL,
                'approved',
                'lifestyle',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-restaurant'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Restaurant app creation failed (may already exist): {e}")

    # Insert activity app if it doesn't exist
    try:
        await db.execute_schema(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url,
                status, category, is_active, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Activity',
                'fairydust-activity',
                'Discover personalized activities and attractions based on your location and preferences',
                NULL,
                'approved',
                'lifestyle',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-activity'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Activity app creation failed (may already exist): {e}")

    # User Inspirations table for Inspire app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_inspirations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            category VARCHAR(50) NOT NULL,
            is_favorited BOOLEAN DEFAULT FALSE,
            session_id UUID,
            model_used VARCHAR(100),
            tokens_used INTEGER,
            cost_usd DECIMAL(10, 6),
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_inspirations_user_id ON user_inspirations(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_inspirations_created_at ON user_inspirations(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_user_inspirations_category ON user_inspirations(category);
        CREATE INDEX IF NOT EXISTS idx_user_inspirations_favorited ON user_inspirations(user_id, is_favorited) WHERE is_favorited = TRUE;
        CREATE INDEX IF NOT EXISTS idx_user_inspirations_active ON user_inspirations(user_id, created_at DESC) WHERE deleted_at IS NULL;
    """
    )

    # Insert inspire app if it doesn't exist
    try:
        await db.execute_schema(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url,
                status, category, is_active, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Inspire',
                'fairydust-inspire',
                'Get personalized inspirations and challenges for daily motivation',
                NULL,
                'approved',
                'lifestyle',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-inspire'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Inspire app creation failed (may already exist): {e}")

    # Fortune Readings table for Fortune Teller app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS fortune_readings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            target_person_id UUID REFERENCES people_in_my_life(id) ON DELETE CASCADE,
            target_person_name VARCHAR(100) NOT NULL,
            reading_type VARCHAR(20) NOT NULL CHECK (reading_type IN ('question', 'daily')),
            question TEXT,
            content TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            is_favorited BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_fortune_readings_user_id ON fortune_readings(user_id);
        CREATE INDEX IF NOT EXISTS idx_fortune_readings_created_at ON fortune_readings(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fortune_readings_favorited ON fortune_readings(user_id, is_favorited) WHERE is_favorited = TRUE;
        CREATE INDEX IF NOT EXISTS idx_fortune_readings_target_person ON fortune_readings(target_person_id);
        CREATE INDEX IF NOT EXISTS idx_fortune_readings_type ON fortune_readings(reading_type);
        CREATE INDEX IF NOT EXISTS idx_fortune_readings_user_type ON fortune_readings(user_id, reading_type, created_at DESC);

        -- Remove cosmic_influences and lucky_elements columns (no longer used)
        ALTER TABLE fortune_readings DROP COLUMN IF EXISTS cosmic_influences;
        ALTER TABLE fortune_readings DROP COLUMN IF EXISTS lucky_elements;
    """
    )

    # Insert fortune teller app if it doesn't exist
    try:
        await db.execute_schema(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url,
                status, category, is_active, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Fortune Teller',
                'fairydust-fortune-teller',
                'Get personalized mystical guidance and fortune readings based on astrology and numerology',
                NULL,
                'approved',
                'lifestyle',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-fortune-teller'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Fortune Teller app creation failed (may already exist): {e}")

    # User Recipe Preferences table for Recipe app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_recipe_preferences (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            personal_restrictions JSONB DEFAULT '[]',
            custom_restrictions TEXT,
            people_preferences JSONB DEFAULT '[]',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_recipe_preferences_user_id ON user_recipe_preferences(user_id);
    """
    )

    # Enhanced User Recipes table for new Recipe app (update existing table)
    await db.execute_schema(
        """
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS complexity VARCHAR(20);
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS servings INTEGER;
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS prep_time_minutes INTEGER;
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS cook_time_minutes INTEGER;
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS session_id UUID;
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS model_used VARCHAR(100);
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS tokens_used INTEGER;
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS cost_usd DECIMAL(10, 6);
        ALTER TABLE user_recipes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE;

        CREATE INDEX IF NOT EXISTS idx_user_recipes_complexity ON user_recipes(complexity);
        CREATE INDEX IF NOT EXISTS idx_user_recipes_servings ON user_recipes(servings);
        CREATE INDEX IF NOT EXISTS idx_user_recipes_active_new ON user_recipes(user_id, created_at DESC) WHERE deleted_at IS NULL;
    """
    )

    # Insert recipe app if it doesn't exist
    try:
        await db.execute_schema(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url,
                status, category, is_active, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Recipe',
                'fairydust-recipe',
                'Generate personalized recipes based on dietary preferences and group needs',
                NULL,
                'approved',
                'lifestyle',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-recipe'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Recipe app creation failed (may already exist): {e}")

    # App Grants table for tracking initial and streak bonuses
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS app_grants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            app_id UUID NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
            grant_type VARCHAR(20) NOT NULL CHECK (grant_type IN ('initial', 'streak')),
            amount INTEGER NOT NULL CHECK (amount > 0),
            granted_date DATE NOT NULL DEFAULT CURRENT_DATE,
            idempotency_key VARCHAR(128) NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            -- Constraints to prevent duplicate grants
            -- For initial grants: one per user per app (no date constraint)
            -- For streak grants: one per user per app per day
            UNIQUE(user_id, app_id, grant_type, granted_date),
            UNIQUE(idempotency_key)
        );

        CREATE INDEX IF NOT EXISTS idx_app_grants_user_id ON app_grants(user_id);
        CREATE INDEX IF NOT EXISTS idx_app_grants_app_id ON app_grants(app_id);
        CREATE INDEX IF NOT EXISTS idx_app_grants_granted_date ON app_grants(granted_date);
        CREATE INDEX IF NOT EXISTS idx_app_grants_type ON app_grants(grant_type);
        CREATE INDEX IF NOT EXISTS idx_app_grants_user_type_date ON app_grants(user_id, grant_type, granted_date);
    """
    )
    
    # Fix for streak constraint bug - remove old constraint and ensure correct one exists
    try:
        # Drop the problematic constraint that prevents daily streak bonuses
        await db.execute("ALTER TABLE app_grants DROP CONSTRAINT IF EXISTS app_grants_user_id_app_id_grant_type_key")
        logger.info("Dropped old app_grants constraint that prevented daily streak bonuses")
    except Exception as e:
        # Constraint might not exist, which is fine
        logger.debug(f"Old constraint drop (expected if doesn't exist): {e}")
    
    # Ensure the correct constraint exists (CREATE TABLE IF NOT EXISTS above should have created it)
    # but add it if migrating from old schema
    try:
        await db.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conname = 'app_grants_user_id_app_id_grant_type_granted_date_key'
                ) THEN
                    ALTER TABLE app_grants ADD CONSTRAINT app_grants_user_id_app_id_grant_type_granted_date_key 
                        UNIQUE(user_id, app_id, grant_type, granted_date);
                END IF;
            END $$;
        """)
        logger.info("Ensured correct app_grants constraint exists for daily streak bonuses")
    except Exception as e:
        logger.warning(f"Error ensuring constraint (may already exist): {e}")

    # Action-based DUST pricing table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS action_pricing (
            action_slug VARCHAR(50) PRIMARY KEY,
            dust_cost INTEGER NOT NULL CHECK (dust_cost >= 0),
            description TEXT NOT NULL,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_action_pricing_active ON action_pricing(is_active);
    """
    )

    # Note: Action pricing data should be managed through Admin Portal, not seeded here

    # Custom Characters table for Story app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS custom_characters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL,
            description TEXT NOT NULL,
            character_type VARCHAR(20) NOT NULL DEFAULT 'custom',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            -- Unique constraint to prevent duplicate names per user
            UNIQUE(user_id, name)
        );

        CREATE INDEX IF NOT EXISTS idx_custom_characters_user_id ON custom_characters(user_id);
        CREATE INDEX IF NOT EXISTS idx_custom_characters_active ON custom_characters(user_id, is_active);
    """
    )

    # Would You Rather game tables
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS wyr_game_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            game_length INTEGER NOT NULL CHECK (game_length IN (5, 10, 20)),
            category VARCHAR(50) NOT NULL,
            custom_request TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
            current_question INTEGER DEFAULT 1,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE,
            summary TEXT,
            questions JSONB NOT NULL DEFAULT '[]',
            answers JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_wyr_sessions_user_id ON wyr_game_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_wyr_sessions_status ON wyr_game_sessions(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_wyr_sessions_created ON wyr_game_sessions(created_at DESC);
    """
    )

    # Referral System Tables
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS referral_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            referral_code VARCHAR(10) UNIQUE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            is_active BOOLEAN DEFAULT true
        );

        CREATE INDEX IF NOT EXISTS idx_referral_codes_code ON referral_codes(referral_code);
        CREATE INDEX IF NOT EXISTS idx_referral_codes_user ON referral_codes(user_id);
        CREATE INDEX IF NOT EXISTS idx_referral_codes_active ON referral_codes(is_active, expires_at);
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS referral_redemptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            referral_code VARCHAR(10) NOT NULL,
            referrer_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            referee_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            referee_bonus INTEGER NOT NULL,
            referrer_bonus INTEGER NOT NULL,
            milestone_bonus INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_referral_redemptions_referrer ON referral_redemptions(referrer_user_id);
        CREATE INDEX IF NOT EXISTS idx_referral_redemptions_referee ON referral_redemptions(referee_user_id);
        CREATE INDEX IF NOT EXISTS idx_referral_redemptions_code ON referral_redemptions(referral_code);
        CREATE INDEX IF NOT EXISTS idx_referral_redemptions_redeemed ON referral_redemptions(redeemed_at DESC);
    """
    )

    # Promotional Referral Codes table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS promotional_referral_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code VARCHAR(20) UNIQUE NOT NULL,
            description TEXT NOT NULL,
            dust_bonus INTEGER NOT NULL,
            max_uses INTEGER,
            current_uses INTEGER DEFAULT 0,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            is_active BOOLEAN DEFAULT true
        );

        CREATE INDEX IF NOT EXISTS idx_promotional_codes_code ON promotional_referral_codes(code);
        CREATE INDEX IF NOT EXISTS idx_promotional_codes_active ON promotional_referral_codes(is_active, expires_at);
        CREATE INDEX IF NOT EXISTS idx_promotional_codes_usage ON promotional_referral_codes(current_uses, max_uses);
    """
    )

    # Promotional Referral Redemptions table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS promotional_referral_redemptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            promotional_code VARCHAR(20) NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            dust_bonus INTEGER NOT NULL,
            redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(promotional_code, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_promotional_redemptions_code ON promotional_referral_redemptions(promotional_code);
        CREATE INDEX IF NOT EXISTS idx_promotional_redemptions_user ON promotional_referral_redemptions(user_id);
        CREATE INDEX IF NOT EXISTS idx_promotional_redemptions_redeemed ON promotional_referral_redemptions(redeemed_at DESC);
    """
    )

    # Referral System Configuration table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS referral_system_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            referee_bonus INTEGER NOT NULL DEFAULT 15,
            referrer_bonus INTEGER NOT NULL DEFAULT 15,
            milestone_rewards JSONB NOT NULL DEFAULT '[{"referral_count": 5, "bonus_amount": 25}, {"referral_count": 10, "bonus_amount": 50}]'::jsonb,
            code_expiry_days INTEGER NOT NULL DEFAULT 30,
            max_referrals_per_user INTEGER NOT NULL DEFAULT 100,
            system_enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        -- Insert default configuration if none exists
        INSERT INTO referral_system_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
    """
    )

    # Insert fairydust-invite app if it doesn't exist
    try:
        await db.execute_schema(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url,
                status, category, is_active, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Friend Invitations',
                'fairydust-invite',
                'Invite friends to fairydust and earn DUST rewards together',
                NULL,
                'approved',
                'social',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-invite'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Invite app creation failed (may already exist): {e}")

    # System Configuration table for admin-configurable values
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS system_config (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_by UUID REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Insert default daily bonus configuration
        INSERT INTO system_config (key, value, description) 
        VALUES ('daily_login_bonus_amount', '5', 'Amount of DUST granted for daily login bonus')
        ON CONFLICT (key) DO NOTHING;
    """
    )

    # Clean up streak-related columns and constraints safely
    try:
        # Drop old index that references streak_days first
        await db.execute_schema(
            """
            DROP INDEX IF EXISTS idx_users_streak_login;
            """
        )
        logger.info("Dropped old streak login index")
    except Exception as e:
        logger.debug(f"Index cleanup (expected if index doesn't exist): {e}")
    
    try:
        await db.execute_schema(
            """
            -- Remove old streak columns (they may not exist in all environments)
            ALTER TABLE users DROP COLUMN IF EXISTS streak_days;
            ALTER TABLE users DROP COLUMN IF EXISTS timezone;
            """
        )
        logger.info("Removed streak_days and timezone columns from users table")
    except Exception as e:
        logger.debug(f"Column cleanup (expected if columns don't exist): {e}")

    # Clean up app_grants table for daily bonus only (remove streak logic)
    try:
        # First drop the constraint, then update data, then recreate constraint
        await db.execute_schema(
            """
            -- Drop the existing constraint first
            ALTER TABLE app_grants DROP CONSTRAINT IF EXISTS app_grants_grant_type_check;
            """
        )
        logger.info("Dropped existing app_grants constraint")
        
        # Update existing data
        await db.execute_schema(
            """
            UPDATE app_grants SET grant_type = 'daily_bonus' WHERE grant_type = 'streak';
            """
        )
        logger.info("Updated existing streak grants to daily_bonus")
        
        # Add the new constraint with all valid grant types
        await db.execute_schema(
            """
            ALTER TABLE app_grants ADD CONSTRAINT app_grants_grant_type_check 
                CHECK (grant_type IN ('initial', 'referral_bonus', 'referee_bonus', 'milestone_bonus', 'promotional', 'daily_bonus'));
            """
        )
        logger.info("Added updated app_grants constraint for daily bonus system")
    except Exception as e:
        logger.warning(f"App grants cleanup failed: {e}")

    # User Images table for Image app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_images (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            prompt TEXT NOT NULL,
            style VARCHAR(20) NOT NULL CHECK (style IN ('realistic', 'artistic', 'cartoon', 'abstract', 'vintage', 'modern')),
            image_size VARCHAR(10) NOT NULL CHECK (image_size IN ('standard', 'large', 'square')),
            is_favorited BOOLEAN DEFAULT FALSE,
            reference_people JSONB DEFAULT '[]',
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_images_user_id ON user_images(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_images_created_at ON user_images(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_user_images_style ON user_images(style);
        CREATE INDEX IF NOT EXISTS idx_user_images_favorited ON user_images(user_id, is_favorited);
        CREATE INDEX IF NOT EXISTS idx_user_images_has_people ON user_images(user_id) WHERE jsonb_array_length(reference_people) > 0;
    """
    )

    # Insert Image app if it doesn't exist
    try:
        await db.execute_schema(
            """
            INSERT INTO apps (
                id, builder_id, name, slug, description, icon_url,
                status, category, is_active, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Image',
                'fairydust-image',
                'Generate AI images from text prompts with optional reference people',
                NULL,
                'approved',
                'creative',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-image'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Image app creation failed (may already exist): {e}")

    logger.info("Database schema creation/update completed successfully")
