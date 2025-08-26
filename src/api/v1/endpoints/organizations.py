from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import Any, List, Optional
import logging

from src.db.session import get_db
from src.db.models.organization import Organization, Department
from src.db.models.user import User
from src.services.auth_service import get_current_active_user, require_admin
from src.schemas.organization import (
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    OrganizationList, DepartmentCreate, DepartmentUpdate,
    DepartmentResponse, DepartmentList, LicenseUpdate
)
from src.schemas.base import PaginationParams, PaginatedResponse, SuccessResponse
from src.core.exceptions import ResourceNotFoundError, AuthorizationError, ValidationError

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=OrganizationResponse)
async def create_organization(
    *,
    db: AsyncSession = Depends(get_db),
    org_in: OrganizationCreate,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Create a new organization.
    
    Requires admin privileges.
    """
    # Check if subdomain already exists
    if org_in.subdomain:
        result = await db.execute(
            select(Organization).where(Organization.subdomain == org_in.subdomain)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subdomain already in use"
            )
    
    # Create organization
    org = Organization(**org_in.model_dump())
    
    db.add(org)
    await db.commit()
    await db.refresh(org)
    
    logger.info(f"Organization created by {current_user.email}: {org.name}")
    
    return OrganizationResponse.from_orm_with_counts(org)

@router.get("/", response_model=PaginatedResponse)
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    pagination: PaginationParams = Depends(),
    org_type: Optional[str] = Query(None),
    is_verified: Optional[bool] = Query(None),
    search: Optional[str] = Query(None)
) -> Any:
    """
    List organizations with pagination and filters.
    
    - Super admins can see all organizations
    - Others can only see their own organization
    """
    # Build query
    query = select(Organization).where(Organization.deleted_at.is_(None))
    
    # Apply access control
    if current_user.role != "super_admin":
        query = query.where(Organization.id == current_user.organization_id)
    
    # Apply filters
    if org_type:
        query = query.where(Organization.type == org_type)
    
    if is_verified is not None:
        query = query.where(Organization.is_verified == is_verified)
    
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Organization.name.ilike(search_term)) |
            (Organization.subdomain.ilike(search_term))
        )
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.limit)
    query = query.order_by(Organization.created_at.desc())
    
    # Execute query
    result = await db.execute(query)
    orgs = result.scalars().all()
    
    # Get counts for each organization
    items = []
    for org in orgs:
        # Get user count
        user_count_result = await db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.organization_id == org.id,
                    User.deleted_at.is_(None)
                )
            )
        )
        user_count = user_count_result.scalar() or 0
        
        # Get device count (would need VendorDevice import)
        device_count = 0  # TODO: Add device count query
        
        items.append(OrganizationResponse.from_orm_with_counts(
            org, user_count, device_count
        ))
    
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=pagination.page,
        limit=pagination.limit
    )

@router.get("/current", response_model=OrganizationResponse)
async def get_current_organization(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get current user's organization.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with an organization"
        )
    
    # Get organization with counts
    org = current_user.organization
    
    # Get user count
    user_count_result = await db.execute(
        select(func.count(User.id)).where(
            and_(
                User.organization_id == org.id,
                User.deleted_at.is_(None)
            )
        )
    )
    user_count = user_count_result.scalar() or 0
    
    return OrganizationResponse.from_orm_with_counts(org, user_count)

@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get organization by ID.
    """
    # Get organization
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.id == org_id,
                Organization.deleted_at.is_(None)
            )
        )
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise ResourceNotFoundError("Organization", org_id)
    
    # Check access
    if current_user.role != "super_admin" and org.id != current_user.organization_id:
        raise AuthorizationError("Cannot access other organizations")
    
    # Get counts
    user_count_result = await db.execute(
        select(func.count(User.id)).where(
            and_(
                User.organization_id == org.id,
                User.deleted_at.is_(None)
            )
        )
    )
    user_count = user_count_result.scalar() or 0
    
    return OrganizationResponse.from_orm_with_counts(org, user_count)

