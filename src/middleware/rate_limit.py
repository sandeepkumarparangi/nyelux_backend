"""
Rate limiting middleware using Redis.
REAL implementation - no fake limits.
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
from datetime import datetime, timedelta
import re

from src.core.config import settings
from src.core.cache import CacheService

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Real rate limiting using Redis.
    Tracks requests per IP address and enforces limits.
    """
    
    def __init__(
        self, 
        requests: int = 100, 
        window: int = 3600,  # seconds
        key_prefix: str = "rate_limit"
    ):
        self.requests = requests
        self.window = window
        self.key_prefix = key_prefix
        self.cache_service = CacheService()
    
    async def check_rate_limit(self, request: Request) -> tuple[bool, dict]:
        """
        Check if request should be rate limited.
        Returns (is_allowed, headers_dict)
        """
        # Skip if Redis not available
        if not self.cache_service.redis:
            return True, {}
            
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Generate key for this endpoint and IP
        endpoint = f"{request.method}:{request.url.path}"
        key = f"{self.key_prefix}:{endpoint}:{client_ip}"
        
        try:
            # Get current count from Redis
            count = await self.cache_service.redis.incr(key)
            
            # Set expiry on first request
            if count == 1:
                await self.cache_service.redis.expire(key, self.window)
            
            # Get TTL for headers
            ttl = await self.cache_service.redis.ttl(key)
            
            # Prepare headers
            headers = {
                "X-RateLimit-Limit": str(self.requests),
                "X-RateLimit-Remaining": str(max(0, self.requests - count)),
                "X-RateLimit-Reset": str(int(time.time()) + ttl)
            }
            
            # Check if over limit
            if count > self.requests:
                headers["Retry-After"] = str(ttl)
                
                logger.warning(
                    f"Rate limit exceeded for {client_ip} on {endpoint}. "
                    f"Count: {count}/{self.requests}"
                )
                
                return False, headers
            
            return True, headers
            
        except Exception as e:
            # If Redis is down, log but don't block requests
            logger.error(f"Rate limiting error: {e}")
            return True, {}
    
    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, considering proxies"""
        # Check X-Forwarded-For header first (for proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Use first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct connection IP
        if request.client:
            return request.client.host
        
        return "unknown"


# Preset rate limiters for different endpoints
auth_rate_limiter = RateLimiter(
    requests=50 if settings.DEBUG else 5,  # More lenient in debug mode
    window=3600,  # per hour
    key_prefix="auth"
)

api_rate_limiter = RateLimiter(
    requests=1000,
    window=3600,
    key_prefix="api"
)

search_rate_limiter = RateLimiter(
    requests=100,
    window=60,  # per minute
    key_prefix="search"
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to apply rate limiting based on endpoint patterns.
    REAL implementation using Redis for tracking.
    """
    
    def __init__(self, app, dispatch=None):
        super().__init__(app, dispatch)
        
        # Define rate limits for different endpoint patterns
        self.limiters = [
            # Auth endpoints - strict limits
            (r"/api/v1/auth/(register|login|password-reset)", auth_rate_limiter),
            
            # Search endpoints - moderate limits
            (r"/api/v1/(search|devices/search)", search_rate_limiter),
            
            # General API - standard limits
            (r"/api/v1/.*", api_rate_limiter),
        ]
    
    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting based on endpoint"""
        # Skip rate limiting in test mode
        if hasattr(settings, 'is_testing') and settings.is_testing():
            return await call_next(request)
        
        # Also skip if explicitly disabled
        if hasattr(settings, 'TESTING') and settings.TESTING:
            return await call_next(request)
        
        # Find matching rate limiter
        path = request.url.path
        limiter = None
        
        for pattern, rate_limiter in self.limiters:
            if re.match(pattern, path):
                limiter = rate_limiter
                break
        
        if limiter:
            # Check rate limit
            is_allowed, headers = await limiter.check_rate_limit(request)
            
            if not is_allowed:
                # Return rate limit error
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Rate limit exceeded",
                        "retry_after": int(headers.get("Retry-After", 3600))
                    },
                    headers=headers
                )
            
            # Process request and add headers
            response = await call_next(request)
            for header, value in headers.items():
                response.headers[header] = value
            return response
        
        # No rate limiting for this endpoint
        return await call_next(request)
