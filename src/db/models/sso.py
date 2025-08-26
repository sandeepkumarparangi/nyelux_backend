"""
SSO and Organization Invitation Models

This module defines database models for:
- SSO configurations and sessions
- Organization invitations
- Domain verification
- Manual verification requests
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from src.db.base_class import Base


class SSOConfiguration(Base):
    """SSO configuration for organizations"""
    __tablename__ = "sso_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, unique=True)
    provider_type = Column(String(50), nullable=False)  # google, saml, azure_ad, okta
    enabled = Column(Boolean, default=True)
    configuration = Column(JSON)  # Provider-specific config
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="sso_configuration")


class SSOSession(Base):
    """OAuth/SSO session storage"""
    __tablename__ = "sso_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    provider = Column(String(50), nullable=False)
    provider_user_id = Column(String(255))
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="sso_sessions")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'provider', name='_user_provider_uc'),
    )


class OrganizationInvitation(Base):
    """Invitations to join organizations"""
    __tablename__ = "organization_invitations"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(50), default="viewer")
    department = Column(String(255))
    invitation_code = Column(String(100), unique=True, nullable=False, index=True)
    temporary_password_hash = Column(String(255))  # Hashed temp password
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime)
    device_access = Column(JSON)  # Specific device permissions
    message = Column(Text)  # Custom message from inviter
    
    created_by = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="invitations")
    creator = relationship("User", foreign_keys=[created_by])


class OrganizationDomain(Base):
    """Whitelisted domains for automatic organization membership"""
    __tablename__ = "organization_domains"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    domain = Column(String(255), nullable=False, index=True)
    verified = Column(Boolean, default=False)
    auto_approve = Column(Boolean, default=False)
    default_role = Column(String(50), default="healthcare_professional")
    verification_token = Column(String(255))
    verification_method = Column(String(50))  # dns_txt, email_admin, file_upload
    verified_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="domains")
    
    __table_args__ = (
        UniqueConstraint('organization_id', 'domain', name='_org_domain_uc'),
    )


class VerificationRequest(Base):
    """Manual verification requests for users"""
    __tablename__ = "verification_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    organization_name = Column(String(255))
    department = Column(String(255))
    license_number = Column(String(100))
    documents = Column(JSON)  # List of document URLs/IDs
    notes = Column(Text)
    status = Column(String(50), default="pending")  # pending, approved, rejected, info_needed
    priority = Column(String(20), default="normal")  # low, normal, high, urgent
    
    reviewer_id = Column(Integer, ForeignKey("user.id"))
    reviewer_notes = Column(Text)
    reviewed_at = Column(DateTime)
    
    assigned_role = Column(String(50))
    assigned_organization_id = Column(Integer, ForeignKey("organization.id"))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    assigned_organization = relationship("Organization", foreign_keys=[assigned_organization_id])
