# shared/app_config_cache.py
"""
App configuration caching utilities for the fairydust platform.
Provides Redis-based caching for frequently accessed app configurations.
"""

import json
import logging
from typing import Optional, Dict, Any
from uuid import UUID
import redis.asyncio as redis

from shared.json_utils import safe_json_parse, safe_json_dumps

logger = logging.getLogger(__name__)

class AppConfigCache:
    """Redis-based cache for app configurations"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.cache_ttl = 15 * 60  # 15 minutes TTL
        
    def _get_cache_key(self, app_id: str, config_type: str = "model_config") -> str:
        """Generate cache key for app configuration"""
        return f"app_config:{app_id}:{config_type}"
    
    async def get_model_config(self, app_id: str) -> Optional[Dict[str, Any]]:
        """
        Get LLM model configuration from cache.
        
        Args:
            app_id: App identifier (UUID or slug)
            
        Returns:
            Cached configuration dict or None if not found
        """
        try:
            cache_key = self._get_cache_key(app_id, "model_config")
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                # Handle both string and bytes from Redis
                cached_str = cached_data.decode() if isinstance(cached_data, bytes) else cached_data
                config = safe_json_parse(cached_str, expected_type=dict)
                
                if config:
                    logger.debug(f"Cache hit for app {app_id} model config")
                    return config
                    
        except Exception as e:
            logger.warning(f"Failed to get model config from cache for app {app_id}: {e}")
            
        return None
    
    async def set_model_config(self, app_id: str, config: Dict[str, Any]) -> bool:
        """
        Store LLM model configuration in cache.
        
        Args:
            app_id: App identifier (UUID or slug)
            config: Configuration dictionary to cache
            
        Returns:
            True if successfully cached, False otherwise
        """
        try:
            cache_key = self._get_cache_key(app_id, "model_config")
            config_json = safe_json_dumps(config)
            
            await self.redis.setex(cache_key, self.cache_ttl, config_json)
            logger.debug(f"Cached model config for app {app_id}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to cache model config for app {app_id}: {e}")
            return False
    
    async def invalidate_model_config(self, app_id: str) -> bool:
        """
        Invalidate cached model configuration for an app.
        
        Args:
            app_id: App identifier (UUID or slug)
            
        Returns:
            True if successfully invalidated, False otherwise
        """
        try:
            cache_key = self._get_cache_key(app_id, "model_config")
            result = await self.redis.delete(cache_key)
            
            if result:
                logger.debug(f"Invalidated model config cache for app {app_id}")
                return True
            else:
                logger.debug(f"No cached model config found to invalidate for app {app_id}")
                return False
                
        except Exception as e:
            logger.warning(f"Failed to invalidate model config cache for app {app_id}: {e}")
            return False
    
    async def get_app_basic_info(self, app_id: str) -> Optional[Dict[str, Any]]:
        """
        Get basic app information from cache.
        
        Args:
            app_id: App identifier (UUID or slug)
            
        Returns:
            Cached app info dict or None if not found
        """
        try:
            cache_key = self._get_cache_key(app_id, "basic_info")
            cached_data = await self.redis.get(cache_key)
            
            if cached_data:
                cached_str = cached_data.decode() if isinstance(cached_data, bytes) else cached_data
                app_info = safe_json_parse(cached_str, expected_type=dict)
                
                if app_info:
                    logger.debug(f"Cache hit for app {app_id} basic info")
                    return app_info
                    
        except Exception as e:
            logger.warning(f"Failed to get app basic info from cache for app {app_id}: {e}")
            
        return None
    
    async def set_app_basic_info(self, app_id: str, app_info: Dict[str, Any]) -> bool:
        """
        Store basic app information in cache.
        
        Args:
            app_id: App identifier (UUID or slug)
            app_info: App information dictionary to cache
            
        Returns:
            True if successfully cached, False otherwise
        """
        try:
            cache_key = self._get_cache_key(app_id, "basic_info")
            info_json = safe_json_dumps(app_info)
            
            await self.redis.setex(cache_key, self.cache_ttl, info_json)
            logger.debug(f"Cached basic info for app {app_id}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to cache basic info for app {app_id}: {e}")
            return False
    
    async def invalidate_app_basic_info(self, app_id: str) -> bool:
        """
        Invalidate cached basic app information.
        
        Args:
            app_id: App identifier (UUID or slug)
            
        Returns:
            True if successfully invalidated, False otherwise
        """
        try:
            cache_key = self._get_cache_key(app_id, "basic_info")
            result = await self.redis.delete(cache_key)
            
            if result:
                logger.debug(f"Invalidated basic info cache for app {app_id}")
                return True
            else:
                logger.debug(f"No cached basic info found to invalidate for app {app_id}")
                return False
                
        except Exception as e:
            logger.warning(f"Failed to invalidate basic info cache for app {app_id}: {e}")
            return False
    
    async def invalidate_all_app_cache(self, app_id: str) -> bool:
        """
        Invalidate all cached data for an app.
        
        Args:
            app_id: App identifier (UUID or slug)
            
        Returns:
            True if all caches successfully invalidated, False otherwise
        """
        model_config_result = await self.invalidate_model_config(app_id)
        basic_info_result = await self.invalidate_app_basic_info(app_id)
        
        return model_config_result and basic_info_result

# Dependency function to get app config cache instance
async def get_app_config_cache() -> AppConfigCache:
    """
    Dependency to get app configuration cache instance.
    
    Returns:
        AppConfigCache instance with Redis connection
    """
    from shared.redis_client import get_redis
    
    redis_client = await get_redis()
    return AppConfigCache(redis_client)