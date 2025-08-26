"""
SSO Configuration model for organizations.
This was missing and causing the relationship error.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base_class import Base


class SSOConfiguration(Base):
    """SSO Configuration for organizations"""
    __tablename__ = "sso_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, nullable=False)
    
    # SSO Settings
    provider = Column(String(50), nullable=False)  # okta, azure, google, saml
    enabled = Column(Boolean, default=True)
    
    # Configuration
    config = Column(JSONB, nullable=False, default=dict)
    metadata_url = Column(Text, nullable=True)
    entity_id = Column(String(255), nullable=True)
    login_url = Column(Text, nullable=True)
    logout_url = Column(Text, nullable=True)
    certificate = Column(Text, nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="sso_configuration")
    
    def __repr__(self):
        return f"<SSOConfiguration {self.provider} for org {self.organization_id}>"


class OrganizationInvitation(Base):
    """Organization invitations"""
    __tablename__ = "organization_invitations"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="invitations")
    
    def __repr__(self):
        return f"<OrganizationInvitation {self.email} to {self.organization_id}>"


class OrganizationDomain(Base):
    """Allowed email domains for organizations"""
    __tablename__ = "organization_domains"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    domain = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String(255), nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="domains")
    
    def __repr__(self):
        return f"<OrganizationDomain {self.domain} for {self.organization_id}>"
