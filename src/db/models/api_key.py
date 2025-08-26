from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, ARRAY, Text,
    Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import secrets
import hashlib

from src.db.base_class import Base


class APIKey(Base):
    """
    Third-party API access management.
    """
    __tablename__ = "api_keys"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Organization association
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Key details
    name = Column(String(255), nullable=False, comment="Descriptive name for the key")
    key_hash = Column(String(255), nullable=False, unique=True, comment="SHA-256 hash of the key")
    key_prefix = Column(String(10), nullable=True, comment="First few chars for identification")
    
    # Permissions
    scopes = Column(ARRAY(String), nullable=False, default=list, comment="API permissions")
    
    # Rate limiting
    rate_limit_per_hour = Column(Integer, nullable=False, default=1000)
    
    # Usage tracking
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_used_ip = Column(String, nullable=True)
    
    # Lifecycle
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Audit trail
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    revoked_reason = Column(Text, nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="api_keys")
    created_by_user = relationship("User", foreign_keys=[created_by], back_populates="api_keys")
    revoker = relationship("User", foreign_keys=[revoked_by])
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("rate_limit_per_hour > 0", name='check_rate_limit_positive'),
        Index('idx_api_key_hash', 'key_hash'),
        Index('idx_api_key_org_active', 'organization_id', 'is_active'),
        Index('idx_api_key_expires', 'expires_at'),
    )
    
    @property
    def is_valid(self) -> bool:
        """Check if API key is currently valid"""
        if not self.is_active:
            return False
        if self.revoked_at:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True
    
    @property
    def is_expired(self) -> bool:
        """Check if API key has expired"""
        return self.expires_at and self.expires_at < datetime.utcnow()
    
    @property
    def days_until_expiry(self) -> int:
        """Calculate days until expiry"""
        if not self.expires_at:
            return -1  # Never expires
        delta = self.expires_at - datetime.utcnow()
        return delta.days
    
    @property
    def usage_in_current_hour(self) -> int:
        """Get usage count in current hour (would be tracked in Redis)"""
        # This would actually query Redis in production
        return 0
    
    def has_scope(self, scope: str) -> bool:
        """Check if key has specific scope"""
        return scope in self.scopes or 'admin' in self.scopes
    
    def has_any_scope(self, scopes: list) -> bool:
        """Check if key has any of the provided scopes"""
        return any(self.has_scope(scope) for scope in scopes)
    
    @staticmethod
    def generate_key() -> tuple:
        """Generate a new API key and its hash"""
        # Generate secure random key
        raw_key = f"sk_{secrets.token_urlsafe(32)}"
        
        # Create hash for storage
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        
        # Extract prefix for identification
        key_prefix = raw_key[:8]
        
        return raw_key, key_hash, key_prefix
    
    def update_usage(self, ip_address: str = None):
        """Update last usage information"""
        self.last_used_at = datetime.utcnow()
        if ip_address:
            self.last_used_ip = ip_address
    
    def revoke(self, user_id: int, reason: str = None):
        """Revoke the API key"""
        self.is_active = False
        self.revoked_at = datetime.utcnow()
        self.revoked_by = user_id
        self.revoked_reason = reason
    
    def extend_expiry(self, days: int):
        """Extend expiry date by specified days"""
        if self.expires_at:
            self.expires_at += timedelta(days=days)
        else:
            self.expires_at = datetime.utcnow() + timedelta(days=days)
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert to dictionary for API responses"""
        result = {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "scopes": self.scopes,
            "rate_limit_per_hour": self.rate_limit_per_hour,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "is_valid": self.is_valid,
            "is_expired": self.is_expired,
            "days_until_expiry": self.days_until_expiry,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if self.revoked_at:
            result.update({
                "revoked_at": self.revoked_at.isoformat(),
                "revoked_by": self.revoked_by,
                "revoked_reason": self.revoked_reason,
            })
        
        if include_sensitive:
            result["last_used_ip"] = self.last_used_ip
        
        return result
    
    def __repr__(self):
        return f"<APIKey {self.key_prefix}... : {'Active' if self.is_valid else 'Inactive'}>"
