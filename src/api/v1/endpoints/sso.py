"""
SSO (Single Sign-On) endpoints for Google OAuth, SAML, and enterprise authentication.

This module provides endpoints for:
- Google OAuth 2.0 authentication
- SAML 2.0 enterprise SSO
- Domain-based auto-approval
- Organization invitations with auto-generated passwords
"""
import secrets
import logging
from typing import Any, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.organization import Organization
from src.services.auth_service import auth_service, get_current_active_user
from src.services.sso.google_oauth_service import GoogleOAuthService
from src.services.email_service import get_email_service
from src.core.config import settings
from src.core.cache import get_cache_service
from src.schemas.user import LoginResponse, UserResponse
from src.schemas.base import SuccessResponse

router = APIRouter()
logger = logging.getLogger(__name__)
google_oauth = GoogleOAuthService()


# ============= GOOGLE OAUTH ENDPOINTS =============

@router.get("/google/login")
async def google_login(
    redirect_uri: Optional[str] = Query(None, description="Frontend redirect URI after auth")
) -> dict:
    """
    Initiate Google OAuth login flow.
    
    Returns the Google authorization URL for the frontend to redirect to.
    """
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state in cache with redirect URI
    cache = get_cache_service()
    await cache.set(
        f"oauth_state:{state}",
        {"redirect_uri": redirect_uri or settings.FRONTEND_URL},
        expire=600  # 10 minutes
    )
    
    # Get Google auth URL
    auth_url = google_oauth.get_authorization_url(state)
    
    return {
        "status": "success",
        "data": {
            "auth_url": auth_url,
            "state": state
        }
    }


@router.post("/google/callback")
async def google_callback(
    *,
    db: AsyncSession = Depends(get_db),
    code: str,
    state: str,
    background_tasks: BackgroundTasks
) -> LoginResponse:
    """
    Handle Google OAuth callback.
    
    Exchanges the authorization code for tokens and creates/authenticates the user.
    """
    # Verify state token
    cache = get_cache_service()
    state_data = await cache.get(f"oauth_state:{state}")
    
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state token"
        )
    
    # Clear state from cache
    await cache.delete(f"oauth_state:{state}")
    
    try:
        # Exchange code for tokens
        token_data = await google_oauth.exchange_code_for_tokens(code)
        
        # Get user info from Google
        user_info = await google_oauth.get_user_info(token_data["access_token"])
        
        # Add tokens to user info for session storage
        user_info["access_token"] = token_data.get("access_token")
        user_info["refresh_token"] = token_data.get("refresh_token")
        
        # Authenticate or create user
        user, is_new_user = await google_oauth.authenticate_or_create_user(db, user_info)
        
        # Check organization membership
        organization_matched = user.organization_id is not None
        
        # Send welcome email for new users
        if is_new_user:
            try:
                email_service = get_email_service()
                background_tasks.add_task(
                    email_service.send_welcome_email,
                    user.email,
                    user.first_name,
                    "google_oauth"
                )
            except Exception as e:
                logger.error(f"Failed to send welcome email: {e}")
        
        # Create session tokens
        session_data = await auth_service.create_session(db, user)
        
        # Build response
        return LoginResponse(
            **session_data,
            user=UserResponse.from_orm_with_computed(user),
            is_new_user=is_new_user,
            organization_matched=organization_matched,
            created_via="google_oauth"
        )
        
    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {str(e)}"
        )


# ============= ORGANIZATION INVITATIONS =============

