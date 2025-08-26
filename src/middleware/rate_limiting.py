"""
Rate limiting middleware using Redis.
Protects API endpoints from abuse.
"""
import time
from typing import Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
import logging

from src.core.cache import cache_service
from src.core.config import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """
    Rate limiting middleware using Redis for distributed rate limiting.
    Supports per-user and per-IP rate limiting.
    """
    
    def __init__(
        self,
        requests_per_hour: int = 1000,
        requests_per_minute: int = 100,
        burst_size: int = 10
    ):
        self.requests_per_hour = requests_per_hour
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Process rate limiting"""
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/api/docs", "/api/redoc", "/api/openapi.json"]:
            return await call_next(request)
        
        # Skip in development mode
        if settings.DEBUG:
            return await call_next(request)
        
        # Get identifier (user ID or IP)
        identifier = self._get_identifier(request)
        
        # Check minute rate limit (burst protection)
        minute_allowed, minute_remaining = await cache_service.rate_limit_check(
            f"{identifier}:minute",
            limit=self.requests_per_minute,
            window=60
        )
        
        if not minute_allowed:
            return self._rate_limit_exceeded_response(
                "Too many requests. Please slow down.",
                retry_after=60
            )
        
        # Check hourly rate limit
        hour_allowed, hour_remaining = await cache_service.rate_limit_check(
            f"{identifier}:hour",
            limit=self.requests_per_hour,
            window=3600
        )
        
        if not hour_allowed:
            return self._rate_limit_exceeded_response(
                "Hourly rate limit exceeded. Please try again later.",
                retry_after=3600
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining"] = str(hour_remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 3600)
        
        return response
    
    def _get_identifier(self, request: Request) -> str:
        """Get identifier for rate limiting"""
        # Try to get user ID from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"
        
        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        
        # Check for X-Forwarded-For header (for proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()
        
        return f"ip:{client_ip}"
    
    def _rate_limit_exceeded_response(self, detail: str, retry_after: int) -> Response:
        """Create rate limit exceeded response"""
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": detail,
                "retry_after": retry_after
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": "0",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + retry_after)
            }
        )


class EndpointRateLimiter:
    """
    Endpoint-specific rate limiter for use as a dependency.
    Allows fine-grained control over specific endpoints.
    """
    
    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
    
    async def __call__(self, request: Request):
        """Check rate limit for specific endpoint"""
        # Get identifier
        user_id = getattr(request.state, "user_id", None)
        identifier = f"user:{user_id}" if user_id else f"ip:{request.client.host}"
        
        # Add endpoint to identifier
        endpoint_key = f"{identifier}:{request.url.path}"
        
        # Check rate limit
        allowed, remaining = await cache_service.rate_limit_check(
            endpoint_key,
            limit=self.requests_per_minute,
            window=60
        )
        
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests for this endpoint",
                headers={"Retry-After": "60"}
            )
        
        return True


# Pre-configured rate limiters for common use cases
rate_limit_auth = EndpointRateLimiter(requests_per_minute=5)  # Login/register
rate_limit_ai = EndpointRateLimiter(requests_per_minute=10)  # AI chat
rate_limit_upload = EndpointRateLimiter(requests_per_minute=20)  # File uploads
rate_limit_search = EndpointRateLimiter(requests_per_minute=100)  # Search
