"""
Core dependencies and helper functions for API endpoints.
"""

from typing import Optional, Generator
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
import logging

from src.db.session import get_db as get_async_db
from src.db.models.user import User
from src.core.config import settings

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Re-export get_db for compatibility
get_db = get_async_db


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """Get current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    from sqlalchemy import select
    result = await db.execute(
        select(User).where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Ensure user is active."""
    if current_user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deleted user"
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Ensure user is a superuser."""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.
    Handles proxy headers appropriately.
    """
    # Check for proxy headers first
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return forwarded_for.split(",")[0].strip()
    
    # Check for other proxy headers
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fall back to direct client IP
    if request.client:
        return request.client.host
    
    return "unknown"


class RoleChecker:
    """
    Dependency class for role-based access control.
    Usage: 
        require_role = RoleChecker(["admin", "vendor_admin"])
        @router.get("/", dependencies=[Depends(require_role)])
    """
    
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles
    
    def __call__(self, user: User = Depends(get_current_active_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{user.role}' not in {self.allowed_roles}"
            )
        return user


# Convenience role checkers
require_healthcare_professional = RoleChecker([
    "physician", "nurse", "technician", "clinical_admin", "super_admin"
])

require_vendor_role = RoleChecker([
    "vendor_admin", "vendor_rep", "super_admin"
])

require_admin = RoleChecker([
    "org_admin", "clinical_admin", "vendor_admin", "super_admin"
])


class PaginationParams:
    """
    Common pagination parameters.
    Usage:
        @router.get("/")
        async def get_items(pagination: PaginationParams = Depends()):
            offset = pagination.offset
            limit = pagination.limit
    """
    
    def __init__(
        self,
        page: int = 1,
        limit: int = 20,
        max_limit: int = 100
    ):
        if page < 1:
            page = 1
        if limit < 1:
            limit = 20
        if limit > max_limit:
            limit = max_limit
            
        self.page = page
        self.limit = limit
        self.offset = (page - 1) * limit


def create_filter_query(query, filters: dict):
    """
    Apply filters to a SQLAlchemy query.
    
    Args:
        query: Base SQLAlchemy query
        filters: Dictionary of field:value filters
    
    Returns:
        Modified query with filters applied
    """
    for field, value in filters.items():
        if value is not None:
            if isinstance(value, list):
                query = query.where(getattr(query.column_descriptions[0]['type'], field).in_(value))
            else:
                query = query.where(getattr(query.column_descriptions[0]['type'], field) == value)
    return query
