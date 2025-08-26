from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, 
    UniqueConstraint, Index, CheckConstraint, DECIMAL
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from typing import TYPE_CHECKING

from src.db.base_class import Base

if TYPE_CHECKING:
    from src.db.models.user import User

class Organization(Base):
    """
    Organization model for multi-tenant architecture.
    Supports hospitals, clinics, vendors, and distributors.
    """
    __tablename__ = "organizations"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic information
    name = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)  # hospital, clinic, vendor, distributor
    subdomain = Column(String(100), unique=True, nullable=True, index=True)
    
    # Licensing
    license_tier = Column(String(50), default='free', nullable=False)  # free, basic, professional, enterprise
    license_expires_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    
    # Settings and branding
    settings = Column(JSONB, default=dict, nullable=False)
    branding = Column(JSONB, default=dict, nullable=False)
    
    # Address information
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state_province = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country_code = Column(String(2), nullable=True)  # ISO 3166-1 alpha-2
    
    # Contact information
    phone = Column(String(20), nullable=True)
    website = Column(Text, nullable=True)
    
    # Contact persons (foreign keys)
    primary_contact_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    billing_contact_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    technical_contact_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Business information
    employee_count_range = Column(String(50), nullable=True)  # 1-10, 11-50, 51-200, etc.
    annual_revenue_range = Column(String(50), nullable=True)  # <1M, 1-10M, 10-50M, etc.
    specialties = Column(ARRAY(Text), nullable=True)
    certifications = Column(JSONB, default=dict, nullable=True)
    
    # Verification
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Relationships - all properly defined with string references
    users = relationship(
        "User",
        foreign_keys="User.organization_id",
        back_populates="organization"
    )
    departments = relationship(
        "Department",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    vendor_devices = relationship(
        "VendorDevice",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    device_documents = relationship(
        "DeviceDocument",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    device_videos = relationship(
        "DeviceVideo",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    device_incidents = relationship(
        "DeviceIncident",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    teams = relationship(
        "Team",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    # Removed calendar_events relationship - CalendarEvent doesn't have organization_id
    api_keys = relationship(
        "APIKey",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    subscription = relationship(
        "Subscription",
        back_populates="organization",
        uselist=False,
        cascade="all, delete-orphan"
    )
    invoices = relationship(
        "Invoice",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    payment_methods = relationship(
        "PaymentMethod",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    notes = relationship(
        "Note",
        back_populates="organization",
        cascade="all, delete-orphan"
    )
    
    # FIXED: Comment out problematic SSO relationships for now
    # sso_configuration = relationship(
    #     "SSOConfiguration",
    #     back_populates="organization",
    #     uselist=False,
    #     cascade="all, delete-orphan"
    # )
    # invitations = relationship(
    #     "OrganizationInvitation",
    #     back_populates="organization",
    #     cascade="all, delete-orphan"
    # )
    # domains = relationship(
    #     "OrganizationDomain",
    #     back_populates="organization",
    #     cascade="all, delete-orphan"
    # )
    
    # Email domain configuration
    allowed_email_domains = Column(ARRAY(String), nullable=True)
    auto_approve_domains = Column(Boolean, default=False)
    default_role = Column(String(50), default="healthcare_professional")
    
    # SSO configuration
    sso_enabled = Column(Boolean, default=False)
    sso_provider = Column(String(50), nullable=True)  # google, saml, azure
    sso_config = Column(JSONB, nullable=True)  # Provider-specific configuration
    sso_metadata_url = Column(Text, nullable=True)  # SAML metadata URL
    sso_entity_id = Column(String(255), nullable=True)  # SAML entity ID
    sso_login_url = Column(Text, nullable=True)  # IdP login URL
    sso_logout_url = Column(Text, nullable=True)  # IdP logout URL
    sso_certificate = Column(Text, nullable=True)  # IdP certificate
    
    # Contact relationships (avoiding circular references with post_update)
    primary_contact = relationship(
        "User",
        foreign_keys=[primary_contact_id],
        post_update=True
    )
    billing_contact = relationship(
        "User",
        foreign_keys=[billing_contact_id],
        post_update=True
    )
    technical_contact = relationship(
        "User",
        foreign_keys=[technical_contact_id],
        post_update=True
    )
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("type IN ('hospital', 'clinic', 'vendor', 'distributor')", name='check_org_type'),
        CheckConstraint("license_tier IN ('free', 'basic', 'professional', 'enterprise')", name='check_license_tier'),
        CheckConstraint("LENGTH(country_code) = 2", name='check_country_code_length'),
        Index('idx_org_type_active', 'type', 'deleted_at'),
        Index('idx_org_verified', 'is_verified', 'deleted_at'),
    )
    
    @property
    def is_active(self) -> bool:
        """Check if organization is active"""
        return self.deleted_at is None
    
    @property
    def is_healthcare_provider(self) -> bool:
        """Check if organization is a healthcare provider"""
        return self.type in ['hospital', 'clinic']
    
    @property
    def is_vendor(self) -> bool:
        """Check if organization is a vendor or distributor"""
        return self.type in ['vendor', 'distributor']
    
    @property
    def has_valid_license(self) -> bool:
        """Check if organization has a valid license"""
        from datetime import datetime
        if self.license_tier == 'free':
            return True
        if self.license_expires_at is None:
            return False
        return self.license_expires_at > datetime.utcnow()
    
    @property
    def in_trial(self) -> bool:
        """Check if organization is in trial period"""
        from datetime import datetime
        if self.trial_ends_at is None:
            return False
        return self.trial_ends_at > datetime.utcnow()
    
    def get_setting(self, key: str, default=None):
        """Get a setting value"""
        return self.settings.get(key, default) if self.settings else default
    
    def set_setting(self, key: str, value):
        """Set a setting value"""
        if self.settings is None:
            self.settings = {}
        self.settings[key] = value
    
    def __repr__(self):
        return f"<Organization {self.name} ({self.type})>"


class Department(Base):
    """
    Department model for organizational structure.
    """
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="departments")
    users = relationship("User", back_populates="department")
    parent = relationship("Department", remote_side=[id])
    notes = relationship("Note", back_populates="department")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('organization_id', 'name', name='uq_org_dept_name'),
        Index('idx_dept_org', 'organization_id'),
    )
    
    def __repr__(self):
        return f"<Department {self.name}>"
