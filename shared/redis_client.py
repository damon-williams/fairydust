# shared/redis_client.py
import os
import redis.asyncio as redis
from typing import Optional

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    
    if REDIS_PASSWORD:
        REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    else:
        REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Global Redis client
_redis_client: Optional[redis.Redis] = None

async def init_redis():
    """Initialize Redis connection"""
    global _redis_client
    
    _redis_client = redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
        health_check_interval=30,
        socket_connect_timeout=5,
        retry_on_timeout=True,
        retry_on_error=[ConnectionError, TimeoutError],
    )
    
    # Test connection
    await _redis_client.ping()

async def close_redis():
    """Close Redis connection"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None

async def get_redis() -> redis.Redis:
    """Dependency to get Redis client"""
    if not _redis_client:
        await init_redis()
    return _redis_client

# Utility functions for common Redis operations
class RedisCache:
    """Utility class for common Redis caching operations"""
    
    def __init__(self, client: redis.Redis, prefix: str = "cache"):
        self.client = client
        self.prefix = prefix
    
    def _key(self, key: str) -> str:
        """Generate namespaced key"""
        return f"{self.prefix}:{key}"
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        return await self.client.get(self._key(key))
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Set value in cache with optional TTL"""
        if ttl:
            await self.client.setex(self._key(key), ttl, value)
        else:
            await self.client.set(self._key(key), value)
    
    async def delete(self, key: str) -> None:
        """Delete value from cache"""
        await self.client.delete(self._key(key))
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        return bool(await self.client.exists(self._key(key)))
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter"""
        return await self.client.incrby(self._key(key), amount)
    
    async def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement a counter"""
        return await self.client.decrby(self._key(key), amount)

# Common cache instances
async def get_user_cache() -> RedisCache:
    """Get user-specific cache instance"""
    client = await get_redis()
    return RedisCache(client, "user")

async def get_balance_cache() -> RedisCache:
    """Get balance-specific cache instance"""
    client = await get_redis()
    return RedisCache(client, "balance")