@router.put("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    org_in: OrganizationUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update organization.
    
    - Super admins can update any organization
    - Org admins can update their own organization (limited fields)
    """
    # Get organization
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.id == org_id,
                Organization.deleted_at.is_(None)
            )
        )
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise ResourceNotFoundError("Organization", org_id)
    
    # Check permissions
    if current_user.role == "org_admin":
        if org.id != current_user.organization_id:
            raise AuthorizationError("Cannot update other organizations")
        
        # Org admins can only update certain fields
        allowed_fields = {
            "phone", "website", "address_line1", "address_line2",
            "city", "state_province", "postal_code", "country_code"
        }
        update_data = org_in.model_dump(exclude_unset=True)
        restricted_fields = set(update_data.keys()) - allowed_fields
        if restricted_fields:
            raise AuthorizationError(
                f"Cannot update restricted fields: {', '.join(restricted_fields)}"
            )
    elif current_user.role != "super_admin":
        raise AuthorizationError("Insufficient permissions")
    
    # Check subdomain uniqueness
    if org_in.subdomain and org_in.subdomain != org.subdomain:
        result = await db.execute(
            select(Organization).where(
                and_(
                    Organization.subdomain == org_in.subdomain,
                    Organization.id != org_id
                )
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subdomain already in use"
            )
    
    # Update organization
    update_data = org_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(org, field, value)
    
    await db.commit()
    await db.refresh(org)
    
    logger.info(f"Organization updated by {current_user.email}: {org.name}")
    
    # Get counts
    user_count_result = await db.execute(
        select(func.count(User.id)).where(
            and_(
                User.organization_id == org.id,
                User.deleted_at.is_(None)
            )
        )
    )
    user_count = user_count_result.scalar() or 0
    
    return OrganizationResponse.from_orm_with_counts(org, user_count)

@router.delete("/{org_id}", response_model=SuccessResponse)
async def delete_organization(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Soft delete organization.
    
    Requires super admin privileges.
    """
    if current_user.role != "super_admin":
        raise AuthorizationError("Only super admins can delete organizations")
    
    # Get organization
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.id == org_id,
                Organization.deleted_at.is_(None)
            )
        )
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise ResourceNotFoundError("Organization", org_id)
    
    # Check for active users
    user_count_result = await db.execute(
        select(func.count(User.id)).where(
            and_(
                User.organization_id == org.id,
                User.deleted_at.is_(None)
            )
        )
    )
    user_count = user_count_result.scalar() or 0
    
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete organization with {user_count} active users"
        )
    
    # Soft delete
    from datetime import datetime
    org.deleted_at = datetime.utcnow()
    await db.commit()
    
    logger.info(f"Organization deleted by {current_user.email}: {org.name}")
    
    return SuccessResponse(
        message="Organization successfully deleted"
    )

