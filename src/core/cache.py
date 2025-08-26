import redis.asyncio as redis
from typing import Optional, Any, List, Dict
import json
import logging
from datetime import timedelta

from src.core.config import settings

logger = logging.getLogger(__name__)

class CacheService:
    """
    Redis cache service for high-performance caching.
    Handles connection, serialization, and error recovery.
    """
    
    def __init__(self):
        """Initialize Redis connection"""
        self.redis = None
        self._connected = False
        
        if not settings.REDIS_URL:
            logger.warning("Redis URL not configured - cache disabled")
            return
            
        try:
            self.redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
    
    async def health_check(self) -> bool:
        """
        Check Redis connection health.
        Returns True if Redis is accessible.
        """
        if not self.redis:
            return False
        
        try:
            await self.redis.ping()
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            self._connected = False
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        Returns None if key doesn't exist or on error.
        """
        if not self.redis:
            return None
        
        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except json.JSONDecodeError:
            # Return raw value if not JSON
            return value
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        expire: int = 3600
    ) -> bool:
        """
        Set cache value with expiration.
        Default expiration is 1 hour.
        """
        if not self.redis:
            return False
        
        try:
            # Serialize to JSON
            json_value = json.dumps(value, default=str)
            
            # Set with expiration
            await self.redis.setex(key, expire, json_value)
            return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.redis:
            return False
        
        try:
            result = await self.redis.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        if not self.redis:
            return 0
        
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                return await self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self.redis:
            return False
        
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment counter"""
        if not self.redis:
            return None
        
        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {e}")
            return None
    
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values at once"""
        if not self.redis or not keys:
            return {}
        
        try:
            values = await self.redis.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value
            return result
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}
    
    async def set_many(self, data: Dict[str, Any], expire: int = 3600) -> bool:
        """Set multiple values at once"""
        if not self.redis or not data:
            return False
        
        try:
            # Prepare pipeline
            pipe = self.redis.pipeline()
            
            for key, value in data.items():
                json_value = json.dumps(value, default=str)
                pipe.setex(key, expire, json_value)
            
            # Execute pipeline
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            return False
    
    # Cache key generators for consistency
    @staticmethod
    def device_key(device_id: int) -> str:
        """Generate cache key for device"""
        return f"device:{device_id}"
    
    @staticmethod
    def user_key(user_id: int) -> str:
        """Generate cache key for user"""
        return f"user:{user_id}"
    
    @staticmethod
    def search_key(query: str, filters: dict = None) -> str:
        """Generate cache key for search results"""
        filter_str = json.dumps(filters or {}, sort_keys=True)
        return f"search:{query}:{filter_str}"
    
    @staticmethod
    def session_key(session_id: str) -> str:
        """Generate cache key for session"""
        return f"session:{session_id}"
    
    async def cache_device(self, device_id: int, device_data: dict, expire: int = 900) -> bool:
        """Cache device data (15 minutes default)"""
        key = self.device_key(device_id)
        return await self.set(key, device_data, expire)
    
    async def get_cached_device(self, device_id: int) -> Optional[dict]:
        """Get cached device data"""
        key = self.device_key(device_id)
        return await self.get(key)
    
    async def invalidate_device_cache(self, device_id: int) -> bool:
        """Invalidate device cache"""
        key = self.device_key(device_id)
        return await self.delete(key)
    
    async def rate_limit_check(
        self, 
        identifier: str, 
        limit: int = 100, 
        window: int = 3600
    ) -> tuple[bool, int]:
        """
        Check rate limit for an identifier.
        Returns (is_allowed, remaining_requests)
        """
        if not self.redis:
            return True, limit  # Allow if Redis is down
        
        key = f"rate_limit:{identifier}"
        
        try:
            # Increment counter
            current = await self.increment(key)
            
            # Set expiration on first request
            if current == 1:
                await self.redis.expire(key, window)
            
            # Check limit
            is_allowed = current <= limit
            remaining = max(0, limit - current)
            
            return is_allowed, remaining
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            return True, limit  # Allow on error
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            self._connected = False

# Dependency function for FastAPI
def get_cache_service() -> CacheService:
    """
    Get cache service instance for dependency injection.
    
    Returns:
        CacheService instance
    """
    return CacheService()
