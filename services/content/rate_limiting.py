# services/content/rate_limiting.py
import time
from uuid import UUID

import redis.asyncio as redis
from fastapi import HTTPException

from shared.redis_client import get_redis


class RateLimiter:
    """Rate limiting for story generation and API requests"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check_story_generation_limit(self, user_id: UUID) -> bool:
        """Check if user has exceeded story generation limit (5 per hour)"""
        key = f"story_gen_limit:{user_id}"
        current_time = int(time.time())
        hour_start = current_time - (current_time % 3600)  # Start of current hour

        # Use Redis sorted set to track generations within the hour
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, hour_start - 1)  # Remove old entries
        pipe.zcard(key)  # Count current entries
        pipe.expire(key, 3600)  # Set expiry for cleanup

        results = await pipe.execute()
        current_count = results[1]

        if current_count >= 5:
            return False

        # Add current generation
        await self.redis.zadd(key, {str(current_time): current_time})
        await self.redis.expire(key, 3600)

        return True

    async def check_api_rate_limit(self, user_id: UUID) -> bool:
        """Check API rate limit (100 requests per minute)"""
        key = f"api_limit:{user_id}"
        current_time = int(time.time())
        minute_start = current_time - (current_time % 60)  # Start of current minute

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, minute_start - 1)  # Remove old entries
        pipe.zcard(key)  # Count current entries
        pipe.expire(key, 60)  # Set expiry for cleanup

        results = await pipe.execute()
        current_count = results[1]

        if current_count >= 100:
            return False

        # Add current request
        await self.redis.zadd(key, {str(current_time): current_time})
        await self.redis.expire(key, 60)

        return True

    async def check_burst_limit(self, user_id: UUID) -> bool:
        """Check burst limit (10 requests per 10 seconds)"""
        key = f"burst_limit:{user_id}"
        current_time = int(time.time())
        window_start = current_time - 10  # 10 seconds ago

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start - 1)  # Remove old entries
        pipe.zcard(key)  # Count current entries
        pipe.expire(key, 10)  # Set expiry for cleanup

        results = await pipe.execute()
        current_count = results[1]

        if current_count >= 10:
            return False

        # Add current request
        await self.redis.zadd(key, {str(current_time): current_time})
        await self.redis.expire(key, 10)

        return True


async def check_rate_limits(user_id: UUID, is_story_generation: bool = False):
    """Dependency to check all rate limits"""
    redis_client = await get_redis()
    rate_limiter = RateLimiter(redis_client)

    # Check burst limit
    if not await rate_limiter.check_burst_limit(user_id):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: Too many requests in short time. Please wait 10 seconds.",
        )

    # Check API rate limit
    if not await rate_limiter.check_api_rate_limit(user_id):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: Too many API requests per minute. Please wait.",
        )

    # Check story generation limit if applicable
    if is_story_generation:
        if not await rate_limiter.check_story_generation_limit(user_id):
            raise HTTPException(
                status_code=429,
                detail="Story generation limit exceeded: Maximum 5 stories per hour.",
            )


async def check_story_generation_rate_limit(user_id: UUID):
    """Specific rate limit check for story generation"""
    await check_rate_limits(user_id, is_story_generation=True)


async def check_api_rate_limit_only(user_id: UUID):
    """Rate limit check for regular API endpoints"""
    await check_rate_limits(user_id, is_story_generation=False)
