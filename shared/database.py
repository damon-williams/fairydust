import os
import ssl
import asyncpg
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Build from individual components if DATABASE_URL not provided
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "fairydust")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Connection pool
_pool: Optional[asyncpg.Pool] = None

class Database:
    """Database wrapper for asyncpg with connection pooling"""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def fetch_one(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Fetch a single row"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None
    
    async def fetch_all(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetch multiple rows"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def execute_many(self, query: str, args_list: List[tuple]) -> None:
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
    global _pool
    
    # Configure SSL for production environments
    ssl_context = None
    environment = os.getenv("ENVIRONMENT", "development")
    
    if environment in ["production", "staging"]:
        # Create SSL context for production/staging (Railway requires this)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
    
    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        ssl=ssl_context,  # Add SSL context
        min_size=10,
        max_size=20,
        max_queries=50000,
        max_cached_statement_lifetime=300,
        command_timeout=60,
    )
    
    # Create tables if they don't exist
    await create_tables()

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
    db = await get_db()
    
    # Users table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            fairyname VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE,
            phone VARCHAR(20) UNIQUE,
            avatar_url TEXT,
            is_builder BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            dust_balance INTEGER DEFAULT 0,
            auth_provider VARCHAR(50) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT check_contact CHECK (email IS NOT NULL OR phone IS NOT NULL)
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_fairyname ON users(fairyname);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
    ''')
    
    # User auth providers table (for OAuth)
    await db.execute('''
        CREATE TABLE IF NOT EXISTS user_auth_providers (
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL,
            provider_user_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, provider)
        );
        
        CREATE INDEX IF NOT EXISTS idx_auth_providers_lookup 
        ON user_auth_providers(provider, provider_user_id);
    ''')
    
    # DUST transactions table
    await db.execute('''
        CREATE TABLE IF NOT EXISTS dust_transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL,
            type VARCHAR(50) NOT NULL, -- grant, consume, purchase, refund
            description TEXT,
            app_id UUID,
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_dust_transactions_user 
        ON dust_transactions(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_dust_transactions_app 
        ON dust_transactions(app_id, created_at DESC);
    ''')
    
    # Apps table (for later phases)
    await db.execute('''
        CREATE TABLE IF NOT EXISTS apps (
            id UUID PRIMARY KEY,
            builder_id UUID REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(255) UNIQUE NOT NULL,
            description TEXT,
            icon_url TEXT,
            dust_per_use INTEGER NOT NULL DEFAULT 5,
            is_active BOOLEAN DEFAULT TRUE,
            is_approved BOOLEAN DEFAULT FALSE,
            category VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_apps_builder ON apps(builder_id);
        CREATE INDEX IF NOT EXISTS idx_apps_slug ON apps(slug);
        CREATE INDEX IF NOT EXISTS idx_apps_active_approved 
        ON apps(is_active, is_approved);
    ''')