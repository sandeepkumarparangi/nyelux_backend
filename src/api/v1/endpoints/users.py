from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from typing import Any, List, Optional
import logging

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.organization import Organization
from src.services.auth_service import get_current_active_user, require_admin
from src.schemas.user import UserResponse, UserUpdate, UserList, RoleUpdate
from src.schemas.base import PaginationParams, PaginatedResponse, SuccessResponse
from src.core.exceptions import ResourceNotFoundError, AuthorizationError

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get current user profile.
    Properly loads relationships to avoid lazy loading issues.
    """
    # Reload the user with relationships eagerly loaded
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.department)
        )
        .where(User.id == current_user.id)
    )
    user = result.scalar_one()
    
    return UserResponse.from_orm_with_computed(user)

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update current user profile.
    """
    # Update allowed fields
    update_data = user_in.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if field == "email" and value != current_user.email:
            # Check if new email already exists
            result = await db.execute(
                select(User).where(
                    and_(
                        User.email == value,
                        User.id != current_user.id
                    )
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
                )
            # Reset email verification if email changed
            current_user.email_verified = False
            
        setattr(current_user, field, value)
    
    await db.commit()
    
    # Reload with relationships for response
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.department)
        )
        .where(User.id == current_user.id)
    )
    updated_user = result.scalar_one()
    
    logger.info(f"User profile updated: {updated_user.email}")
    
    return UserResponse.from_orm_with_computed(updated_user)