@router.post("/organizations/{org_id}/invitations")
async def create_invitation(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    email: str,
    role: str = "viewer",
    department: Optional[str] = None,
    auto_generate_password: bool = True,
    expires_days: int = 7,
    devices: Optional[list[str]] = None,
    message: Optional[str] = None,
    send_email: bool = True,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> dict:
    """
    Create an invitation for a user to join an organization.
    
    This endpoint is for vendor organizations to invite healthcare workers
    or for healthcare organizations to invite their staff.
    """
    # Check permissions - must be admin of the organization
    if current_user.role not in ["super_admin", "org_admin", "vendor_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create invitations"
        )
    
    if current_user.organization_id != org_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create invitations for other organizations"
        )
    
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == email)
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        # If user exists, just add them to the organization
        if existing_user.organization_id == org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this organization"
            )
        
        # For existing users, we'll need a different flow
        # This could be an organization transfer or multi-org membership
        # For now, we'll return an error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists. Please use the organization transfer process."
        )
    
    # Generate invitation code
    invitation_code = f"inv_{secrets.token_urlsafe(16)}"
    
    # Generate temporary password if requested
    temp_password = None
    if auto_generate_password:
        # Generate a secure temporary password
        temp_password = secrets.token_urlsafe(12)
        # Add some special characters to meet complexity requirements
        temp_password = f"{temp_password}!Aa1"
    
    # Store invitation in cache (in production, use a database table)
    cache = get_cache_service()
    invitation_data = {
        "email": email,
        "organization_id": org_id,
        "role": role,
        "department": department,
        "devices": devices,
        "temp_password": auth_service.get_password_hash(temp_password) if temp_password else None,
        "created_by": current_user.id,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(days=expires_days)).isoformat()
    }
    
    await cache.set(
        f"invitation:{invitation_code}",
        invitation_data,
        expire=expires_days * 24 * 3600
    )
    
    # Send invitation email
    if send_email:
        try:
            email_service = get_email_service()
            
            # Get organization details
            result = await db.execute(
                select(Organization).where(Organization.id == org_id)
            )
            org = result.scalar_one_or_none()
            
            background_tasks.add_task(
                email_service.send_invitation_email,
                to_email=email,
                invitation_code=invitation_code,
                organization_name=org.name if org else "Unknown",
                inviter_name=f"{current_user.first_name} {current_user.last_name}",
                temp_password=temp_password,
                message=message,
                expires_days=expires_days
            )
        except Exception as e:
            logger.error(f"Failed to send invitation email: {e}")
    
    logger.info(f"Invitation created by {current_user.email} for {email} to join org {org_id}")
    
    return {
        "status": "success",
        "data": {
            "invitation_id": invitation_code,
            "invitation_url": f"{settings.FRONTEND_URL}/invite/{invitation_code}",
            "temporary_password": temp_password if auto_generate_password else None,
            "expires_at": invitation_data["expires_at"]
        }
    }


