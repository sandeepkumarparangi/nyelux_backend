"""
Vendor Organization Authentication & User Management

This module handles vendor-specific authentication features including:
- Automatic password generation for healthcare organizations
- Bulk user provisioning
- Domain-based auto-approval
- Organization transfer between vendors
"""
import secrets
import logging
from typing import Any, Optional, List
from datetime import datetime, timedelta
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from pydantic import BaseModel, EmailStr

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.organization import Organization
from src.services.auth_service import auth_service, get_current_active_user
from src.services.email_service import get_email_service
from src.core.config import settings
from src.core.cache import get_cache_service
from src.schemas.user import UserResponse
from src.schemas.base import SuccessResponse, PaginatedResponse

router = APIRouter()
logger = logging.getLogger(__name__)


# ============= SCHEMAS =============

class VendorUserProvision(BaseModel):
    """Schema for provisioning users with vendor access"""
    email: EmailStr
    full_name: str
    department: Optional[str] = None
    role: str = "device_user"
    devices: Optional[List[str]] = None  # List of device DIs
    access_level: str = "viewer"  # viewer, user, admin
    auto_generate_password: bool = True
    require_password_change: bool = True
    send_welcome_email: bool = True
    expires_at: Optional[datetime] = None


class BulkProvisionRequest(BaseModel):
    """Request for bulk user provisioning"""
    organization_id: int
    users: List[VendorUserProvision]
    send_summary_email: bool = True
    grant_immediate_access: bool = True


class OrganizationAccessGrant(BaseModel):
    """Grant access to vendor devices for an organization"""
    organization_id: int
    device_dis: Optional[List[str]] = None  # Specific devices or all
    access_type: str = "full"  # full, limited, trial
    expires_at: Optional[datetime] = None
    auto_provision_users: bool = False
    user_limit: Optional[int] = None


class AccessTransferRequest(BaseModel):
    """Transfer organization access from one vendor to another"""
    from_vendor_id: int
    to_vendor_id: int
    organization_id: int
    maintain_user_access: bool = True
    transfer_date: Optional[datetime] = None


# ============= VENDOR USER PROVISIONING =============

@router.post("/provision-user")
async def provision_single_user(
    *,
    db: AsyncSession = Depends(get_db),
    provision_request: VendorUserProvision,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> dict:
    """
    Provision a single user with vendor device access.
    
    This endpoint allows vendors to create user accounts for healthcare
    professionals with automatic password generation and device access.
    """
    # Check permissions - must be vendor admin or super admin
    if current_user.role not in ["vendor_admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only vendor admins can provision users"
        )
    
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == provision_request.email)
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        # Update existing user's vendor access
        return await _update_vendor_access(
            db, existing_user, provision_request, current_user, background_tasks
        )
    
    # Generate secure temporary password
    temp_password = None
    if provision_request.auto_generate_password:
        # Generate a memorable but secure password
        words = ["Secure", "Medical", "Device", "Access"]
        numbers = secrets.token_hex(2).upper()
        special = "!@#"[secrets.randbelow(3)]
        temp_password = f"{secrets.choice(words)}{numbers}{special}"
    else:
        # Use a standard temporary password
        temp_password = "TempAccess2025!"
    
    # Parse full name
    name_parts = provision_request.full_name.strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    
    # Create user account
    user = User(
        email=provision_request.email,
        password_hash=auth_service.get_password_hash(temp_password),
        first_name=first_name,
        last_name=last_name,
        department=provision_request.department,
        role=provision_request.role,
        organization_id=current_user.organization_id,  # Link to vendor org initially
        email_verified=False,
        require_password_change=provision_request.require_password_change,
        created_via="vendor_provision",
        created_by=current_user.id,
        vendor_access_level=provision_request.access_level,
        vendor_device_access=provision_request.devices,
        access_expires_at=provision_request.expires_at
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Send welcome email with credentials
    if provision_request.send_welcome_email:
        try:
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_vendor_provision_email,
                to_email=user.email,
                temp_password=temp_password,
                vendor_name=current_user.organization.name if current_user.organization else "Vendor",
                devices=provision_request.devices,
                expires_at=provision_request.expires_at
            )
        except Exception as e:
            logger.error(f"Failed to send provision email: {e}")
    
    logger.info(f"User {user.email} provisioned by vendor {current_user.email}")
    
    return {
        "status": "success",
        "data": {
            "user_id": user.id,
            "email": user.email,
            "temporary_password": temp_password,
            "access_level": provision_request.access_level,
            "devices": provision_request.devices,
            "expires_at": provision_request.expires_at.isoformat() if provision_request.expires_at else None
        }
    }


