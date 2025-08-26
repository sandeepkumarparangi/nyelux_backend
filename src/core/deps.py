"""
Common dependencies for FastAPI endpoints
"""
from typing import Optional, Annotated
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.core.config import settings
from src.services.auth_service import auth_service
from src.db.models.user import User

# Security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)]
) -> Optional[User]:
    """
    Get current user from JWT token if provided.
    Returns None if no token or invalid token.
    """
    if not credentials:
        return None
    
    try:
        user = await auth_service.get_user_from_token(db, credentials.credentials)
        return user
    except Exception:
        return None


async def get_current_active_user(
    current_user: Annotated[Optional[User], Depends(get_current_user)]
) -> User:
    """
    Get current active user. Raises exception if not authenticated.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if current_user.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account has been deleted"
        )
    
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified"
        )
    
    return current_user


async def get_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    """
    Get current user if they are an admin.
    """
    if current_user.role not in ["super_admin", "org_admin", "vendor_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_super_admin(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    """
    Get current user if they are a super admin.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return current_user


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.
    Handles proxy headers.
    """
    # Check for proxy headers
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fallback to direct connection
    if request.client:
        return request.client.host
    
    return "unknown"


def get_user_agent(request: Request) -> str:
    """
    Get user agent from request headers.
    """
    return request.headers.get("User-Agent", "unknown")


class RateLimitDep:
    """
    Rate limiting dependency.
    Can be customized per endpoint.
    """
    def __init__(self, calls: int = 100, period: int = 60):
        self.calls = calls
        self.period = period
    
    async def __call__(self, request: Request) -> bool:
        # In production, implement actual rate limiting with Redis
        # For now, just return True
        return True


class PaginationParams:
    """
    Common pagination parameters.
    """
    def __init__(
        self,
        skip: int = 0,
        limit: int = 20,
        max_limit: int = 100
    ):
        self.skip = skip
        self.limit = min(limit, max_limit)


# Common dependencies
CommonDeps = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_active_user)]
OptionalUser = Annotated[Optional[User], Depends(get_current_user)]
AdminUser = Annotated[User, Depends(get_admin_user)]
SuperAdmin = Annotated[User, Depends(get_super_admin)]
ClientIP = Annotated[str, Depends(get_client_ip)]
UserAgent = Annotated[str, Depends(get_user_agent)]
