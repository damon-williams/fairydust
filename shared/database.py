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
            age_range VARCHAR(20),
            city VARCHAR(100),
            country VARCHAR(100) DEFAULT 'US',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT check_contact CHECK (email IS NOT NULL OR phone IS NOT NULL)
        );

        CREATE INDEX IF NOT EXISTS idx_users_fairyname ON users(fairyname);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
        CREATE INDEX IF NOT EXISTS idx_users_streak_login ON users(id, last_login_date, streak_days);
    """
    )

    # Add new profile columns to existing users table
    await db.execute_schema(
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(100);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS age_range VARCHAR(20);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(100);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS country VARCHAR(100) DEFAULT 'US';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_profiling_session TIMESTAMP;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_profiling_sessions INTEGER DEFAULT 0;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_days INTEGER DEFAULT 0;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_date TIMESTAMP WITH TIME ZONE;
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
            dust_per_use INTEGER NOT NULL DEFAULT 5,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            category VARCHAR(100) NOT NULL,
            website_url TEXT,
            demo_url TEXT,
            callback_url TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            admin_notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_apps_builder ON apps(builder_id);
        CREATE INDEX IF NOT EXISTS idx_apps_slug ON apps(slug);
        CREATE INDEX IF NOT EXISTS idx_apps_status ON apps(status);
        CREATE INDEX IF NOT EXISTS idx_apps_category ON apps(category);
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
        CREATE TABLE IF NOT EXISTS profiling_questions (
            id VARCHAR(100) PRIMARY KEY,
            category VARCHAR(50) NOT NULL,
            question_text TEXT NOT NULL,
            question_type VARCHAR(50) NOT NULL,
            profile_field VARCHAR(100) NOT NULL,
            priority INTEGER NOT NULL DEFAULT 5,
            app_context JSONB,
            min_app_uses INTEGER DEFAULT 0,
            options JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        );

        CREATE INDEX IF NOT EXISTS idx_profiling_questions_category ON profiling_questions(category);
        CREATE INDEX IF NOT EXISTS idx_profiling_questions_priority ON profiling_questions(priority);
    """
    )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_question_responses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question_id VARCHAR(100) NOT NULL REFERENCES profiling_questions(id),
            response_value JSONB NOT NULL,
            session_id VARCHAR(100),
            dust_reward INTEGER DEFAULT 0,
            answered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, question_id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_question_responses_user_id ON user_question_responses(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_question_responses_session ON user_question_responses(session_id);
        CREATE INDEX IF NOT EXISTS idx_user_question_responses_question_id ON user_question_responses(question_id);
    """
    )

    # Insert default profiling questions (with smaller batches to avoid timeout)
    questions = [
        (
            "interests_hobbies",
            "interests",
            "What activities do you enjoy in your free time?",
            "multi_select",
            "interests",
            10,
            '["fairydust-inspire"]',
            '[{"id": "cooking", "label": "Cooking"}, {"id": "fitness", "label": "Fitness"}, {"id": "music", "label": "Music"}, {"id": "reading", "label": "Reading"}, {"id": "gaming", "label": "Gaming"}, {"id": "art", "label": "Art & Crafts"}, {"id": "outdoor", "label": "Outdoor Activities"}, {"id": "travel", "label": "Travel"}]',
            True,
        ),
        (
            "adventure_level",
            "personality",
            "How adventurous are you?",
            "scale",
            "adventure_level",
            8,
            '["fairydust-inspire"]',
            '{"min": 1, "max": 5, "labels": {"1": "Prefer familiar", "3": "Sometimes try new things", "5": "Always seeking adventure"}}',
            True,
        ),
        (
            "creativity_level",
            "personality",
            "How creative would you say you are?",
            "scale",
            "creativity_level",
            7,
            '["fairydust-inspire", "fairydust-recipe"]',
            '{"min": 1, "max": 5, "labels": {"1": "Practical", "3": "Somewhat creative", "5": "Very creative"}}',
            True,
        ),
        (
            "dietary_preferences",
            "cooking",
            "Do you follow any specific dietary preferences?",
            "multi_select",
            "dietary_preferences",
            9,
            '["fairydust-recipe"]',
            '[{"id": "none", "label": "No restrictions"}, {"id": "vegetarian", "label": "Vegetarian"}, {"id": "vegan", "label": "Vegan"}, {"id": "gluten_free", "label": "Gluten-free"}, {"id": "dairy_free", "label": "Dairy-free"}, {"id": "keto", "label": "Keto"}, {"id": "paleo", "label": "Paleo"}, {"id": "low_carb", "label": "Low-carb"}]',
            True,
        ),
        (
            "cooking_skill_level",
            "cooking",
            "How would you describe your cooking skills?",
            "single_choice",
            "cooking_skill_level",
            6,
            '["fairydust-recipe"]',
            '[{"id": "beginner", "label": "Beginner"}, {"id": "intermediate", "label": "Intermediate"}, {"id": "advanced", "label": "Advanced"}, {"id": "expert", "label": "Expert"}]',
            True,
        ),
        (
            "lifestyle_goals",
            "goals",
            "What are your main lifestyle goals?",
            "multi_select",
            "lifestyle_goals",
            8,
            '["fairydust-inspire"]',
            '[{"id": "health", "label": "Health & Wellness"}, {"id": "relationships", "label": "Relationships"}, {"id": "career", "label": "Career Growth"}, {"id": "learning", "label": "Learning & Growth"}, {"id": "creativity", "label": "Creative Expression"}, {"id": "adventure", "label": "Adventure & Travel"}, {"id": "family", "label": "Family Time"}, {"id": "relaxation", "label": "Rest & Relaxation"}]',
            True,
        ),
        (
            "social_preference",
            "personality",
            "What size groups do you prefer for activities?",
            "single_choice",
            "social_preference",
            5,
            '["fairydust-inspire"]',
            '[{"id": "solo", "label": "Solo activities"}, {"id": "small_group", "label": "Small groups (2-4 people)"}, {"id": "large_group", "label": "Large groups (5+ people)"}, {"id": "varies", "label": "Depends on the activity"}]',
            True,
        ),
        (
            "cooking_skill",
            "cooking",
            "How would you describe your cooking skills?",
            "single_choice",
            "cooking_skill",
            6,
            '["fairydust-recipe"]',
            '[{"id": "beginner", "label": "Beginner"}, {"id": "intermediate", "label": "Intermediate"}, {"id": "advanced", "label": "Advanced"}, {"id": "expert", "label": "Expert"}]',
            True,
        ),
    ]

    # Insert questions individually to avoid timeout
    for question in questions:
        await db.execute_schema(
            """
            INSERT INTO profiling_questions (id, category, question_text, question_type, profile_field, priority, app_context, options, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9)
            ON CONFLICT (id) DO UPDATE SET
                question_text = EXCLUDED.question_text,
                question_type = EXCLUDED.question_type,
                profile_field = EXCLUDED.profile_field,
                priority = EXCLUDED.priority,
                app_context = EXCLUDED.app_context,
                options = EXCLUDED.options,
                is_active = EXCLUDED.is_active
        """,
            *question,
        )

    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS people_in_my_life (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            age_range VARCHAR(50),
            relationship VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_people_in_my_life_user_id ON people_in_my_life(user_id);
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
                ELSE 'anthropic'
            END,
            CASE
                WHEN a.slug = 'fairydust-inspire' THEN 'claude-3-5-haiku-20241022'
                WHEN a.slug = 'fairydust-recipe' THEN 'claude-3-5-sonnet-20241022'
                ELSE 'claude-3-5-haiku-20241022'
            END,
            CASE
                WHEN a.slug = 'fairydust-inspire' THEN '{"temperature": 0.8, "max_tokens": 150, "top_p": 0.9}'::jsonb
                WHEN a.slug = 'fairydust-recipe' THEN '{"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}'::jsonb
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
                ELSE '[]'::jsonb
            END,
            CASE
                WHEN a.slug = 'fairydust-inspire' THEN '{"per_request_max": 0.05, "daily_max": 10.0, "monthly_max": 100.0}'::jsonb
                WHEN a.slug = 'fairydust-recipe' THEN '{"per_request_max": 0.15, "daily_max": 25.0, "monthly_max": 200.0}'::jsonb
                ELSE '{"per_request_max": 0.05, "daily_max": 10.0, "monthly_max": 100.0}'::jsonb
            END,
            '{"streaming_enabled": true, "cache_responses": true, "log_prompts": false}'::jsonb
        FROM apps a
        WHERE a.slug IN ('fairydust-inspire', 'fairydust-recipe')
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

    # User Stories table for story app
    await db.execute_schema(
        """
        CREATE TABLE IF NOT EXISTS user_stories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            genre VARCHAR(50) NOT NULL,
            story_length VARCHAR(20) NOT NULL,
            characters_involved JSONB DEFAULT '[]',
            metadata JSONB DEFAULT '{}',
            is_favorited BOOLEAN DEFAULT FALSE,
            dust_cost INTEGER NOT NULL,
            word_count INTEGER,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_stories_user_id ON user_stories(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_stories_created_at ON user_stories(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_user_stories_genre ON user_stories(genre);
        CREATE INDEX IF NOT EXISTS idx_user_stories_favorited ON user_stories(user_id, is_favorited) WHERE is_favorited = TRUE;
    """
    )

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
                id, builder_id, name, slug, description, icon_url, dust_per_use,
                status, category, website_url, demo_url, callback_url,
                is_active, admin_notes, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Restaurant',
                'fairydust-restaurant',
                'Find restaurants based on your group''s preferences',
                NULL,
                3,
                'approved',
                'lifestyle',
                NULL,
                NULL,
                NULL,
                true,
                'Auto-created for mobile app implementation',
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
                id, builder_id, name, slug, description, icon_url, dust_per_use,
                status, category, website_url, demo_url, callback_url,
                is_active, admin_notes, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Activity',
                'fairydust-activity',
                'Discover personalized activities and attractions based on your location and preferences',
                NULL,
                3,
                'approved',
                'lifestyle',
                NULL,
                NULL,
                NULL,
                true,
                'Auto-created for mobile app implementation',
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
                id, builder_id, name, slug, description, icon_url, dust_per_use,
                status, category, website_url, demo_url, callback_url,
                is_active, admin_notes, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Inspire',
                'fairydust-inspire',
                'Get personalized inspirations and challenges for daily motivation',
                NULL,
                2,
                'approved',
                'lifestyle',
                NULL,
                NULL,
                NULL,
                true,
                'Auto-created for mobile app implementation',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-inspire'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Inspire app creation failed (may already exist): {e}")

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
                id, builder_id, name, slug, description, icon_url, dust_per_use,
                status, category, website_url, demo_url, callback_url,
                is_active, admin_notes, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                (SELECT id FROM users WHERE is_builder = true LIMIT 1),
                'Recipe',
                'fairydust-recipe',
                'Generate personalized recipes based on dietary preferences and group needs',
                NULL,
                3,
                'approved',
                'lifestyle',
                NULL,
                NULL,
                NULL,
                true,
                'Auto-created for mobile app implementation',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM apps WHERE slug = 'fairydust-recipe'
            );
        """
        )
    except Exception as e:
        logger.warning(f"Recipe app creation failed (may already exist): {e}")

    logger.info("Database schema creation/update completed successfully")