@router.post("/bulk-provision")
async def bulk_provision_users(
    *,
    db: AsyncSession = Depends(get_db),
    provision_request: BulkProvisionRequest,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> dict:
    """
    Bulk provision multiple users for an organization.
    
    Vendors can provision entire departments or organizations at once.
    """
    # Check permissions
    if current_user.role not in ["vendor_admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only vendor admins can bulk provision users"
        )
    
    # Get target organization
    result = await db.execute(
        select(Organization).where(Organization.id == provision_request.organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    
    provisioned_users = []
    failed_users = []
    
    for user_data in provision_request.users:
        try:
            # Check if user exists
            result = await db.execute(
                select(User).where(User.email == user_data.email)
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                # Update existing user
                failed_users.append({
                    "email": user_data.email,
                    "error": "User already exists"
                })
                continue
            
            # Generate password
            temp_password = None
            if user_data.auto_generate_password:
                words = ["Medical", "Device", "Access", "Secure"]
                temp_password = f"{secrets.choice(words)}{secrets.token_hex(2).upper()}!"
            else:
                temp_password = "TempAccess2025!"
            
            # Parse name
            name_parts = user_data.full_name.strip().split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            
            # Create user
            user = User(
                email=user_data.email,
                password_hash=auth_service.get_password_hash(temp_password),
                first_name=first_name,
                last_name=last_name,
                department=user_data.department,
                role=user_data.role,
                organization_id=provision_request.organization_id,
                email_verified=False,
                require_password_change=user_data.require_password_change,
                created_via="vendor_bulk_provision",
                created_by=current_user.id,
                vendor_access_level=user_data.access_level,
                vendor_device_access=user_data.devices,
                access_expires_at=user_data.expires_at
            )
            
            db.add(user)
            
            provisioned_users.append({
                "email": user_data.email,
                "temporary_password": temp_password,
                "access_level": user_data.access_level
            })
            
            # Queue individual welcome emails
            if user_data.send_welcome_email:
                try:
                    email_service = get_email_service()
                    background_tasks.add_task(
                        email_service.send_vendor_provision_email,
                        to_email=user_data.email,
                        temp_password=temp_password,
                        vendor_name=current_user.organization.name if current_user.organization else "Vendor",
                        devices=user_data.devices,
                        expires_at=user_data.expires_at
                    )
                except Exception as e:
                    logger.error(f"Failed to queue email for {user_data.email}: {e}")
            
        except Exception as e:
            failed_users.append({
                "email": user_data.email,
                "error": str(e)
            })
    
    # Commit all users
    await db.commit()
    
    # Send summary email to requester
    if provision_request.send_summary_email and provisioned_users:
        try:
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_bulk_provision_summary,
                to_email=current_user.email,
                organization_name=organization.name,
                provisioned_count=len(provisioned_users),
                failed_count=len(failed_users),
                user_details=provisioned_users
            )
        except Exception as e:
            logger.error(f"Failed to send summary email: {e}")
    
    logger.info(f"Bulk provision by {current_user.email}: {len(provisioned_users)} users created")
    
    return {
        "status": "success",
        "data": {
            "organization": organization.name,
            "provisioned": len(provisioned_users),
            "failed": len(failed_users),
            "users": provisioned_users,
            "errors": failed_users
        }
    }


@router.post("/provision-from-csv")
async def provision_from_csv(
    *,
    db: AsyncSession = Depends(get_db),
    organization_id: int,
    file: UploadFile = File(...),
    auto_generate_passwords: bool = True,
    send_emails: bool = True,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> dict:
    """
    Provision users from a CSV file upload.
    
    CSV format:
    email,full_name,department,role,devices
    """
    # Check permissions
    if current_user.role not in ["vendor_admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only vendor admins can provision users"
        )
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported"
        )
    
    # Read and parse CSV
    contents = await file.read()
    csv_reader = csv.DictReader(io.StringIO(contents.decode('utf-8')))
    
    users_to_provision = []
    for row in csv_reader:
        devices = row.get('devices', '').split(';') if row.get('devices') else None
        
        users_to_provision.append(VendorUserProvision(
            email=row['email'],
            full_name=row['full_name'],
            department=row.get('department'),
            role=row.get('role', 'device_user'),
            devices=devices,
            access_level=row.get('access_level', 'viewer'),
            auto_generate_password=auto_generate_passwords,
            send_welcome_email=send_emails
        ))
    
    # Process bulk provision
    provision_request = BulkProvisionRequest(
        organization_id=organization_id,
        users=users_to_provision,
        send_summary_email=True,
        grant_immediate_access=True
    )
    
    return await bulk_provision_users(
        db=db,
        provision_request=provision_request,
        current_user=current_user,
        background_tasks=background_tasks
    )


# ============= ORGANIZATION ACCESS MANAGEMENT =============

@router.post("/grant-organization-access")
async def grant_organization_access(
    *,
    db: AsyncSession = Depends(get_db),
    grant_request: OrganizationAccessGrant,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> dict:
    """
    Grant an entire organization access to vendor devices.
    
    This creates a relationship between the vendor and healthcare organization.
    """
    # Check permissions
    if current_user.role not in ["vendor_admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only vendor admins can grant organization access"
        )
    
    # Get organization
    result = await db.execute(
        select(Organization).where(Organization.id == grant_request.organization_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    
    # Store organization access grant in cache (in production, use database)
    cache = get_cache_service()
    grant_id = f"grant_{secrets.token_urlsafe(16)}"
    
    grant_data = {
        "vendor_id": current_user.organization_id,
        "organization_id": grant_request.organization_id,
        "device_dis": grant_request.device_dis,
        "access_type": grant_request.access_type,
        "expires_at": grant_request.expires_at.isoformat() if grant_request.expires_at else None,
        "user_limit": grant_request.user_limit,
        "granted_by": current_user.id,
        "granted_at": datetime.utcnow().isoformat()
    }
    
    await cache.set(f"org_grant:{grant_id}", grant_data)
    
    # Auto-provision users if requested
    provisioned_count = 0
    if grant_request.auto_provision_users:
        # Get all users from the organization
        result = await db.execute(
            select(User).where(
                and_(
                    User.organization_id == grant_request.organization_id,
                    User.deleted_at.is_(None)
                )
            ).limit(grant_request.user_limit or 1000)
        )
        org_users = result.scalars().all()
        
        for user in org_users:
            # Add vendor access to existing users
            user.vendor_device_access = grant_request.device_dis
            user.vendor_access_level = "viewer"
            user.access_expires_at = grant_request.expires_at
            provisioned_count += 1
        
        await db.commit()
    
    # Send notification to organization admin
    try:
        # Get org admin
        result = await db.execute(
            select(User).where(
                and_(
                    User.organization_id == grant_request.organization_id,
                    User.role == "org_admin"
                )
            ).limit(1)
        )
        org_admin = result.scalar_one_or_none()
        
        if org_admin:
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_organization_access_granted,
                to_email=org_admin.email,
                vendor_name=current_user.organization.name if current_user.organization else "Vendor",
                access_type=grant_request.access_type,
                device_count=len(grant_request.device_dis) if grant_request.device_dis else "all",
                expires_at=grant_request.expires_at
            )
    except Exception as e:
        logger.error(f"Failed to notify organization admin: {e}")
    
    logger.info(f"Organization access granted by {current_user.email} to org {grant_request.organization_id}")
    
    return {
        "status": "success",
        "data": {
            "grant_id": grant_id,
            "organization": organization.name,
            "access_type": grant_request.access_type,
            "devices": grant_request.device_dis,
            "expires_at": grant_request.expires_at.isoformat() if grant_request.expires_at else None,
            "users_provisioned": provisioned_count
        }
    }


@router.post("/transfer-organization")
async def transfer_organization_access(
    *,
    db: AsyncSession = Depends(get_db),
    transfer_request: AccessTransferRequest,
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> dict:
    """
    Transfer organization access from one vendor to another.
    
    Used when changing device vendors or during mergers/acquisitions.
    """
    # Check permissions - must be super admin or involved vendor
    if current_user.role != "super_admin":
        if current_user.role != "vendor_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can transfer organizations"
            )
        
        # Check if current user is from either vendor
        if current_user.organization_id not in [transfer_request.from_vendor_id, transfer_request.to_vendor_id]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only transfer your own organizations"
            )
    
    # Get all users from the organization
    result = await db.execute(
        select(User).where(
            and_(
                User.organization_id == transfer_request.organization_id,
                User.deleted_at.is_(None)
            )
        )
    )
    org_users = result.scalars().all()
    
    users_transferred = 0
    for user in org_users:
        # Update vendor association
        # In production, this would update a vendor_user_access table
        user.vendor_id = transfer_request.to_vendor_id
        
        if not transfer_request.maintain_user_access:
            # Reset access and require re-provisioning
            user.vendor_device_access = None
            user.vendor_access_level = None
            user.require_password_change = True
        
        users_transferred += 1
    
    await db.commit()
    
    # Log transfer in cache (in production, use database)
    cache = get_cache_service()
    transfer_id = f"transfer_{secrets.token_urlsafe(16)}"
    
    await cache.set(
        f"org_transfer:{transfer_id}",
        {
            "from_vendor_id": transfer_request.from_vendor_id,
            "to_vendor_id": transfer_request.to_vendor_id,
            "organization_id": transfer_request.organization_id,
            "users_transferred": users_transferred,
            "transferred_by": current_user.id,
            "transferred_at": datetime.utcnow().isoformat()
        }
    )
    
    logger.info(f"Organization {transfer_request.organization_id} transferred from vendor {transfer_request.from_vendor_id} to {transfer_request.to_vendor_id}")
    
    return {
        "status": "success",
        "data": {
            "transfer_id": transfer_id,
            "users_transferred": users_transferred,
            "maintain_access": transfer_request.maintain_user_access,
            "transfer_date": transfer_request.transfer_date.isoformat() if transfer_request.transfer_date else datetime.utcnow().isoformat()
        }
    }


# ============= ACCESS MANAGEMENT =============

@router.get("/provisioned-users")
async def get_provisioned_users(
    *,
    db: AsyncSession = Depends(get_db),
    organization_id: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user)
) -> PaginatedResponse:
    """
    Get list of users provisioned by the vendor.
    """
    # Check permissions
    if current_user.role not in ["vendor_admin", "vendor_rep", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only vendor staff can view provisioned users"
        )
    
    # Build query
    query = select(User).where(
        User.created_by == current_user.id if current_user.role != "super_admin" else True
    )
    
    if organization_id:
        query = query.where(User.organization_id == organization_id)
    
    if search:
        query = query.where(
            or_(
                User.email.ilike(f"%{search}%"),
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%")
            )
        )
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get paginated results
    query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
    result = await db.execute(query)
    users = result.scalars().all()
    
    return PaginatedResponse(
        items=[UserResponse.from_orm_with_computed(user) for user in users],
        total=total,
        skip=skip,
        limit=limit
    )


@router.post("/revoke-access/{user_id}")
async def revoke_user_access(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
) -> SuccessResponse:
    """
    Revoke a user's access to vendor devices.
    """
    # Check permissions
    if current_user.role not in ["vendor_admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only vendor admins can revoke access"
        )
    
    # Get user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Revoke access
    user.vendor_device_access = None
    user.vendor_access_level = None
    user.access_revoked_at = datetime.utcnow()
    user.access_revoked_by = current_user.id
    user.access_revoked_reason = reason
    
    await db.commit()
    
    logger.info(f"Access revoked for user {user.email} by {current_user.email}")
    
    return SuccessResponse(
        message=f"Access revoked for {user.email}"
    )


# ============= HELPER FUNCTIONS =============

async def _update_vendor_access(
    db: AsyncSession,
    user: User,
    provision_request: VendorUserProvision,
    current_user: User,
    background_tasks: BackgroundTasks
) -> dict:
    """
    Update existing user's vendor access.
    """
    # Update access fields
    user.vendor_device_access = provision_request.devices
    user.vendor_access_level = provision_request.access_level
    user.access_expires_at = provision_request.expires_at
    user.access_updated_by = current_user.id
    user.access_updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(user)
    
    # Send update notification
    if provision_request.send_welcome_email:
        try:
            email_service = get_email_service()
            background_tasks.add_task(
                email_service.send_access_update_email,
                to_email=user.email,
                vendor_name=current_user.organization.name if current_user.organization else "Vendor",
                devices=provision_request.devices,
                access_level=provision_request.access_level,
                expires_at=provision_request.expires_at
            )
        except Exception as e:
            logger.error(f"Failed to send access update email: {e}")
    
    logger.info(f"Access updated for user {user.email} by vendor {current_user.email}")
    
    return {
        "status": "success",
        "data": {
            "user_id": user.id,
            "email": user.email,
            "access_updated": True,
            "access_level": provision_request.access_level,
            "devices": provision_request.devices,
            "expires_at": provision_request.expires_at.isoformat() if provision_request.expires_at else None
        }
    }
