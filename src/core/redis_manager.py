"""
Redis Manager for caching and real-time features
PRODUCTION READY with proper error handling
"""
import json
import redis.asyncio as redis
from typing import Optional, Any, List, Dict
import logging
from datetime import timedelta

from src.core.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """
    Production Redis manager with graceful degradation.
    If Redis is not available, the app continues to work without caching.
    """
    
    def __init__(self):
        """Initialize Redis connection if available"""
        self.redis_client = None
        self.available = False
        
        if settings.REDIS_URL:
            try:
                self.redis_client = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=50,
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                # Don't test connection in __init__ to avoid event loop issues
                # Connection will be tested on first use
                self.available = True  # Assume available until proven otherwise
                logger.info("Redis client initialized")
            except Exception as e:
                logger.warning(f"Redis initialization failed: {e}")
                self.redis_client = None
                self.available = False
        else:
            logger.info("Redis URL not configured - running without caching")
    
    async def _test_connection(self):
        """Test Redis connection"""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.ping()
            self.available = True
        except Exception:
            self.available = False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis. Returns None if Redis unavailable."""
        if not self.available or not self.redis_client:
            return None
            
        try:
            value = await self.redis_client.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.debug(f"Redis get error (non-critical): {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> bool:
        """Set value in Redis. Returns False if Redis unavailable."""
        if not self.available or not self.redis_client:
            return False
            
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            if expire:
                await self.redis_client.setex(key, expire, value)
            else:
                await self.redis_client.set(key, value)
            
            return True
        except Exception as e:
            logger.debug(f"Redis set error (non-critical): {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        if not self.available or not self.redis_client:
            return False
            
        try:
            await self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Redis delete error (non-critical): {e}")
            return False
    
    async def incr(self, key: str, amount: int = 1, expire: Optional[int] = None) -> int:
        """Increment counter. Returns 0 if Redis unavailable."""
        if not self.available or not self.redis_client:
            return 0
            
        try:
            value = await self.redis_client.incrby(key, amount)
            if expire:
                await self.redis_client.expire(key, expire)
            return value
        except Exception as e:
            logger.debug(f"Redis incr error (non-critical): {e}")
            return 0
    
    async def lpush(self, key: str, *values) -> int:
        """Push values to list."""
        if not self.available or not self.redis_client:
            return 0
            
        try:
            return await self.redis_client.lpush(key, *values)
        except Exception as e:
            logger.debug(f"Redis lpush error (non-critical): {e}")
            return 0
    
    async def lrange(self, key: str, start: int, stop: int) -> List[str]:
        """Get range from list."""
        if not self.available or not self.redis_client:
            return []
            
        try:
            return await self.redis_client.lrange(key, start, stop)
        except Exception as e:
            logger.debug(f"Redis lrange error (non-critical): {e}")
            return []
    
    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel."""
        if not self.available or not self.redis_client:
            return 0
            
        try:
            if isinstance(message, (dict, list)):
                message = json.dumps(message)
            return await self.redis_client.publish(channel, message)
        except Exception as e:
            logger.debug(f"Redis publish error (non-critical): {e}")
            return 0
    
    async def subscribe(self, *channels):
        """Subscribe to channels."""
        if not self.available or not self.redis_client:
            return None
            
        try:
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(*channels)
            return pubsub
        except Exception as e:
            logger.debug(f"Redis subscribe error (non-critical): {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check Redis connection."""
        if not self.redis_client:
            return False
            
        try:
            await self.redis_client.ping()
            self.available = True
            return True
        except Exception:
            self.available = False
            return False


# Optional helper for endpoints that need Redis
class OptionalRedisManager:
    """
    Wrapper that returns None if Redis is not configured.
    Use this in endpoints where Redis is optional.
    """
    
    def __init__(self):
        try:
            if settings.REDIS_URL:
                self.manager = RedisManager()
            else:
                self.manager = None
        except Exception:
            self.manager = None
    
    def __getattr__(self, name):
        if self.manager:
            return getattr(self.manager, name)
        # Return a no-op function
        async def noop(*args, **kwargs):
            return None if name == 'get' else False if name in ['set', 'delete'] else 0 if name == 'incr' else []
        return noop
