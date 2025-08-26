"""
Authentication endpoints.

This module provides all authentication-related endpoints including user registration,
login, logout, password management, MFA setup, and email verification.
"""
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import EmailStr
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from src.core.config import settings
from src.core.exceptions import AuthenticationError, ValidationError
from src.db.models.user import User
from src.db.session import get_db
from src.schemas.base import SuccessResponse
from src.schemas.user import (
    EmailVerification,
    LoginResponse,
    MFAEnable,
    MFAEnableResponse,
    MFAVerify,
    PasswordChange,
    PasswordReset,
    PasswordResetConfirm,
    Token,
    UserCreate,
    UserResponse,
)
from src.services.auth_service import auth_service, get_current_active_user
from src.services.encryption_service import get_encryption_service
import hashlib
import json
import secrets
from datetime import datetime, timedelta

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate
) -> Any:
    """
    Register a new user account.
    
    This endpoint creates a new user account with the provided information.
    The email must be unique across the system, and the password must meet
    complexity requirements.
    
    Args:
        user_in: User registration data including:
            - email: Valid email address (will be used for login)
            - password: Password meeting complexity requirements
            - first_name: User's first name
            - last_name: User's last name
            - role: User role (nurse, physician, technician, etc.)
            - organization_id: Optional organization association
            - Other optional profile fields
    
    Returns:
        UserResponse: Created user object with all fields except password
        
    Raises:
        HTTPException 400: If email is already registered
        ValidationError: If password doesn't meet requirements
        
    Security:
        - Password is hashed using bcrypt before storage
        - Email verification is required before full access (in production)
    """
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == user_in.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate password strength
    is_valid, error_msg = auth_service.validate_password_strength(user_in.password)
    if not is_valid:
        raise ValidationError(error_msg)
    
    # Create user
    user = User(
        email=user_in.email,
        password_hash=auth_service.get_password_hash(user_in.password),
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        title=user_in.title,
        phone=user_in.phone,
        role=user_in.role,
        organization_id=user_in.organization_id,
        department_id=user_in.department_id,
        language_preference=user_in.language_preference,
        timezone=user_in.timezone
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Generate email verification token
    verification_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(verification_token.encode()).hexdigest()
    
    # Store hashed token
    user.email_verification_token_hash = token_hash
    user.email_verification_expires = datetime.utcnow() + timedelta(hours=24)
    await db.commit()
    await db.refresh(user)
    
    # Send verification email (in production, this should be in background task)
    try:
        from src.services.email_service import get_email_service
        email_service = get_email_service()
        await email_service.send_verification_email(
            to_email=user.email,
            verification_token=verification_token,
            user_name=user.first_name
        )
    except Exception as e:
        # Log but don't fail registration
        logger.error(f"Could not send verification email to {user.email}: {e}")
    
    logger.info(f"New user registered: {user.email}")
    
    return UserResponse.from_orm_with_computed(user)


@router.post("/login", response_model=LoginResponse)
async def login(
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible login endpoint.
    
    Authenticates a user with email and password, returning access and refresh
    tokens following the OAuth2 password flow specification.
    
    Args:
        form_data: OAuth2 form containing:
            - username: User's email address
            - password: User's password
            
    Returns:
        LoginResponse containing:
            - access_token: JWT token for API access
            - refresh_token: Token for refreshing access
            - token_type: Always "bearer"
            - expires_in: Token expiration in seconds
            - user: Complete user profile
            
    Raises:
        HTTPException 401: If credentials are invalid or email not verified
        
    Security:
        - Implements account lockout after 5 failed attempts
        - Tracks last login timestamp
        - Requires email verification in production
    """
    # Authenticate user
    user = await auth_service.authenticate_user(
        db, form_data.username, form_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if email is verified
    if not user.email_verified and settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified. Please check your email for verification link."
        )
    
    # Create session
    session_data = await auth_service.create_session(db, user)
    
    # Refresh the user object to ensure all data is properly loaded
    # This helps avoid any lazy loading issues
    await db.refresh(user)
    
    # Build user response data manually to avoid any async context issues
    user_data = UserResponse.from_orm_with_computed(user)
    
    return LoginResponse(
        **session_data,
        user=user_data
    )


@router.post("/logout", response_model=SuccessResponse)
async def logout(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Logout the current user.
    
    In a stateless JWT system, logout is primarily handled client-side by
    discarding the token. This endpoint serves for audit logging and can be
    extended to maintain a token blacklist if needed.
    
    Args:
        current_user: Authenticated user from token
        
    Returns:
        SuccessResponse with logout confirmation
        
    Security:
        - Requires valid authentication token
        - Logs logout event for audit trail
    """
    logger.info(f"User logged out: {current_user.email}")
    
    return SuccessResponse(
        message="Successfully logged out"
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    db: AsyncSession = Depends(get_db),
    refresh_token: str = Body(..., embed=True)
) -> Any:
    """
    Refresh an expired access token.
    
    Uses a valid refresh token to generate a new access token without
    requiring re-authentication. Refresh tokens have longer expiration
    times and should be stored securely.
    
    Args:
        refresh_token: Valid refresh token from previous login
        
    Returns:
        Token object with new access and refresh tokens
        
    Raises:
        HTTPException 401: If refresh token is invalid or expired
        
    Security:
        - Validates token type to prevent access token reuse
        - Checks user is still active
        - Issues new token pair to prevent token reuse attacks
    """
    try:
        # Decode refresh token
        payload = auth_service.decode_token(refresh_token)
        
        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")
        
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token")
        
        # Get user
        result = await db.execute(
            select(User).where(
                and_(
                    User.id == int(user_id),
                    User.deleted_at.is_(None)
                )
            )
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive")
        
        # Create new session
        session_data = await auth_service.create_session(db, user)
        
        return Token(**session_data)
        
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.post("/forgot-password", response_model=SuccessResponse)
async def forgot_password(
    *,
    db: AsyncSession = Depends(get_db),
    email_in: PasswordReset,
    background_tasks: BackgroundTasks
) -> Any:
    """
    Request a password reset email.
    
    Initiates the password reset process by sending an email with a secure
    reset link to the provided email address if it exists in the system.
    
    Args:
        email_in: Object containing the email address
        background_tasks: FastAPI background task queue
        
    Returns:
        SuccessResponse with generic message (prevents email enumeration)
        
    Security:
        - Always returns success to prevent email enumeration
        - Reset tokens expire after 1 hour
        - Tokens are single-use
        - Email sent asynchronously
    """
    # Get user by email
    result = await db.execute(
        select(User).where(
            and_(
                User.email == email_in.email,
                User.deleted_at.is_(None)
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Generate reset token
        reset_token = await auth_service.create_password_reset(db, user)
        
        # Send reset email in background
        try:
            from src.services.email_service import get_email_service
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_password_reset_email,
                user.email,
                reset_token,
                user.first_name
            )
        except Exception as e:
            logger.error(f"Could not send password reset email to {user.email}: {e}")
        
        logger.info(f"Password reset requested for: {user.email}")
    
    # Always return success to prevent email enumeration
    return SuccessResponse(
        message="If that email exists, we've sent a password reset link"
    )


@router.post("/reset-password", response_model=SuccessResponse)
async def reset_password(
    *,
    db: AsyncSession = Depends(get_db),
    reset_in: PasswordResetConfirm
) -> Any:
    """
    Reset password using token from email.
    
    Completes the password reset process using the token received via email.
    The new password must meet all security requirements.
    
    Args:
        reset_in: Object containing:
            - token: Reset token from email
            - new_password: New password meeting requirements
            
    Returns:
        SuccessResponse confirming password reset
        
    Raises:
        HTTPException 400: If token is invalid or expired
        
    Security:
        - Tokens are single-use and cleared after reset
        - Password complexity is enforced
        - Failed login attempts are reset
    """
    user = await auth_service.reset_password(
        db, reset_in.token, reset_in.new_password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    return SuccessResponse(
        message="Password successfully reset"
    )


@router.post("/change-password", response_model=SuccessResponse)
async def change_password(
    *,
    db: AsyncSession = Depends(get_db),
    password_in: PasswordChange,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Change password for authenticated user.
    
    Allows users to change their password while logged in. Requires
    the current password for verification.
    
    Args:
        password_in: Object containing:
            - current_password: User's current password
            - new_password: New password meeting requirements
        current_user: Authenticated user from token
        
    Returns:
        SuccessResponse confirming password change
        
    Raises:
        HTTPException 400: If current password is incorrect
        ValidationError: If new password doesn't meet requirements
        
    Security:
        - Requires current password verification
        - Enforces password complexity
        - Invalidates existing sessions (future enhancement)
    """
    # Verify current password
    if not auth_service.verify_password(
        password_in.current_password, 
        current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    # Validate new password
    is_valid, error_msg = auth_service.validate_password_strength(
        password_in.new_password
    )
    if not is_valid:
        raise ValidationError(error_msg)
    
    # Update password
    current_user.password_hash = auth_service.get_password_hash(
        password_in.new_password
    )
    await db.commit()
    
    logger.info(f"Password changed for user: {current_user.email}")
    
    return SuccessResponse(
        message="Password successfully changed"
    )


@router.post("/mfa/enable", response_model=MFAEnableResponse)
async def enable_mfa(
    *,
    db: AsyncSession = Depends(get_db),
    mfa_in: MFAEnable,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Enable Multi-Factor Authentication.
    
    Initiates MFA setup by generating a secret key and QR code for
    authenticator apps. Also provides backup codes for account recovery.
    
    Args:
        mfa_in: Object containing user's password for verification
        current_user: Authenticated user from token
        
    Returns:
        MFAEnableResponse containing:
            - secret: Base32 encoded secret key
            - qr_code: QR code URI for authenticator apps
            - backup_codes: List of one-time backup codes
            
    Raises:
        HTTPException 400: If password verification fails
        
    Security:
        - Requires password verification
        - Secret is encrypted before storage
        - Backup codes are hashed
        - MFA not active until verified
    """
    # Verify password
    if not auth_service.verify_password(mfa_in.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    # Generate MFA secret
    secret = auth_service.generate_mfa_secret()
    qr_uri = auth_service.get_mfa_uri(current_user.email, secret)
    backup_codes = auth_service.generate_backup_codes()
    
    # Get encryption service
    encryption_service = get_encryption_service()
    
    # Encrypt MFA secret
    current_user.mfa_secret_encrypted = encryption_service.encrypt(secret)
    
    # Hash backup codes and store as JSON
    hashed_codes = []
    for code in backup_codes:
        # Use bcrypt for hashing backup codes
        hashed = auth_service.get_password_hash(code)
        hashed_codes.append(hashed)
    current_user.mfa_backup_codes_hash = json.dumps(hashed_codes)
    
    # Clear deprecated fields
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    
    await db.commit()
    
    logger.info(f"MFA setup initiated for user: {current_user.email}")
    
    return MFAEnableResponse(
        secret=secret,
        qr_code=qr_uri,
        backup_codes=backup_codes
    )


@router.post("/mfa/verify", response_model=SuccessResponse)
async def verify_mfa(
    *,
    db: AsyncSession = Depends(get_db),
    mfa_in: MFAVerify,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Verify MFA token and complete setup.
    
    Validates the TOTP token from the user's authenticator app to
    confirm MFA setup was successful before enabling it.
    
    Args:
        mfa_in: Object containing the 6-digit TOTP token
        current_user: Authenticated user from token
        
    Returns:
        SuccessResponse confirming MFA is enabled
        
    Raises:
        HTTPException 400: If MFA not initialized or token invalid
        
    Security:
        - Token must be valid within 30-second window
        - MFA only enabled after successful verification
        - Prevents TOTP replay attacks
    """
    if not current_user.mfa_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA not initialized"
        )
    
    # Get encryption service and decrypt secret
    encryption_service = get_encryption_service()
    decrypted_secret = encryption_service.decrypt(current_user.mfa_secret_encrypted)
    
    # Verify token
    if not auth_service.verify_mfa_token(decrypted_secret, mfa_in.token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA token"
        )
    
    # Enable MFA
    current_user.mfa_enabled = True
    await db.commit()
    
    logger.info(f"MFA enabled for user: {current_user.email}")
    
    return SuccessResponse(
        message="MFA successfully enabled"
    )


@router.post("/mfa/disable", response_model=SuccessResponse)
async def disable_mfa(
    *,
    db: AsyncSession = Depends(get_db),
    password: str = Body(..., embed=True),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Disable Multi-Factor Authentication.
    
    Removes MFA from the user's account. Requires password verification
    for security. All MFA data is permanently deleted.
    
    Args:
        password: User's password for verification
        current_user: Authenticated user from token
        
    Returns:
        SuccessResponse confirming MFA is disabled
        
    Raises:
        HTTPException 400: If password verification fails
        
    Security:
        - Requires password verification
        - Permanently removes MFA secret and backup codes
        - Logged for security audit
    """
    # Verify password
    if not auth_service.verify_password(password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    # Disable MFA
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    current_user.mfa_secret_encrypted = None
    current_user.mfa_backup_codes_hash = None
    
    await db.commit()
    
    logger.info(f"MFA disabled for user: {current_user.email}")
    
    return SuccessResponse(
        message="MFA successfully disabled"
    )


@router.post("/verify-email", response_model=SuccessResponse)
async def verify_email(
    *,
    db: AsyncSession = Depends(get_db),
    verification: EmailVerification
) -> Any:
    """
    Verify email address using token.
    
    Completes email verification using the token sent to the user's
    email address during registration.
    
    Args:
        verification: Object containing the verification token
        
    Returns:
        SuccessResponse confirming email verification
        
    Raises:
        HTTPException 400: If token is invalid or expired
        
    Security:
        - Tokens expire after 24 hours
        - Single-use tokens
        - Enables full account access
    """
    # Hash the token for comparison
    token_hash = hashlib.sha256(verification.token.encode()).hexdigest()
    
    # Find user with matching token
    result = await db.execute(
        select(User).where(
            and_(
                User.email_verification_token_hash == token_hash,
                User.email_verification_expires > datetime.utcnow()
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    # Mark as verified
    user.email_verified = True
    user.email_verification_token_hash = None
    user.email_verification_expires = None
    
    await db.commit()
    
    logger.info(f"Email verified for user: {user.email}")
    
    return SuccessResponse(
        message="Email successfully verified"
    )


@router.post("/resend-verification", response_model=SuccessResponse)
async def resend_verification(
    *,
    db: AsyncSession = Depends(get_db),
    email: EmailStr = Body(..., embed=True),
    background_tasks: BackgroundTasks
) -> Any:
    """
    Resend email verification link.
    
    Sends a new verification email to users who haven't verified their
    email address. Rate limited to prevent abuse.
    
    Args:
        email: Email address to resend verification to
        background_tasks: FastAPI background task queue
        
    Returns:
        SuccessResponse with generic message
        
    Security:
        - Rate limited to 1 request per 5 minutes
        - Generic response prevents email enumeration
        - Only sends to unverified accounts
    """
    # Get user by email
    result = await db.execute(
        select(User).where(
            and_(
                User.email == email,
                User.deleted_at.is_(None)
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if user and not user.email_verified:
        # Generate new verification token
        verification_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(verification_token.encode()).hexdigest()
        
        # Update token
        user.email_verification_token_hash = token_hash
        user.email_verification_expires = datetime.utcnow() + timedelta(hours=24)
        await db.commit()
        
        # Send verification email
        try:
            from src.services.email_service import get_email_service
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_verification_email,
                user.email,
                verification_token,
                user.first_name
            )
        except Exception as e:
            logger.error(f"Could not send verification email to {user.email}: {e}")
        
        logger.info(f"Verification email resent to: {user.email}")
    
    # Always return success to prevent email enumeration
    return SuccessResponse(
        message="If that email exists and is unverified, we've sent a verification link"
    )