@router.delete("/me", response_model=SuccessResponse)
async def delete_current_user(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Soft delete current user account.
    """
    from datetime import datetime
    
    current_user.deleted_at = datetime.utcnow()
    await db.commit()
    
    logger.info(f"User account deleted: {current_user.email}")
    
    return SuccessResponse(
        message="Account successfully deleted"
    )

@router.get("/", response_model=PaginatedResponse)
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    pagination: PaginationParams = Depends(),
    organization_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
) -> Any:
    """
    List users with pagination and filters.
    
    - Super admins can see all users
    - Org admins can see users in their organization
    - Others can only see basic info of users in their organization
    """
    # Build query with eager loading
    query = select(User).options(
        selectinload(User.organization),
        selectinload(User.department)
    ).where(User.deleted_at.is_(None))
    
    # Apply filters based on role
    if current_user.role != "super_admin":
        if current_user.role in ["org_admin", "clinical_admin"]:
            # Can see users in their organization
            query = query.where(User.organization_id == current_user.organization_id)
        else:
            # Can only see themselves
            query = query.where(User.id == current_user.id)
    
    # Apply additional filters
    if organization_id:
        query = query.where(User.organization_id == organization_id)
    
    if role:
        query = query.where(User.role == role)
    
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (User.email.ilike(search_term)) |
            (User.first_name.ilike(search_term)) |
            (User.last_name.ilike(search_term))
        )
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.limit)
    query = query.order_by(User.created_at.desc())
    
    # Execute query
    result = await db.execute(query)
    users = result.scalars().all()
    
    # Convert to response
    items = [UserResponse.from_orm_with_computed(user) for user in users]
    
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=pagination.page,
        limit=pagination.limit
    )

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get user by ID.
    
    Access control applies based on user role.
    """
    # Get user with relationships
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.department)
        )
        .where(
            and_(
                User.id == user_id,
                User.deleted_at.is_(None)
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ResourceNotFoundError("User", user_id)
    
    # Check access
    if current_user.role not in ["super_admin", "org_admin", "clinical_admin"]:
        if user.organization_id != current_user.organization_id:
            raise AuthorizationError("Cannot access users from other organizations")
    
    return UserResponse.from_orm_with_computed(user)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Update user by ID.
    
    Requires admin privileges.
    """
    # Get user
    result = await db.execute(
        select(User).where(
            and_(
                User.id == user_id,
                User.deleted_at.is_(None)
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ResourceNotFoundError("User", user_id)
    
    # Check permissions
    if current_user.role == "org_admin" and user.organization_id != current_user.organization_id:
        raise AuthorizationError("Cannot update users from other organizations")
    
    # Update user
    update_data = user_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.department)
        )
        .where(User.id == user_id)
    )
    updated_user = result.scalar_one()
    
    logger.info(f"User updated by admin {current_user.email}: {updated_user.email}")
    
    return UserResponse.from_orm_with_computed(updated_user)

@router.delete("/{user_id}", response_model=SuccessResponse)
async def delete_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Soft delete user by ID.
    
    Requires admin privileges.
    """
    from datetime import datetime
    
    # Get user
    result = await db.execute(
        select(User).where(
            and_(
                User.id == user_id,
                User.deleted_at.is_(None)
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ResourceNotFoundError("User", user_id)
    
    # Check permissions
    if current_user.role == "org_admin" and user.organization_id != current_user.organization_id:
        raise AuthorizationError("Cannot delete users from other organizations")
    
    # Prevent self-deletion
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Soft delete
    user.deleted_at = datetime.utcnow()
    await db.commit()
    
    logger.info(f"User deleted by admin {current_user.email}: {user.email}")
    
    return SuccessResponse(
        message="User successfully deleted"
    )

@router.post("/{user_id}/restore", response_model=UserResponse)
async def restore_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Restore soft-deleted user.
    
    Requires admin privileges.
    """
    # Get deleted user
    result = await db.execute(
        select(User).where(
            and_(
                User.id == user_id,
                User.deleted_at.is_not(None)
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ResourceNotFoundError("Deleted user", user_id)
    
    # Check permissions
    if current_user.role == "org_admin" and user.organization_id != current_user.organization_id:
        raise AuthorizationError("Cannot restore users from other organizations")
    
    # Restore
    user.deleted_at = None
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.department)
        )
        .where(User.id == user_id)
    )
    restored_user = result.scalar_one()
    
    logger.info(f"User restored by admin {current_user.email}: {restored_user.email}")
    
    return UserResponse.from_orm_with_computed(restored_user)

@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    role_in: RoleUpdate,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Update user role.
    
    Requires admin privileges. Only super_admin can assign super_admin role.
    """
    # Get user
    result = await db.execute(
        select(User).where(
            and_(
                User.id == user_id,
                User.deleted_at.is_(None)
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ResourceNotFoundError("User", user_id)
    
    # Check permissions
    if role_in.role == "super_admin" and current_user.role != "super_admin":
        raise AuthorizationError("Only super admins can assign super admin role")
    
    if current_user.role == "org_admin":
        if user.organization_id != current_user.organization_id:
            raise AuthorizationError("Cannot change roles for users from other organizations")
        if role_in.role in ["super_admin", "org_admin"]:
            raise AuthorizationError("Cannot assign admin roles")
    
    # Update role
    old_role = user.role
    user.role = role_in.role
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.department)
        )
        .where(User.id == user_id)
    )
    updated_user = result.scalar_one()
    
    logger.info(
        f"User role changed by admin {current_user.email}: "
        f"{updated_user.email} from {old_role} to {updated_user.role}"
    )
    
    return UserResponse.from_orm_with_computed(updated_user)

@router.post("/{user_id}/unlock", response_model=UserResponse)
async def unlock_user_account(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Unlock user account after failed login attempts.
    
    Requires admin privileges.
    """
    # Get user
    result = await db.execute(
        select(User).where(
            and_(
                User.id == user_id,
                User.deleted_at.is_(None)
            )
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ResourceNotFoundError("User", user_id)
    
    # Check permissions
    if current_user.role == "org_admin" and user.organization_id != current_user.organization_id:
        raise AuthorizationError("Cannot unlock users from other organizations")
    
    # Unlock account
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.department)
        )
        .where(User.id == user_id)
    )
    unlocked_user = result.scalar_one()
    
    logger.info(f"User account unlocked by admin {current_user.email}: {unlocked_user.email}")
    
    return UserResponse.from_orm_with_computed(unlocked_user)

@router.put("/me/organization", response_model=UserResponse)
async def join_organization(
    *,
    db: AsyncSession = Depends(get_db),
    organization_id: int = Query(..., description="Organization ID to join"),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Join an organization (for healthcare professionals only).
    
    - Healthcare professionals can join organizations after signup
    - Vendors cannot change their organization
    - Users already in an organization cannot switch without admin help
    """
    # Check if user is a healthcare professional
    if not current_user.is_healthcare_professional:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only healthcare professionals can join organizations independently"
        )
    
    # Check if user already has an organization
    if current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already associated with an organization. Contact an admin to change."
        )
    
    # Verify organization exists and is a healthcare organization
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.id == organization_id,
                Organization.deleted_at.is_(None),
                Organization.type.in_(['hospital', 'clinic'])
            )
        )
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise ResourceNotFoundError(
            "Healthcare organization", 
            organization_id,
            "Organization not found or is not a healthcare provider"
        )
    
    # Join the organization
    current_user.organization_id = organization_id
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.department)
        )
        .where(User.id == current_user.id)
    )
    updated_user = result.scalar_one()
    
    logger.info(
        f"Healthcare professional {updated_user.email} joined organization: {organization.name}"
    )
    
    return UserResponse.from_orm_with_computed(updated_user)
