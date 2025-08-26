from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator

from src.schemas.base import BaseSchema, TimestampMixin

# Enums
ORGANIZATION_TYPES = ["hospital", "clinic", "vendor", "distributor"]
LICENSE_TIERS = ["free", "basic", "professional", "enterprise"]

class OrganizationBase(BaseSchema):
    """Base organization schema"""
    name: str = Field(..., min_length=1, max_length=255)
    type: str
    subdomain: Optional[str] = Field(None, min_length=3, max_length=100)
    
    # Address
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state_province: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country_code: Optional[str] = Field(None, min_length=2, max_length=2)
    
    # Contact
    phone: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = None
    
    # Business info
    employee_count_range: Optional[str] = None
    annual_revenue_range: Optional[str] = None
    specialties: Optional[List[str]] = None
    
    @field_validator('type')
    def validate_type(cls, v):
        if v not in ORGANIZATION_TYPES:
            raise ValueError(f'Invalid type. Must be one of: {", ".join(ORGANIZATION_TYPES)}')
        return v
    
    @field_validator('subdomain')
    def validate_subdomain(cls, v):
        if v is None:
            return v
        # Subdomain validation: lowercase, alphanumeric with hyphens
        import re
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError('Subdomain must be lowercase alphanumeric with hyphens only')
        if v.startswith('-') or v.endswith('-'):
            raise ValueError('Subdomain cannot start or end with a hyphen')
        return v
    
    @field_validator('country_code')
    def validate_country_code(cls, v):
        if v is None:
            return v
        # Must be 2-letter ISO code
        if len(v) != 2 or not v.isalpha():
            raise ValueError('Country code must be 2-letter ISO code')
        return v.upper()

class OrganizationCreate(OrganizationBase):
    """Schema for creating an organization"""
    license_tier: str = "free"
    
    @field_validator('license_tier')
    def validate_license_tier(cls, v):
        if v not in LICENSE_TIERS:
            raise ValueError(f'Invalid license tier. Must be one of: {", ".join(LICENSE_TIERS)}')
        return v

class OrganizationUpdate(BaseSchema):
    """Schema for updating an organization"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    subdomain: Optional[str] = Field(None, min_length=3, max_length=100)
    
    # Address
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state_province: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country_code: Optional[str] = Field(None, min_length=2, max_length=2)
    
    # Contact
    phone: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = None
    
    # Business info
    employee_count_range: Optional[str] = None
    annual_revenue_range: Optional[str] = None
    specialties: Optional[List[str]] = None
    
    # Settings
    settings: Optional[Dict[str, Any]] = None
    branding: Optional[Dict[str, Any]] = None

class OrganizationInDB(OrganizationBase, TimestampMixin):
    """Organization schema with database fields"""
    id: int
    license_tier: str = "free"
    license_expires_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    is_verified: bool = False
    verified_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    
    # Contact IDs
    primary_contact_id: Optional[int] = None
    billing_contact_id: Optional[int] = None
    technical_contact_id: Optional[int] = None
    
    # Settings
    settings: Dict[str, Any] = {}
    branding: Dict[str, Any] = {}
    certifications: Dict[str, Any] = {}

class OrganizationResponse(OrganizationInDB):
    """Organization response schema"""
    is_active: bool = True
    is_healthcare_provider: bool = False
    is_vendor: bool = False
    has_valid_license: bool = True
    in_trial: bool = False
    user_count: int = 0
    device_count: int = 0
    
    @classmethod
    def from_orm_with_counts(cls, org, user_count: int = 0, device_count: int = 0):
        """Create response with computed fields and counts"""
        data = {
            **org.__dict__,
            "is_active": org.is_active,
            "is_healthcare_provider": org.is_healthcare_provider,
            "is_vendor": org.is_vendor,
            "has_valid_license": org.has_valid_license,
            "in_trial": org.in_trial,
            "user_count": user_count,
            "device_count": device_count
        }
        return cls(**data)

class OrganizationList(BaseSchema):
    """List of organizations"""
    organizations: List[OrganizationResponse]
    total: int

# Department schemas
class DepartmentBase(BaseSchema):
    """Base department schema"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[int] = None

class DepartmentCreate(DepartmentBase):
    """Schema for creating a department"""
    organization_id: int

class DepartmentUpdate(BaseSchema):
    """Schema for updating a department"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[int] = None

class DepartmentResponse(DepartmentBase, TimestampMixin):
    """Department response schema"""
    id: int
    organization_id: int
    user_count: int = 0

class DepartmentList(BaseSchema):
    """List of departments"""
    departments: List[DepartmentResponse]
    total: int

# License management
class LicenseUpdate(BaseSchema):
    """Update organization license"""
    license_tier: str
    expires_at: Optional[datetime] = None
    
    @field_validator('license_tier')
    def validate_license_tier(cls, v):
        if v not in LICENSE_TIERS:
            raise ValueError(f'Invalid license tier. Must be one of: {", ".join(LICENSE_TIERS)}')
        return v

class OrganizationVerification(BaseSchema):
    """Organization verification request"""
    verification_documents: List[str]  # URLs to uploaded documents
    notes: Optional[str] = None