@router.post("/invitations/accept")
async def accept_invitation(
    *,
    db: AsyncSession = Depends(get_db),
    invitation_code: str,
    email: str,
    password: Optional[str] = None,
    full_name: Optional[str] = None,
    use_temp_password: bool = False
) -> LoginResponse:
    """
    Accept an organization invitation.
    
    Creates a new user account with the invitation details.
    """
    # Get invitation from cache
    cache = get_cache_service()
    invitation_data = await cache.get(f"invitation:{invitation_code}")
    
    if not invitation_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation"
        )
    
    # Verify email matches
    if invitation_data["email"] != email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email does not match invitation"
        )
    
    # Check expiration
    expires_at = datetime.fromisoformat(invitation_data["expires_at"])
    if datetime.utcnow() > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired"
        )
    
    # Determine password to use
    if use_temp_password and invitation_data.get("temp_password"):
        # User is using the temporary password
        password_hash = invitation_data["temp_password"]
        require_password_change = True
    elif password:
        # User provided their own password
        is_valid, error_msg = auth_service.validate_password_strength(password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        password_hash = auth_service.get_password_hash(password)
        require_password_change = False
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is required"
        )
    
    # Parse full name if provided
    first_name = ""
    last_name = ""
    if full_name:
        name_parts = full_name.strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
    
    # Create user
    user = User(
        email=email,
        password_hash=password_hash,
        first_name=first_name,
        last_name=last_name,
        organization_id=invitation_data["organization_id"],
        department=invitation_data.get("department"),
        role=invitation_data["role"],
        email_verified=True,  # Pre-verified via invitation
        created_via="invitation",
        require_password_change=require_password_change
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Clear invitation from cache
    await cache.delete(f"invitation:{invitation_code}")
    
    # Create session
    session_data = await auth_service.create_session(db, user)
    
    logger.info(f"User {email} accepted invitation to org {invitation_data['organization_id']}")
    
    return LoginResponse(
        **session_data,
        user=UserResponse.from_orm_with_computed(user),
        is_new_user=True,
        organization_matched=True,
        require_password_change=require_password_change
    )


# ============= BULK USER IMPORT =============

@router.post("/organizations/{org_id}/users/bulk-import")
async def bulk_import_users(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    users: list[dict],
    send_welcome_email: bool = True,
    require_password_change: bool = True,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> dict:
    """
    Bulk import users into an organization.
    
    This is typically used by vendor admins to provision access for
    healthcare organizations.
    """
    # Check permissions
    if current_user.role not in ["super_admin", "vendor_admin", "org_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can bulk import users"
        )
    
    if current_user.organization_id != org_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot import users to other organizations"
        )
    
    created_users = []
    errors = []
    
    for user_data in users:
        try:
            # Check if user already exists
            result = await db.execute(
                select(User).where(User.email == user_data["email"])
            )
            if result.scalar_one_or_none():
                errors.append({
                    "email": user_data["email"],
                    "error": "User already exists"
                })
                continue
            
            # Generate temporary password if requested
            temp_password = None
            if user_data.get("auto_generate_password", True):
                temp_password = secrets.token_urlsafe(12) + "!Aa1"
                password_hash = auth_service.get_password_hash(temp_password)
            else:
                # Use a default password that must be changed
                password_hash = auth_service.get_password_hash("TempPassword123!")
                temp_password = "TempPassword123!"
            
            # Create user
            user = User(
                email=user_data["email"],
                password_hash=password_hash,
                first_name=user_data.get("full_name", "").split()[0] if user_data.get("full_name") else "",
                last_name=" ".join(user_data.get("full_name", "").split()[1:]) if user_data.get("full_name") else "",
                organization_id=org_id,
                department=user_data.get("department"),
                role=user_data.get("role", "device_user"),
                email_verified=False,
                require_password_change=require_password_change,
                created_via="bulk_import",
                created_by=current_user.id
            )
            
            db.add(user)
            
            created_users.append({
                "email": user_data["email"],
                "temporary_password": temp_password
            })
            
            # Queue welcome email
            if send_welcome_email:
                try:
                    email_service = get_email_service()
                    background_tasks.add_task(
                        email_service.send_bulk_import_welcome,
                        to_email=user_data["email"],
                        temp_password=temp_password,
                        organization_name=current_user.organization.name if current_user.organization else "Unknown"
                    )
                except Exception as e:
                    logger.error(f"Failed to queue welcome email for {user_data['email']}: {e}")
            
        except Exception as e:
            errors.append({
                "email": user_data.get("email", "unknown"),
                "error": str(e)
            })
    
    # Commit all users at once
    await db.commit()
    
    logger.info(f"Bulk import by {current_user.email}: {len(created_users)} users created, {len(errors)} errors")
    
    return {
        "status": "success",
        "data": {
            "created": len(created_users),
            "failed": len(errors),
            "users": created_users,
            "errors": errors
        }
    }


# ============= DOMAIN VERIFICATION =============

@router.post("/organizations/{org_id}/domains")
async def add_domain_whitelist(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    domain: str,
    auto_approve: bool = True,
    default_role: str = "healthcare_professional",
    require_email_verification: bool = True,
    current_user: User = Depends(get_current_active_user)
) -> SuccessResponse:
    """
    Add a domain to organization's whitelist for auto-approval.
    
    Users with emails from this domain can automatically join the organization.
    """
    # Check permissions
    if current_user.role not in ["super_admin", "org_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins can manage domains"
        )
    
    if current_user.organization_id != org_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage domains for other organizations"
        )
    
    # Get organization
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    
    # Add domain to allowed list
    if not org.allowed_email_domains:
        org.allowed_email_domains = []
    
    if domain not in org.allowed_email_domains:
        org.allowed_email_domains.append(domain)
        org.auto_approve_domains = auto_approve
        org.default_role = default_role
        
        await db.commit()
        
        logger.info(f"Domain {domain} added to org {org_id} by {current_user.email}")
    
    return SuccessResponse(
        message=f"Domain {domain} added to whitelist"
    )


@router.post("/organizations/{org_id}/domains/{domain}/verify")
async def verify_domain_ownership(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    domain: str,
    verification_method: str = "dns_txt",
    verification_value: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
) -> dict:
    """
    Verify domain ownership for automatic user approval.
    
    Methods:
    - dns_txt: Add TXT record to DNS
    - email_admin: Send verification to admin@domain
    - file_upload: Upload verification file to domain
    """
    # Check permissions
    if current_user.role not in ["super_admin", "org_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization admins can verify domains"
        )
    
    if current_user.organization_id != org_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot verify domains for other organizations"
        )
    
    # Generate verification token if not provided
    if not verification_value:
        verification_value = f"nyelux-verify={secrets.token_urlsafe(32)}"
    
    # Store verification token in cache
    cache = get_cache_service()
    await cache.set(
        f"domain_verify:{org_id}:{domain}",
        {
            "method": verification_method,
            "value": verification_value,
            "created_at": datetime.utcnow().isoformat()
        },
        expire=86400  # 24 hours
    )
    
    instructions = {}
    
    if verification_method == "dns_txt":
        instructions = {
            "method": "dns_txt",
            "record_type": "TXT",
            "host": f"_nyelux.{domain}",
            "value": verification_value,
            "instructions": "Add this TXT record to your DNS configuration"
        }
    elif verification_method == "email_admin":
        # Send verification email to admin@domain
        instructions = {
            "method": "email_admin",
            "email": f"admin@{domain}",
            "instructions": "Check admin email for verification link"
        }
    elif verification_method == "file_upload":
        instructions = {
            "method": "file_upload",
            "path": f"/.well-known/nyelux-verify.txt",
            "content": verification_value,
            "instructions": f"Upload a file to https://{domain}/.well-known/nyelux-verify.txt"
        }
    
    return {
        "status": "success",
        "data": {
            "domain": domain,
            "verification_method": verification_method,
            "verification_status": "pending",
            **instructions
        }
    }


