"""
API Key Authentication for Public Endpoints
Secure access without exposing data publicly
"""
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from typing import Optional
import hashlib
import secrets
import logging

from src.core.config import settings

logger = logging.getLogger(__name__)

# API Key can be passed in header or query parameter
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

class APIKeyValidator:
    """
    Validates API keys for accessing public endpoints.
    Keys are stored as hashes for security.
    """
    
    def __init__(self):
        # In production, store these in database with proper hashing
        # For now, we'll use environment variable
        self.valid_api_keys = set()
        
        # Add API key from environment if available
        if hasattr(settings, 'PUBLIC_API_KEY'):
            # Store hash of the key, not the key itself
            key_hash = hashlib.sha256(settings.PUBLIC_API_KEY.encode()).hexdigest()
            self.valid_api_keys.add(key_hash)
            logger.info("API key authentication enabled")
        else:
            # Generate a default key for development
            default_key = "dev-" + secrets.token_urlsafe(32)
            key_hash = hashlib.sha256(default_key.encode()).hexdigest()
            self.valid_api_keys.add(key_hash)
            logger.warning(f"No PUBLIC_API_KEY set. Generated dev key: {default_key}")
    
    def validate_key(self, api_key: str) -> bool:
        """Validate an API key by checking its hash."""
        if not api_key:
            return False
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return key_hash in self.valid_api_keys
    
    def add_key(self, api_key: str):
        """Add a new valid API key (stores hash)."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        self.valid_api_keys.add(key_hash)
    
    def revoke_key(self, api_key: str):
        """Revoke an API key."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        self.valid_api_keys.discard(key_hash)

# Global validator instance
api_key_validator = APIKeyValidator()

async def verify_api_key(
    api_key_header: Optional[str] = Security(api_key_header),
    api_key_query: Optional[str] = Security(api_key_query),
) -> str:
    """
    Validate API key from header or query parameter.
    Returns the validated key or raises 403 Forbidden.
    """
    # Check header first, then query parameter
    api_key = api_key_header or api_key_query
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key required. Pass via X-API-Key header or api_key query parameter."
        )
    
    if not api_key_validator.validate_key(api_key):
        # Log invalid attempt for security monitoring
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    
    return api_key

async def optional_api_key(
    api_key_header: Optional[str] = Security(api_key_header),
    api_key_query: Optional[str] = Security(api_key_query),
) -> Optional[str]:
    """
    Optional API key validation.
    Returns the key if valid, None otherwise.
    Useful for endpoints that have different behavior with/without authentication.
    """
    api_key = api_key_header or api_key_query
    
    if api_key and api_key_validator.validate_key(api_key):
        return api_key
    
    return None

def generate_api_key() -> str:
    """Generate a new secure API key."""
    prefix = "nyelux"
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"

# Rate limiting per API key
class APIKeyRateLimiter:
    """
    Rate limiting per API key to prevent abuse.
    """
    
    def __init__(self):
        self.limits = {}  # key -> (count, reset_time)
        self.default_limit = 1000  # requests per hour
    
    async def check_rate_limit(self, api_key: str) -> bool:
        """Check if API key has exceeded rate limit."""
        # Implementation would use Redis in production
        # This is a simple in-memory example
        return True  # For now, always allow
