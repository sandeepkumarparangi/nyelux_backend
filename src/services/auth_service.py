from datetime import datetime, timedelta
from typing import Optional, Union, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import secrets
import string
import logging
import pyotp

from src.core.config import settings
from src.core.exceptions import AuthenticationError, AuthorizationError
from src.db.models.user import User
from src.db.session import get_db

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

class AuthService:
    """
    Production-ready authentication service.
    Handles password hashing, JWT tokens, MFA, and session management.
    """
    
    def __init__(self):
        # Use uppercase attribute names to match test expectations
        self.SECRET_KEY = settings.SECRET_KEY
        self.ALGORITHM = settings.ALGORITHM
        self.ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        
        # Also keep lowercase for internal use
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    
    # Password Management
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    def get_password_hash(self, password: str) -> str:
        """Generate password hash"""
        return pwd_context.hash(password)
    
    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """
        Validate password meets security requirements.
        Returns (is_valid, error_message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"
        
        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"
        
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one number"
        
        if not any(c in string.punctuation for c in password):
            return False, "Password must contain at least one special character"
        
        # Check against common passwords (in production, use a comprehensive list)
        common_passwords = ["password", "12345678", "qwerty", "abc123"]
        if password.lower() in common_passwords:
            return False, "Password is too common"
        
        return True, ""
    
    # Token Management
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire, "type": "access"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=7)  # 7 day refresh token
        to_encode.update({"exp": expire, "type": "refresh"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_email_verification_token(self, email: str) -> str:
        """Create email verification token"""
        data = {"email": email, "purpose": "email_verification"}
        return self.create_access_token(data, expires_delta=timedelta(hours=24))
    
    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            logger.error(f"JWT decode error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # User Authentication
    async def authenticate_user(
        self, 
        db: AsyncSession, 
        email: str, 
        password: str
    ) -> Optional[User]:
        """
        Authenticate user with email and password.
        Implements account lockout protection.
        Returns None for failed authentication (doesn't raise exception for lockout).
        """
        # Get user from database without eager loading relationships
        # to avoid async context issues
        result = await db.execute(
            select(User)
            .where(
                and_(
                    User.email == email,
                    User.deleted_at.is_(None)
                )
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"Login attempt for non-existent user: {email}")
            return None
        
        # Check if account is locked - return None instead of raising exception
        if user.locked_until and user.locked_until > datetime.utcnow():
            logger.warning(f"Login attempt on locked account: {email}")
            return None
        
        # Verify password
        if not self.verify_password(password, user.password_hash):
            # Increment failed attempts
            user.failed_login_attempts += 1
            
            # Lock account after 5 failed attempts
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                logger.warning(f"Account locked due to failed attempts: {email}")
            
            await db.commit()
            return None
        
        # Successful login - reset failed attempts
        user.failed_login_attempts = 0
        user.last_login_at = datetime.utcnow()
        user.last_activity_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"Successful login for user: {email}")
        return user
    
    async def get_current_user(
        self, 
        db: AsyncSession, 
        token: str
    ) -> User:
        """
        Get current user from JWT token.
        Raises HTTPException if invalid.
        """
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception
        
        # Get user from database
        result = await db.execute(
            select(User).where(
                and_(
                    User.id == int(user_id),
                    User.deleted_at.is_(None)
                )
            )
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            raise credentials_exception
        
        # Update last activity
        user.last_activity_at = datetime.utcnow()
        await db.commit()
        
        return user
    
    async def verify_email_token(
        self,
        db: AsyncSession,
        token: str
    ) -> bool:
        """
        Verify email verification token and mark email as verified.
        Returns True if successful, False otherwise.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            email = payload.get("email")
            purpose = payload.get("purpose")
            
            if not email or purpose != "email_verification":
                return False
            
            # Find user by email
            result = await db.execute(
                select(User).where(
                    and_(
                        User.email == email,
                        User.deleted_at.is_(None)
                    )
                )
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return False
            
            # Mark email as verified
            user.email_verified = True
            await db.commit()
            
            logger.info(f"Email verified for user: {email}")
            return True
            
        except JWTError:
            logger.error(f"Invalid email verification token")
            return False
    
    # MFA Management
    def generate_mfa_secret(self) -> str:
        """Generate MFA secret for user"""
        return pyotp.random_base32()
    
    def get_mfa_uri(self, email: str, secret: str) -> str:
        """Get MFA provisioning URI for QR code"""
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=email,
            issuer_name='Nyelux Medical'
        )
    
    def verify_mfa_token(self, secret: str, token: str) -> bool:
        """Verify MFA token"""
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)  # Allow 30 second window
    
    def generate_backup_codes(self, count: int = 8) -> list[str]:
        """Generate MFA backup codes"""
        codes = []
        for _ in range(count):
            code = ''.join(secrets.choice(string.digits) for _ in range(8))
            codes.append(f"{code[:4]}-{code[4:]}")  # Format: XXXX-XXXX
        return codes
    
    # Session Management
    async def create_session(
        self, 
        db: AsyncSession, 
        user: User,
        device_info: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """Create user session with tokens"""
        # Create token payload
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "org_id": user.organization_id
        }
        
        # Generate tokens
        access_token = self.create_access_token(token_data)
        refresh_token = self.create_refresh_token(token_data)
        
        # Update user last activity
        user.last_activity_at = datetime.utcnow()
        await db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60
        }
    
    # Token Generation
    def generate_reset_token(self) -> str:
        """Generate secure password reset token"""
        return secrets.token_urlsafe(32)
    
    async def create_password_reset(
        self, 
        db: AsyncSession, 
        user: User
    ) -> str:
        """Create password reset token for user"""
        token = self.generate_reset_token()
        
        user.password_reset_token = token
        user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        
        await db.commit()
        
        logger.info(f"Password reset requested for user: {user.email}")
        return token
    
    async def reset_password(
        self,
        db: AsyncSession,
        token: str,
        new_password: str
    ) -> bool:
        """
        Reset user password with token.
        Returns True if successful, False if token is invalid/expired.
        """
        # Find user with valid token
        result = await db.execute(
            select(User).where(
                and_(
                    User.password_reset_token == token,
                    User.deleted_at.is_(None)
                )
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"Invalid password reset token attempted")
            return False
        
        # Check if token is expired
        if user.password_reset_expires and user.password_reset_expires < datetime.utcnow():
            logger.warning(f"Expired password reset token for user: {user.email}")
            return False
        
        # Update password
        user.password_hash = self.get_password_hash(new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        user.failed_login_attempts = 0
        user.locked_until = None
        
        await db.commit()
        
        logger.info(f"Password reset successful for user: {user.email}")
        return True

# Create a function to get auth service instance
def get_auth_service() -> AuthService:
    """
    Get auth service instance for dependency injection.
    
    Returns:
        AuthService instance
    """
    return AuthService()

# For backward compatibility, create a default instance
# This should be replaced with dependency injection in all endpoints
auth_service = AuthService()

# Dependency functions
async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Get current authenticated user from JWT token.
    Raises HTTPException if invalid.
    """
    return await auth_service.get_current_user(db, token)

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Ensure user is active"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user"
        )
    
    # Only check email verification in production
    if settings.is_production() and not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified"
        )
    
    return current_user

# Role-based access control
def require_role(allowed_roles: list[str]):
    """
    Dependency to require specific roles.
    Usage: current_user = Depends(require_role(["admin", "vendor"]))
    """
    async def role_checker(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' not authorized. "
                       f"Required roles: {', '.join(allowed_roles)}"
            )
        return current_user
    
    return role_checker

# Convenience dependencies
require_admin = require_role(["super_admin", "org_admin"])
require_vendor = require_role(["vendor_admin", "vendor_rep"])
require_healthcare = require_role(["physician", "nurse", "technician"])
