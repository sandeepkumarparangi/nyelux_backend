"""
Authentication schemas for request/response validation.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

from src.schemas.base import BaseSchema


# Token schemas
class Token(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None


class TokenData(BaseModel):
    """JWT token payload data"""
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
    organization_id: Optional[int] = None
    exp: Optional[datetime] = None


class TokenRefresh(BaseModel):
    """Token refresh request"""
    refresh_token: str


# Login schemas
class LoginRequest(BaseModel):
    """Login request with email/password"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    remember_me: Optional[bool] = False


class LoginResponse(BaseModel):
    """Login response with token and user info"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    user: Dict[str, Any]
    requires_mfa: Optional[bool] = False
    mfa_token: Optional[str] = None


# Registration schemas
class UserCreate(BaseModel):
    """User registration request"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    organization_id: Optional[int] = None
    department_id: Optional[int] = None
    role: str = Field(..., pattern="^(nurse|physician|technician|org_admin|vendor_rep)$")
    title: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, pattern=r"^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$")
    invitation_code: Optional[str] = None
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Ensure password meets complexity requirements"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one number')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(char in "!@#$%^&*()_+-=[]{}|;:,.<>?" for char in v):
            raise ValueError('Password must contain at least one special character')
        return v


class UserResponse(BaseModel):
    """User response after registration"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    organization_id: Optional[int]
    department_id: Optional[int]
    title: Optional[str]
    email_verified: bool
    mfa_enabled: bool
    created_at: datetime


# Password reset schemas
class PasswordResetRequest(BaseModel):
    """Request password reset"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Confirm password reset with token"""
    token: str
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v


class PasswordChange(BaseModel):
    """Change password for authenticated user"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str
    
    @field_validator('confirm_password')
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Passwords do not match')
        return v


# Email verification schemas
class EmailVerificationRequest(BaseModel):
    """Request email verification resend"""
    email: EmailStr


class EmailVerificationConfirm(BaseModel):
    """Confirm email with token"""
    token: str


# MFA schemas
class MFAEnableRequest(BaseModel):
    """Request to enable MFA"""
    password: str  # Require password confirmation
    method: str = Field("totp", pattern="^(totp|sms)$")
    phone: Optional[str] = None  # Required if method is SMS


class MFAEnableResponse(BaseModel):
    """MFA enable response with QR code"""
    method: str
    secret: Optional[str] = None  # For TOTP
    qr_code: Optional[str] = None  # Base64 encoded QR image
    backup_codes: Optional[list[str]] = None
    phone: Optional[str] = None  # For SMS


class MFAVerifyRequest(BaseModel):
    """Verify MFA code"""
    code: str = Field(..., min_length=6, max_length=6)
    mfa_token: Optional[str] = None  # From login response


class MFADisableRequest(BaseModel):
    """Disable MFA"""
    password: str
    code: str = Field(..., min_length=6, max_length=6)


# SSO schemas
class SSOLoginRequest(BaseModel):
    """SSO login request"""
    provider: str = Field(..., pattern="^(okta|azure|google|saml)$")
    redirect_uri: Optional[str] = None


class SSOCallbackRequest(BaseModel):
    """SSO callback with assertion"""
    provider: str
    code: Optional[str] = None  # For OAuth providers
    saml_response: Optional[str] = None  # For SAML
    state: Optional[str] = None


# Session schemas
class SessionInfo(BaseModel):
    """Current session information"""
    user_id: int
    email: str
    role: str
    organization_id: Optional[int]
    organization_name: Optional[str]
    permissions: list[str]
    session_id: str
    expires_at: datetime
    last_activity: datetime
    login_ip: Optional[str]
    user_agent: Optional[str]


class ActiveSession(BaseModel):
    """Active session for session management"""
    session_id: str
    device_name: str
    ip_address: str
    location: Optional[str]
    last_activity: datetime
    is_current: bool


# API Key schemas
class APIKeyCreate(BaseModel):
    """Create API key request"""
    name: str = Field(..., min_length=3, max_length=100)
    scopes: list[str] = Field(..., min_length=1)
    expires_at: Optional[datetime] = None


class APIKeyResponse(BaseModel):
    """API key response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    key: Optional[str] = None  # Only shown on creation
    key_prefix: str
    scopes: list[str]
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime


# Permission schemas
class Permission(BaseModel):
    """Permission definition"""
    resource: str
    action: str
    scope: Optional[str] = None  # organization, department, team, own


class RolePermissions(BaseModel):
    """Role with permissions"""
    role: str
    permissions: list[Permission]
    description: str