@router.put("/{org_id}/license", response_model=OrganizationResponse)
async def update_organization_license(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    license_in: LicenseUpdate,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Update organization license.
    
    Requires super admin privileges.
    """
    if current_user.role != "super_admin":
        raise AuthorizationError("Only super admins can update licenses")
    
    # Get organization
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.id == org_id,
                Organization.deleted_at.is_(None)
            )
        )
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise ResourceNotFoundError("Organization", org_id)
    
    # Update license
    org.license_tier = license_in.license_tier
    org.license_expires_at = license_in.expires_at
    
    await db.commit()
    await db.refresh(org)
    
    logger.info(
        f"Organization license updated by {current_user.email}: "
        f"{org.name} to {org.license_tier}"
    )
    
    return OrganizationResponse.from_orm_with_counts(org)

@router.post("/{org_id}/verify", response_model=OrganizationResponse)
async def verify_organization(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    current_user: User = Depends(require_admin)
) -> Any:
    """
    Verify organization.
    
    Requires super admin privileges.
    """
    if current_user.role != "super_admin":
        raise AuthorizationError("Only super admins can verify organizations")
    
    # Get organization
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.id == org_id,
                Organization.deleted_at.is_(None)
            )
        )
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise ResourceNotFoundError("Organization", org_id)
    
    if org.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization is already verified"
        )
    
    # Verify organization
    from datetime import datetime
    org.is_verified = True
    org.verified_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(org)
    
    logger.info(f"Organization verified by {current_user.email}: {org.name}")
    
    return OrganizationResponse.from_orm_with_counts(org)

# Department endpoints
@router.post("/{org_id}/departments", response_model=DepartmentResponse)
async def create_department(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    dept_in: DepartmentCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Create a new department.
    
    Requires org admin privileges.
    """
    # Check permissions
    if current_user.role not in ["super_admin", "org_admin"]:
        raise AuthorizationError("Insufficient permissions")
    
    if current_user.role == "org_admin" and current_user.organization_id != org_id:
        raise AuthorizationError("Cannot create departments for other organizations")
    
    # Verify organization exists
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.id == org_id,
                Organization.deleted_at.is_(None)
            )
        )
    )
    if not result.scalar_one_or_none():
        raise ResourceNotFoundError("Organization", org_id)
    
    # Check if department name already exists
    result = await db.execute(
        select(Department).where(
            and_(
                Department.organization_id == org_id,
                Department.name == dept_in.name
            )
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department name already exists in this organization"
        )
    
    # Create department
    dept = Department(
        organization_id=org_id,
        **dept_in.model_dump(exclude={"organization_id"})
    )
    
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    
    logger.info(f"Department created by {current_user.email}: {dept.name}")
    
    return DepartmentResponse(**dept.__dict__)

@router.get("/{org_id}/departments", response_model=List[DepartmentResponse])
async def list_departments(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    List departments in an organization.
    """
    # Check permissions
    if current_user.role != "super_admin" and current_user.organization_id != org_id:
        raise AuthorizationError("Cannot access departments from other organizations")
    
    # Get departments
    result = await db.execute(
        select(Department).where(Department.organization_id == org_id)
    )
    departments = result.scalars().all()
    
    # Get user counts
    items = []
    for dept in departments:
        user_count_result = await db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.department_id == dept.id,
                    User.deleted_at.is_(None)
                )
            )
        )
        user_count = user_count_result.scalar() or 0
        
        dept_response = DepartmentResponse(**dept.__dict__)
        dept_response.user_count = user_count
        items.append(dept_response)
    
    return items

@router.put("/{org_id}/departments/{dept_id}", response_model=DepartmentResponse)
async def update_department(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    dept_id: int,
    dept_in: DepartmentUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update department.
    
    Requires org admin privileges.
    """
    # Check permissions
    if current_user.role not in ["super_admin", "org_admin"]:
        raise AuthorizationError("Insufficient permissions")
    
    if current_user.role == "org_admin" and current_user.organization_id != org_id:
        raise AuthorizationError("Cannot update departments for other organizations")
    
    # Get department
    result = await db.execute(
        select(Department).where(
            and_(
                Department.id == dept_id,
                Department.organization_id == org_id
            )
        )
    )
    dept = result.scalar_one_or_none()
    
    if not dept:
        raise ResourceNotFoundError("Department", dept_id)
    
    # Check name uniqueness
    if dept_in.name and dept_in.name != dept.name:
        result = await db.execute(
            select(Department).where(
                and_(
                    Department.organization_id == org_id,
                    Department.name == dept_in.name,
                    Department.id != dept_id
                )
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department name already exists in this organization"
            )
    
    # Update department
    update_data = dept_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dept, field, value)
    
    await db.commit()
    await db.refresh(dept)
    
    logger.info(f"Department updated by {current_user.email}: {dept.name}")
    
    return DepartmentResponse(**dept.__dict__)

@router.delete("/{org_id}/departments/{dept_id}", response_model=SuccessResponse)
async def delete_department(
    *,
    db: AsyncSession = Depends(get_db),
    org_id: int,
    dept_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Delete department.
    
    Requires org admin privileges.
    """
    # Check permissions
    if current_user.role not in ["super_admin", "org_admin"]:
        raise AuthorizationError("Insufficient permissions")
    
    if current_user.role == "org_admin" and current_user.organization_id != org_id:
        raise AuthorizationError("Cannot delete departments for other organizations")
    
    # Get department
    result = await db.execute(
        select(Department).where(
            and_(
                Department.id == dept_id,
                Department.organization_id == org_id
            )
        )
    )
    dept = result.scalar_one_or_none()
    
    if not dept:
        raise ResourceNotFoundError("Department", dept_id)
    
    # Check for users in department
    user_count_result = await db.execute(
        select(func.count(User.id)).where(
            and_(
                User.department_id == dept_id,
                User.deleted_at.is_(None)
            )
        )
    )
    user_count = user_count_result.scalar() or 0
    
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete department with {user_count} active users"
        )
    
    # Delete department
    await db.delete(dept)
    await db.commit()
    
    logger.info(f"Department deleted by {current_user.email}: {dept.name}")
    
    return SuccessResponse(
        message="Department successfully deleted"
    )