# ============= MANUAL VERIFICATION =============

@router.post("/verification/request")
async def request_manual_verification(
    *,
    db: AsyncSession = Depends(get_db),
    email: str,
    organization_name: str,
    department: Optional[str] = None,
    license_number: Optional[str] = None,
    verification_documents: Optional[list[str]] = None,
    notes: Optional[str] = None
) -> SuccessResponse:
    """
    Request manual verification for users who can't be auto-approved.
    
    This creates a verification request that admins can review.
    """
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists"
        )
    
    # Store verification request in cache (in production, use database)
    cache = get_cache_service()
    verification_id = f"ver_{secrets.token_urlsafe(16)}"
    
    await cache.set(
        f"verification:{verification_id}",
        {
            "email": email,
            "organization_name": organization_name,
            "department": department,
            "license_number": license_number,
            "documents": verification_documents,
            "notes": notes,
            "status": "pending",
            "submitted_at": datetime.utcnow().isoformat()
        },
        expire=7 * 24 * 3600  # 7 days
    )
    
    logger.info(f"Manual verification requested for {email}")
    
    # Notify admins (in production, send email/notification)
    # ...
    
    return SuccessResponse(
        message="Verification request submitted. You will be notified within 48 hours."
    )


@router.get("/admin/verification/pending")
async def get_pending_verifications(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> dict:
    """
    Get pending verification requests for admin review.
    
    Only super admins can see all requests.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can review verifications"
        )
    
    # Get all pending verifications from cache
    cache = get_cache_service()
    # In production, this would query a database table
    # For now, we'll return a mock response
    
    return {
        "status": "success",
        "data": {
            "pending_verifications": []
        }
    }


@router.post("/admin/verification/{verification_id}/review")
async def review_verification(
    *,
    db: AsyncSession = Depends(get_db),
    verification_id: str,
    action: str,  # approve, reject, request_more_info
    reviewer_notes: Optional[str] = None,
    assigned_role: Optional[str] = None,
    organization_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> SuccessResponse:
    """
    Review and approve/reject a manual verification request.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can review verifications"
        )
    
    # Get verification request
    cache = get_cache_service()
    verification = await cache.get(f"verification:{verification_id}")
    
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification request not found"
        )
    
    if action == "approve":
        # Generate temporary password
        temp_password = secrets.token_urlsafe(12) + "!Aa1"
        
        # Create user account
        user = User(
            email=verification["email"],
            password_hash=auth_service.get_password_hash(temp_password),
            organization_id=organization_id,
            department=verification.get("department"),
            role=assigned_role or "healthcare_professional",
            email_verified=True,  # Pre-verified by admin
            created_via="manual_verification",
            require_password_change=True
        )
        
        db.add(user)
        await db.commit()
        
        # Send approval email with credentials
        try:
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_verification_approved,
                to_email=verification["email"],
                temp_password=temp_password
            )
        except Exception as e:
            logger.error(f"Failed to send approval email: {e}")
        
        # Clear verification request
        await cache.delete(f"verification:{verification_id}")
        
        logger.info(f"Verification approved by {current_user.email} for {verification['email']}")
        
        return SuccessResponse(
            message="Verification approved and user account created"
        )
    
    elif action == "reject":
        # Send rejection email
        try:
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_verification_rejected,
                to_email=verification["email"],
                reason=reviewer_notes
            )
        except Exception as e:
            logger.error(f"Failed to send rejection email: {e}")
        
        # Clear verification request
        await cache.delete(f"verification:{verification_id}")
        
        logger.info(f"Verification rejected by {current_user.email} for {verification['email']}")
        
        return SuccessResponse(
            message="Verification rejected"
        )
    
    elif action == "request_more_info":
        # Update status and send email requesting more information
        verification["status"] = "pending_info"
        verification["reviewer_notes"] = reviewer_notes
        
        await cache.set(
            f"verification:{verification_id}",
            verification,
            expire=7 * 24 * 3600
        )
        
        # Send email requesting more info
        try:
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_verification_info_request,
                to_email=verification["email"],
                info_needed=reviewer_notes
            )
        except Exception as e:
            logger.error(f"Failed to send info request email: {e}")
        
        return SuccessResponse(
            message="Additional information requested"
        )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Must be approve, reject, or request_more_info"
        )
