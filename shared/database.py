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
        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_logins INTEGER DEFAULT 0;
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
            id UUID PRIMARY KEY,
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

    # Add Apple Receipt Verification Fields to existing dust_transactions table
    await db.execute_schema(
        """
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS payment_id VARCHAR(255);
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS receipt_data TEXT;
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS receipt_verification_status VARCHAR(50);
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS receipt_verification_response JSONB;
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS apple_transaction_id VARCHAR(255);
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS apple_original_transaction_id VARCHAR(255);
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS apple_product_id VARCHAR(100);
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS apple_purchase_date_ms BIGINT;
        ALTER TABLE dust_transactions ADD COLUMN IF NOT EXISTS payment_amount_cents INTEGER;

        CREATE INDEX IF NOT EXISTS idx_dust_transactions_apple_txn
        ON dust_transactions(apple_transaction_id);
        CREATE INDEX IF NOT EXISTS idx_dust_transactions_payment_id
        ON dust_transactions(payment_id);
    """
    )

    # Apps table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS apps (
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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

        -- Add personality description column for Story app character enhancement
        ALTER TABLE people_in_my_life ADD COLUMN IF NOT EXISTS personality_description TEXT;

        -- Drop old age_range column from people_in_my_life (replaced with birth_date)
        ALTER TABLE people_in_my_life DROP COLUMN IF EXISTS age_range;

        -- Pet support extensions
        -- Add entry_type to distinguish between people and pets
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'entry_type_enum') THEN
                CREATE TYPE entry_type_enum AS ENUM ('person', 'pet');
            END IF;
        END $$;

        ALTER TABLE people_in_my_life ADD COLUMN IF NOT EXISTS entry_type entry_type_enum NOT NULL DEFAULT 'person';

        -- Add species field for pets (breed, animal type, etc.)
        ALTER TABLE people_in_my_life ADD COLUMN IF NOT EXISTS species VARCHAR(50);

        -- Add composite index for efficient filtering by user and type
        CREATE INDEX IF NOT EXISTS idx_people_in_my_life_user_type ON people_in_my_life(user_id, entry_type);
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
            id UUID PRIMARY KEY,
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

    # LLM Architecture Tables - Migration to normalized structure
    logger.info("Creating/migrating app_model_configs table to normalized structure...")

    # Check if table exists and has old structure (no model_type column)
    table_info = await db.fetch_one(
        """
        SELECT COUNT(*) as count
        FROM information_schema.columns
        WHERE table_name = 'app_model_configs'
        AND column_name = 'model_type'
    """
    )

    has_new_structure = table_info and table_info["count"] > 0

    if not has_new_structure:
        logger.info("Migrating app_model_configs to normalized structure...")

        # Backup existing data if the old table exists
        old_data = []
        try:
            old_data = await db.fetch_all(
                """
                SELECT app_id, text_config, image_config, video_config, created_at, updated_at
                FROM app_model_configs
                WHERE text_config IS NOT NULL OR image_config IS NOT NULL OR video_config IS NOT NULL
            """
            )
            logger.info(f"Backing up {len(old_data)} existing model configurations")
        except Exception as e:
            logger.info(f"No existing data to backup: {e}")

        # Drop old table and recreate with new structure
        await db.execute_schema("DROP TABLE IF EXISTS app_model_configs CASCADE")
        logger.info("Dropped old app_model_configs table structure")

        # Create new normalized table
        await db.execute_schema(
            """
            CREATE TABLE app_model_configs (
                id UUID PRIMARY KEY,
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
            CREATE INDEX idx_app_model_configs_app_id ON app_model_configs(app_id);
            CREATE INDEX idx_app_model_configs_model_type ON app_model_configs(model_type);
        """
        )
        logger.info("Created new normalized app_model_configs table")

        # Migrate old data to new structure
        if old_data:
            logger.info(f"Migrating {len(old_data)} configurations to normalized structure...")
            for row in old_data:
                app_id = row["app_id"]

                # Migrate text config
                if row.get("text_config"):
                    text_config = row["text_config"]
                    await db.execute(
                        """
                        INSERT INTO app_model_configs (app_id, model_type, provider, model_id, parameters, is_enabled, created_at)
                        VALUES ($1, 'text', $2, $3, $4, true, $5)
                    """,
                        app_id,
                        text_config.get("primary_provider", "anthropic"),
                        text_config.get("primary_model_id", "claude-3-5-haiku-20241022"),
                        text_config.get("parameters", {}),
                        row.get("created_at"),
                    )

                # Migrate image config
                if row.get("image_config"):
                    image_config = row["image_config"]
                    await db.execute(
                        """
                        INSERT INTO app_model_configs (app_id, model_type, provider, model_id, parameters, is_enabled, created_at)
                        VALUES ($1, 'image', $2, $3, $4, true, $5)
                    """,
                        app_id,
                        image_config.get("primary_provider", "replicate"),
                        image_config.get("primary_model_id", "black-forest-labs/flux-schnell"),
                        image_config.get("parameters", {}),
                        row.get("created_at"),
                    )

                # Migrate video config
                if row.get("video_config"):
                    video_config = row["video_config"]
                    await db.execute(
                        """
                        INSERT INTO app_model_configs (app_id, model_type, provider, model_id, parameters, is_enabled, created_at)
                        VALUES ($1, 'video', $2, $3, $4, true, $5)
                    """,
                        app_id,
                        video_config.get("primary_provider", "runwayml"),
                        video_config.get("primary_model_id", "gen4-video"),
                        video_config.get("parameters", {}),
                        row.get("created_at"),
                    )
            logger.info("Migration of existing data completed")
    else:
        # Table already has new structure, just ensure it exists
        await db.execute_schema(
            """
            CREATE TABLE IF NOT EXISTS app_model_configs (
                id UUID PRIMARY KEY,
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
            CREATE INDEX IF NOT EXISTS idx_app_model_configs_app_id ON app_model_configs(app_id);
            CREATE INDEX IF NOT EXISTS idx_app_model_configs_model_type ON app_model_configs(model_type);
        """
        )
        logger.info("Verified normalized app_model_configs table structure")

    # Global fallback models table
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS global_fallback_models (
            id UUID PRIMARY KEY,
            model_type VARCHAR(20) NOT NULL CHECK (model_type IN ('text', 'image', 'video')),
            provider VARCHAR(50) NOT NULL,
            model_id VARCHAR(200) NOT NULL,
            parameters JSONB DEFAULT '{}',
            is_enabled BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(model_type)
        );

        CREATE INDEX IF NOT EXISTS idx_global_fallback_models_type ON global_fallback_models(model_type);

        -- Migrate existing global_fallback_models table to simplified structure
        -- Drop old columns that are no longer needed
        ALTER TABLE global_fallback_models DROP COLUMN IF EXISTS primary_provider;
        ALTER TABLE global_fallback_models DROP COLUMN IF EXISTS primary_model_id;
        ALTER TABLE global_fallback_models DROP COLUMN IF EXISTS fallback_provider;
        ALTER TABLE global_fallback_models DROP COLUMN IF EXISTS fallback_model_id;
        ALTER TABLE global_fallback_models DROP COLUMN IF EXISTS trigger_condition;
        ALTER TABLE global_fallback_models DROP COLUMN IF EXISTS priority;

        -- Add new simplified columns
        ALTER TABLE global_fallback_models ADD COLUMN IF NOT EXISTS provider VARCHAR(50);
        ALTER TABLE global_fallback_models ADD COLUMN IF NOT EXISTS model_id VARCHAR(200);

        -- Update any NULL values in new columns (shouldn't happen with new structure, but just in case)
        UPDATE global_fallback_models SET provider = 'anthropic' WHERE provider IS NULL AND model_type = 'text';
        UPDATE global_fallback_models SET model_id = 'claude-3-5-haiku-20241022' WHERE model_id IS NULL AND model_type = 'text';
        UPDATE global_fallback_models SET provider = 'replicate' WHERE provider IS NULL AND model_type = 'image';
        UPDATE global_fallback_models SET model_id = 'black-forest-labs/flux-schnell' WHERE model_id IS NULL AND model_type = 'image';
        UPDATE global_fallback_models SET provider = 'runwayml' WHERE provider IS NULL AND model_type = 'video';
        UPDATE global_fallback_models SET model_id = 'runwayml/gen4-video' WHERE model_id IS NULL AND model_type = 'video';

        -- Make the columns NOT NULL after setting defaults
        ALTER TABLE global_fallback_models ALTER COLUMN provider SET NOT NULL;
        ALTER TABLE global_fallback_models ALTER COLUMN model_id SET NOT NULL;
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS llm_usage_logs (
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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

    # Insert default model configurations for existing apps (normalized structure)
    await db.execute_schema(
        """
        -- Insert text model configurations for existing apps
        INSERT INTO app_model_configs (app_id, model_type, provider, model_id, parameters, is_enabled)
        SELECT
            a.id,
            'text',
            'anthropic',
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
            true
        FROM apps a
        WHERE a.slug IN ('fairydust-inspire', 'fairydust-recipe', 'fairydust-fortune-teller')
        ON CONFLICT (app_id, model_type) DO NOTHING;

        -- Insert image model configurations for Story app (has image generation)
        INSERT INTO app_model_configs (app_id, model_type, provider, model_id, parameters, is_enabled)
        SELECT
            a.id,
            'image',
            'replicate',
            'black-forest-labs/flux-1.1-pro',
            '{"standard_model": "black-forest-labs/flux-1.1-pro", "reference_model": "runwayml/gen4-image"}'::jsonb,
            true
        FROM apps a
        WHERE a.slug = 'fairydust-story'
        ON CONFLICT (app_id, model_type) DO NOTHING;
    """
    )

    # Insert default global fallback models
    await db.execute_schema(
        """
        INSERT INTO global_fallback_models (
            model_type, provider, model_id, parameters
        ) VALUES
        -- Text model fallback
        ('text', 'anthropic', 'claude-3-5-haiku-20241022', '{"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}'::jsonb),
        -- Image model fallback
        ('image', 'replicate', 'black-forest-labs/flux-schnell', '{"guidance_scale": 2.5}'::jsonb),
        -- Video model fallback (future)
        ('video', 'runwayml', 'runwayml/gen4-video', '{"duration": 5, "fps": 24, "resolution": "1080p"}'::jsonb)
        ON CONFLICT (model_type) DO NOTHING;
    """
    )

    # User Recipes table for app-specific content storage
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_recipes (
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(500) NOT NULL,
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

    # Add image support columns to user_stories table
    await db.execute_schema(
        """
        ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS has_images BOOLEAN DEFAULT FALSE;
        ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS images_complete BOOLEAN DEFAULT FALSE;
        ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS image_data JSONB DEFAULT '{}';
        """
    )

    # Add story_summary column for theme variety tracking
    await db.execute_schema(
        """
        ALTER TABLE user_stories ADD COLUMN IF NOT EXISTS story_summary TEXT;
        """
    )

    # Increase title length from 255 to 500 characters to match model definition
    await db.execute_schema(
        """
        ALTER TABLE user_stories ALTER COLUMN title TYPE VARCHAR(500);
        """
    )

    # Create index for target_audience after column is added
    await db.execute_schema(
        """
        CREATE INDEX IF NOT EXISTS idx_user_stories_target_audience ON user_stories(target_audience);
        """
    )

    # Story images table for tracking individual image generation
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS story_images (
            id UUID PRIMARY KEY,
            story_id UUID NOT NULL REFERENCES user_stories(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            image_id VARCHAR(50) NOT NULL,
            url TEXT,
            prompt TEXT NOT NULL,
            scene_description TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            generation_metadata JSONB DEFAULT '{}',
            attempt_number INTEGER DEFAULT 1,
            max_attempts INTEGER DEFAULT 3,
            retry_reason TEXT DEFAULT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(story_id, image_id)
        );

        CREATE INDEX IF NOT EXISTS idx_story_images_story_id ON story_images(story_id);
        CREATE INDEX IF NOT EXISTS idx_story_images_user_id ON story_images(user_id);
        CREATE INDEX IF NOT EXISTS idx_story_images_status ON story_images(status);
        CREATE INDEX IF NOT EXISTS idx_story_images_created_at ON story_images(created_at DESC);
    """
    )

    # Add retry metadata columns to existing story_images tables (safe migrations)
    # Handle each column separately to avoid syntax issues
    try:
        await db.execute_schema(
            "ALTER TABLE story_images ADD COLUMN IF NOT EXISTS attempt_number INTEGER DEFAULT 1"
        )
    except Exception as e:
        if "already exists" not in str(e):
            logger.warning(f"Could not add attempt_number column: {e}")

    try:
        await db.execute_schema(
            "ALTER TABLE story_images ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 3"
        )
    except Exception as e:
        if "already exists" not in str(e):
            logger.warning(f"Could not add max_attempts column: {e}")

    try:
        await db.execute_schema(
            "ALTER TABLE story_images ADD COLUMN IF NOT EXISTS retry_reason TEXT DEFAULT NULL"
        )
    except Exception as e:
        if "already exists" not in str(e):
            logger.warning(f"Could not add retry_reason column: {e}")

    # Add index for retry columns after they exist
    try:
        await db.execute_schema(
            "CREATE INDEX IF NOT EXISTS idx_story_images_status_attempts ON story_images(status, attempt_number) WHERE status IN ('generating', 'retrying', 'failed')"
        )
    except Exception as e:
        logger.warning(f"Could not create retry status index: {e}")

    # User Inspirations table for Inspire app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_inspirations (
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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

        -- Add image support columns for custom characters
        ALTER TABLE custom_characters ADD COLUMN IF NOT EXISTS image_url TEXT;
        ALTER TABLE custom_characters ADD COLUMN IF NOT EXISTS image_uploaded_at TIMESTAMP WITH TIME ZONE;
        ALTER TABLE custom_characters ADD COLUMN IF NOT EXISTS image_size_bytes INTEGER;
    """
    )

    # Would You Rather game tables
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS wyr_game_sessions (
            id UUID PRIMARY KEY,
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

    # User question history table for Would You Rather duplicate prevention
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_question_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            question_hash TEXT NOT NULL,
            question_content JSONB NOT NULL,
            game_session_id UUID REFERENCES wyr_game_sessions(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_question_hash ON user_question_history(user_id, question_hash);
        CREATE INDEX IF NOT EXISTS idx_user_question_created ON user_question_history(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_question_history_session ON user_question_history(game_session_id);
    """
    )

    # Referral System Tables
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS referral_codes (
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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
            id UUID PRIMARY KEY,
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

        -- Insert default initial dust amount configuration
        INSERT INTO system_config (key, value, description)
        VALUES ('initial_dust_amount', '100', 'Initial DUST amount granted to new users upon registration')
        ON CONFLICT (key) DO NOTHING;
    """
    )

    # Account Deletion Logs table for audit trail and compliance
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS account_deletion_logs (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL,
            fairyname VARCHAR(255),
            email VARCHAR(255),
            deletion_reason VARCHAR(50),
            deletion_feedback TEXT,
            deleted_by VARCHAR(50) NOT NULL DEFAULT 'self',
            deleted_by_user_id UUID,
            user_created_at TIMESTAMP WITH TIME ZONE,
            deletion_requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deletion_completed_at TIMESTAMP WITH TIME ZONE,
            data_summary JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT deletion_reason_check CHECK (deletion_reason IN (
                'not_using_anymore', 'privacy_concerns', 'too_expensive',
                'switching_platform', 'other'
            )),
            CONSTRAINT deleted_by_check CHECK (deleted_by IN ('self', 'admin'))
        );

        CREATE INDEX IF NOT EXISTS idx_account_deletion_logs_user_id ON account_deletion_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_account_deletion_logs_deletion_requested_at ON account_deletion_logs(deletion_requested_at DESC);
        CREATE INDEX IF NOT EXISTS idx_account_deletion_logs_deleted_by ON account_deletion_logs(deleted_by);
        CREATE INDEX IF NOT EXISTS idx_account_deletion_logs_reason ON account_deletion_logs(deletion_reason);
    """
    )

    # User Images table for Image app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_images (
            id UUID PRIMARY KEY,
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

    # User Videos table for Video app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_videos (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            thumbnail_url TEXT,
            prompt TEXT NOT NULL,
            generation_type VARCHAR(20) NOT NULL CHECK (generation_type IN ('text_to_video', 'image_to_video')),
            source_image_url TEXT, -- For image-to-video generation
            duration_seconds INTEGER NOT NULL CHECK (duration_seconds > 0),
            resolution VARCHAR(10) NOT NULL CHECK (resolution IN ('sd_480p', 'hd_1080p')),
            aspect_ratio VARCHAR(10) NOT NULL CHECK (aspect_ratio IN ('16:9', '4:3', '1:1', '3:4', '9:16', '21:9', '9:21')),
            reference_person JSONB, -- Single reference person (MiniMax Video-01 limitation)
            metadata JSONB DEFAULT '{}',
            is_favorited BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_videos_user_id ON user_videos(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_videos_created_at ON user_videos(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_user_videos_generation_type ON user_videos(generation_type);
        CREATE INDEX IF NOT EXISTS idx_user_videos_favorited ON user_videos(user_id, is_favorited);
        CREATE INDEX IF NOT EXISTS idx_user_videos_has_reference ON user_videos(user_id) WHERE reference_person IS NOT NULL;
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

    # Terms & Conditions system tables
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS terms_documents (
            id UUID PRIMARY KEY,
            document_type VARCHAR(50) NOT NULL CHECK (document_type IN ('terms_of_service', 'privacy_policy')),
            version VARCHAR(20) NOT NULL,
            title VARCHAR(200) NOT NULL,
            content_url TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            is_active BOOLEAN DEFAULT false,
            requires_acceptance BOOLEAN DEFAULT true,
            effective_date TIMESTAMP WITH TIME ZONE NOT NULL,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(document_type, version)
        );

        CREATE INDEX IF NOT EXISTS idx_terms_documents_active ON terms_documents(document_type, is_active);
        CREATE INDEX IF NOT EXISTS idx_terms_documents_effective ON terms_documents(effective_date);
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_terms_acceptance (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES terms_documents(id) ON DELETE CASCADE,
            document_type VARCHAR(50) NOT NULL,
            document_version VARCHAR(20) NOT NULL,
            accepted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            ip_address INET,
            user_agent TEXT,
            acceptance_method VARCHAR(50) DEFAULT 'app_signup' CHECK (acceptance_method IN ('app_signup', 'forced_update', 'voluntary')),

            UNIQUE(user_id, document_id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_terms_acceptance_user_type ON user_terms_acceptance(user_id, document_type);
        CREATE INDEX IF NOT EXISTS idx_user_terms_acceptance_accepted_at ON user_terms_acceptance(accepted_at);
    """
    )

    # AI Usage Logs table for unified tracking of text, image, and video models
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id UUID PRIMARY KEY,
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
            prompt_text TEXT, -- Full prompt text for debugging/analysis
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

        -- Add missing prompt_text column for existing deployments
        ALTER TABLE ai_usage_logs ADD COLUMN IF NOT EXISTS prompt_text TEXT;
    """
    )

    # Create a view that unions old LLM logs with new AI logs for backward compatibility
    await db.execute_schema(
        """
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
    """
    )

    # Video Generation Jobs table for async video processing
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS video_generation_jobs (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            generation_type VARCHAR(20) NOT NULL, -- 'text_to_video' | 'image_to_video'

            -- Input parameters (stored as JSONB for flexibility)
            input_parameters JSONB NOT NULL,

            -- Progress tracking
            replicate_prediction_id VARCHAR(100),
            replicate_status VARCHAR(20), -- 'starting' | 'processing' | 'succeeded' | 'failed'
            estimated_completion_seconds INT DEFAULT 180,

            -- Results
            video_id UUID, -- FK to user_videos table when completed
            video_url TEXT,
            thumbnail_url TEXT,
            generation_metadata JSONB,

            -- Error handling
            error_code VARCHAR(50),
            error_message TEXT,
            error_details JSONB,

            -- Timestamps
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP,

            -- Constraints
            CONSTRAINT valid_status CHECK (status IN ('queued', 'starting', 'processing', 'completed', 'failed', 'cancelled')),
            CONSTRAINT valid_generation_type CHECK (generation_type IN ('text_to_video', 'image_to_video'))
        );

        -- Indexes for efficient queries
        CREATE INDEX IF NOT EXISTS idx_video_jobs_user_id ON video_generation_jobs(user_id);
        CREATE INDEX IF NOT EXISTS idx_video_jobs_status ON video_generation_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_video_jobs_created_at ON video_generation_jobs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_video_jobs_replicate_id ON video_generation_jobs(replicate_prediction_id);
        CREATE INDEX IF NOT EXISTS idx_video_jobs_user_status ON video_generation_jobs(user_id, status);

        -- Function to automatically update updated_at timestamp (only create if not exists)
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'update_updated_at_column') THEN
                CREATE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $trigger$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $trigger$ language 'plpgsql';
            END IF;
        END $$;

        -- Trigger to auto-update updated_at (only create if not exists)
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_video_jobs_updated_at') THEN
                CREATE TRIGGER update_video_jobs_updated_at
                    BEFORE UPDATE ON video_generation_jobs
                    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
            END IF;
        END $$;
    """
    )

    # 20 Questions Game Tables
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS twenty_questions_games (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category VARCHAR(50) NOT NULL,
            mode VARCHAR(20) NOT NULL DEFAULT 'user_thinks' CHECK (mode IN ('user_thinks', 'fairydust_thinks')),
            target_person_id UUID REFERENCES people_in_my_life(id) ON DELETE CASCADE,
            target_person_name VARCHAR(100) NOT NULL,
            secret_answer VARCHAR(100), -- For fairydust_thinks mode
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'won', 'lost', 'abandoned')),
            questions_asked INTEGER DEFAULT 0,
            questions_remaining INTEGER DEFAULT 20,
            current_ai_question TEXT,
            final_guess TEXT,
            answer_revealed TEXT,
            is_correct BOOLEAN,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        -- Add new columns if they don't exist
        ALTER TABLE twenty_questions_games ADD COLUMN IF NOT EXISTS current_ai_question TEXT;
        ALTER TABLE twenty_questions_games ADD COLUMN IF NOT EXISTS mode VARCHAR(20) DEFAULT 'user_thinks' CHECK (mode IN ('user_thinks', 'fairydust_thinks'));
        ALTER TABLE twenty_questions_games ADD COLUMN IF NOT EXISTS secret_answer VARCHAR(100);

        -- Update status constraint to include 'abandoned'
        DO $$
        BEGIN
            ALTER TABLE twenty_questions_games DROP CONSTRAINT IF EXISTS twenty_questions_games_status_check;
            ALTER TABLE twenty_questions_games ADD CONSTRAINT twenty_questions_games_status_check
                CHECK (status IN ('active', 'won', 'lost', 'abandoned'));
        EXCEPTION
            WHEN others THEN null;
        END $$;

        CREATE INDEX IF NOT EXISTS idx_twenty_questions_games_user_id ON twenty_questions_games(user_id);
        CREATE INDEX IF NOT EXISTS idx_twenty_questions_games_status ON twenty_questions_games(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_twenty_questions_games_created_at ON twenty_questions_games(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_twenty_questions_games_target_person ON twenty_questions_games(target_person_id);
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS twenty_questions_history (
            id UUID PRIMARY KEY,
            game_id UUID NOT NULL REFERENCES twenty_questions_games(id) ON DELETE CASCADE,
            question_number INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            answer TEXT NOT NULL CHECK (answer IN ('yes', 'no', 'sometimes', 'unknown', 'correct', 'incorrect', 'pending')),
            is_guess BOOLEAN DEFAULT FALSE,
            asked_by VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (asked_by IN ('user', 'ai')),
            mode VARCHAR(20), -- Track which mode this question was asked in
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        -- Add mode column to history if it doesn't exist
        ALTER TABLE twenty_questions_history ADD COLUMN IF NOT EXISTS mode VARCHAR(20);

        -- Add asked_by column if it doesn't exist
        ALTER TABLE twenty_questions_history ADD COLUMN IF NOT EXISTS asked_by VARCHAR(10) DEFAULT 'user';

        -- Update answer constraint to include 'pending' for AI questions
        DO $$
        BEGIN
            ALTER TABLE twenty_questions_history DROP CONSTRAINT IF EXISTS twenty_questions_history_answer_check;
            ALTER TABLE twenty_questions_history ADD CONSTRAINT twenty_questions_history_answer_check
                CHECK (answer IN ('yes', 'no', 'sometimes', 'unknown', 'correct', 'incorrect', 'pending'));
        EXCEPTION
            WHEN others THEN null;
        END $$;

        -- Update asked_by constraint to allow both 'user' and 'ai'
        DO $$
        BEGIN
            ALTER TABLE twenty_questions_history DROP CONSTRAINT IF EXISTS twenty_questions_history_asked_by_check;
            ALTER TABLE twenty_questions_history ADD CONSTRAINT twenty_questions_history_asked_by_check
                CHECK (asked_by IN ('user', 'ai'));
        EXCEPTION
            WHEN others THEN null;
        END $$;

        CREATE INDEX IF NOT EXISTS idx_twenty_questions_history_game_id ON twenty_questions_history(game_id, question_number);
        CREATE INDEX IF NOT EXISTS idx_twenty_questions_history_created_at ON twenty_questions_history(created_at DESC);
    """
    )

    # Insert 20 Questions app if it doesn't exist
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
                '20 Questions',
                'fairydust-20-questions',
                'Collaborative guessing game where AI thinks of someone in your life and you ask questions to figure out who',
                NULL,
                'approved',
                'games',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-20-questions'
            );
        """
        )
    except Exception as e:
        logger.warning(f"20 Questions app creation failed (may already exist): {e}")

    logger.info("Database schema creation/update completed successfully")
