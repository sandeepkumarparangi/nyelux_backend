from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
import re

from src.schemas.base import BaseSchema, TimestampMixin

# Enums for validation
VALID_ROLES = [
    "super_admin", "org_admin", "vendor_admin", "vendor_rep",
    "clinical_admin", "physician", "nurse", "technician", "read_only"
]

class UserBase(BaseSchema):
    """Base user schema"""
    email: EmailStr
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    title: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    language_preference: str = Field("en", max_length=10)
    timezone: str = Field("America/New_York", max_length=50)
    
    @field_validator('phone')
    def validate_phone(cls, v):
        if v is None:
            return v
        # Basic phone validation
        phone_regex = re.compile(r'^\+?1?\d{9,15}$')
        if not phone_regex.match(v.replace("-", "").replace(" ", "")):
            raise ValueError('Invalid phone number format')
        return v

class UserCreate(UserBase):
    """Schema for creating a user"""
    password: str = Field(..., min_length=8)
    role: str
    organization_id: Optional[int] = None
    department_id: Optional[int] = None
    
    @field_validator('role')
    def validate_role(cls, v):
        if v not in VALID_ROLES:
            raise ValueError(f'Invalid role. Must be one of: {", ".join(VALID_ROLES)}')
        return v
    
    @model_validator(mode='after')
    def validate_organization_requirement(self):
        """Validate organization requirement based on role"""
        # Define vendor roles that require organization
        vendor_roles = ['vendor_admin', 'vendor_rep']
        
        # Check if vendor role requires organization
        if self.role in vendor_roles and self.organization_id is None:
            raise ValueError('Vendor users must be associated with an organization')
        
        return self
    
    @field_validator('password')
    def validate_password(cls, v):
        # Password strength validation
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain special character')
        return v

class UserUpdate(BaseSchema):
    """Schema for updating a user"""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    title: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    language_preference: Optional[str] = Field(None, max_length=10)
    timezone: Optional[str] = Field(None, max_length=50)
    bio: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = None
    notification_preferences: Optional[Dict[str, Any]] = None

class UserInDB(UserBase, TimestampMixin):
    """User schema with database fields"""
    id: int
    organization_id: Optional[int] = None
    department_id: Optional[int] = None
    role: str
    email_verified: bool = False
    phone_verified: bool = False
    mfa_enabled: bool = False
    onboarding_completed: bool = False
    last_login_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

class UserResponse(UserInDB):
    """User response schema (no sensitive data)"""
    organization_name: Optional[str] = None
    department_name: Optional[str] = None
    full_name: str = ""
    is_active: bool = True
    is_admin: bool = False
    is_vendor: bool = False
    
    @classmethod
    def from_orm_with_computed(cls, user):
        """
        Create response with computed fields.
        This method safely accesses user attributes without triggering lazy loading.
        """
        # Simple approach - directly access attributes with try/except
        data = {}
        
        # Get basic attributes directly
        data['id'] = getattr(user, 'id', None)
        data['email'] = getattr(user, 'email', None)
        data['first_name'] = getattr(user, 'first_name', None)
        data['last_name'] = getattr(user, 'last_name', None)
        data['title'] = getattr(user, 'title', None)
        data['phone'] = getattr(user, 'phone', None)
        data['role'] = getattr(user, 'role', None)
        data['language_preference'] = getattr(user, 'language_preference', 'en')
        data['timezone'] = getattr(user, 'timezone', 'America/New_York')
        data['organization_id'] = getattr(user, 'organization_id', None)
        data['department_id'] = getattr(user, 'department_id', None)
        data['email_verified'] = getattr(user, 'email_verified', False)
        data['phone_verified'] = getattr(user, 'phone_verified', False)
        data['mfa_enabled'] = getattr(user, 'mfa_enabled', False)
        data['onboarding_completed'] = getattr(user, 'onboarding_completed', False)
        data['last_login_at'] = getattr(user, 'last_login_at', None)
        data['last_activity_at'] = getattr(user, 'last_activity_at', None)
        data['created_at'] = getattr(user, 'created_at', None)
        data['updated_at'] = getattr(user, 'updated_at', None)
        data['deleted_at'] = getattr(user, 'deleted_at', None)
        
        # Try to get relationship data if loaded
        org_name = None
        dept_name = None
        
        # Check if organization is loaded and accessible
        try:
            if hasattr(user, 'organization') and user.organization is not None:
                org_name = user.organization.name
        except Exception:
            # If lazy loading fails, just skip it
            pass
            
        try:
            if hasattr(user, 'department') and user.department is not None:
                dept_name = user.department.name
        except Exception:
            # If lazy loading fails, just skip it
            pass
        
        # Compute derived fields
        full_name = ""
        if data.get('first_name'):
            full_name = data['first_name']
        if data.get('last_name'):
            if full_name:
                full_name = f"{full_name} {data['last_name']}"
            else:
                full_name = data['last_name']
        if not full_name:
            full_name = data.get('email', '')
            
        # Compute is_active
        is_active = data.get('deleted_at') is None
        locked_until = getattr(user, 'locked_until', None)
        if is_active and locked_until:
            is_active = locked_until < datetime.utcnow()
        
        # Compute admin and vendor flags
        role = data.get('role', '')
        is_admin = role in ['super_admin', 'org_admin', 'vendor_admin', 'clinical_admin']
        is_vendor = role in ['vendor_admin', 'vendor_rep']
        
        # Add computed fields to data
        data['organization_name'] = org_name
        data['department_name'] = dept_name
        data['full_name'] = full_name
        data['is_active'] = is_active
        data['is_admin'] = is_admin
        data['is_vendor'] = is_vendor
        
        return cls(**data)

class UserList(BaseSchema):
    """List of users"""
    users: List[UserResponse]
    total: int

# Authentication schemas
class Token(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int

class TokenData(BaseModel):
    """Token payload data"""
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
    org_id: Optional[int] = None

class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr
    password: str
    mfa_token: Optional[str] = None

class LoginResponse(Token):
    """Login response with user data"""
    user: UserResponse

class PasswordChange(BaseModel):
    """Password change request"""
    current_password: str
    new_password: str = Field(..., min_length=8)
    
    @field_validator('new_password')
    def validate_new_password(cls, v, values):
        # Same validation as UserCreate
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v

class PasswordReset(BaseModel):
    """Password reset request"""
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    """Password reset confirmation"""
    token: str
    new_password: str = Field(..., min_length=8)

class MFAEnable(BaseModel):
    """MFA enable request"""
    password: str
    
class MFAEnableResponse(BaseModel):
    """MFA enable response"""
    secret: str
    qr_code: str
    backup_codes: List[str]

class MFAVerify(BaseModel):
    """MFA verification"""
    token: str

class EmailVerification(BaseModel):
    """Email verification request"""
    token: str

# Role management schemas
class RoleUpdate(BaseModel):
    """Update user role"""
    role: str
    
    @field_validator('role')
    def validate_role(cls, v):
        if v not in VALID_ROLES:
            raise ValueError(f'Invalid role. Must be one of: {", ".join(VALID_ROLES)}')
        return v
