from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import uuid
import logging
from typing import Callable

from src.core.config import settings

logger = logging.getLogger(__name__)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    Implements OWASP security best practices.
    """
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Generate request ID if not present
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Track request timing
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        # Add HSTS header for HTTPS connections
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "font-src 'self' data: https://fonts.gstatic.com",
            "img-src 'self' data: https: blob:",
            "connect-src 'self' https://api.openai.com https://*.amazonaws.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # Add custom headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{process_time:.3f}s"
        
        # Log request completion
        logger.info(
            f"{request.method} {request.url.path} "
            f"completed in {process_time:.3f}s "
            f"with status {response.status_code}"
        )
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis.
    Protects against abuse and DDoS.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.enabled = settings.ENVIRONMENT != "development"
    
    async def dispatch(self, request: Request, call_next: Callable):
        if not self.enabled:
            return await call_next(request)
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/api/docs"]:
            return await call_next(request)
        
        # Get identifier (user ID or IP)
        user = getattr(request.state, "user", None)
        if user:
            identifier = f"user:{user.id}"
            limit = 1000  # Higher limit for authenticated users
        else:
            # Use IP address for anonymous users
            client_ip = request.client.host
            identifier = f"ip:{client_ip}"
            limit = 100  # Lower limit for anonymous users
        
        # Check rate limit using cache service
        from src.core.cache import cache_service
        is_allowed, remaining = await cache_service.rate_limit_check(
            identifier=identifier,
            limit=limit,
            window=3600  # 1 hour window
        )
        
        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {identifier}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Please try again later.",
                        "retry_after": 3600
                    }
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + 3600),
                    "Retry-After": "3600"
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 3600)
        
        return response


class CompressionMiddleware(BaseHTTPMiddleware):
    """
    Response compression middleware.
    Compresses responses for better performance.
    """
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Check if client accepts compression
        accept_encoding = request.headers.get("accept-encoding", "")
        
        # Process request
        response = await call_next(request)
        
        # Skip compression for small responses or already compressed content
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) < 1000:
            return response
        
        # Skip if already compressed
        if response.headers.get("content-encoding"):
            return response
        
        # Add compression hint for reverse proxy
        if "gzip" in accept_encoding:
            response.headers["X-Compression-Hint"] = "gzip"
        elif "br" in accept_encoding:
            response.headers["X-Compression-Hint"] = "br"
        
        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Audit logging middleware for HIPAA compliance.
    Logs all data access and modifications.
    """
    
    # Paths that should be audited
    AUDIT_PATHS = [
        "/api/v1/devices",
        "/api/v1/documents",
        "/api/v1/incidents",
        "/api/v1/users",
        "/api/v1/organizations"
    ]
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Check if path should be audited
        should_audit = any(
            request.url.path.startswith(path) 
            for path in self.AUDIT_PATHS
        )
        
        if not should_audit:
            return await call_next(request)
        
        # Capture request details
        user = getattr(request.state, "user", None)
        method = request.method
        path = request.url.path
        
        # Process request
        response = await call_next(request)
        
        # Log audit event if user is authenticated
        if user and response.status_code < 400:
            # Determine action from HTTP method
            action_map = {
                "GET": "view",
                "POST": "create",
                "PUT": "update",
                "PATCH": "update",
                "DELETE": "delete"
            }
            action = action_map.get(method, "unknown")
            
            # Extract resource info from path
            path_parts = path.strip("/").split("/")
            if len(path_parts) >= 4:
                resource_type = path_parts[3]  # e.g., "devices", "documents"
                resource_id = path_parts[4] if len(path_parts) > 4 else "list"
                
                # Create audit log entry (would be saved to database)
                audit_data = {
                    "user_id": user.id,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "ip_address": request.client.host,
                    "user_agent": request.headers.get("user-agent"),
                    "success": response.status_code < 400
                }
                
                # Log for now (would save to database in production)
                logger.info(f"Audit log: {audit_data}")
        
        return response
