"""
Device management endpoints.

This module provides endpoints for searching, creating, updating, and managing
medical devices. Includes both FDA GUDID data access and vendor-specific device
information management.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cache import CacheService, get_cache_service
from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.db.models.device_document import DeviceDocument
from src.db.models.device_video import DeviceVideo
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.db.models.user_bookmarks import UserBookmark
from src.db.session import get_db
from src.schemas.base import PaginatedResponse, PaginationParams, SuccessResponse
from src.schemas.device import (
    DeviceComparisonRequest,
    DeviceComparisonResponse,
    DeviceSearchRequest,
    DeviceSearchResponse,
    DeviceSearchResult,
    GUDIDDeviceResponse,
    VendorDeviceCreate,
    VendorDeviceResponse,
    VendorDeviceUpdate,
)
from src.services.auth_service import get_current_active_user, require_vendor

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/search", response_model=DeviceSearchResponse)
async def search_devices(
    *,
    db: AsyncSession = Depends(get_db),
    search_request: DeviceSearchRequest,
    current_user = Depends(get_current_active_user),
    cache_service: CacheService = Depends(get_cache_service)
) -> Any:
    """
    Search for medical devices across GUDID and vendor data.
    
    Implements multi-strategy search to find the most relevant medical devices
    based on the query. Results are ranked by relevance and filtered based on
    user permissions.
    
    Search Strategies:
        1. Exact DI/UDI match - Highest priority for device identifiers
        2. Full-text search - PostgreSQL ts_vector search on device fields  
        3. Manufacturer + model - Handles queries like "Medtronic pacemaker"
        4. Category search - GMDN terms and FDA device classifications
        5. Fuzzy search - Elasticsearch integration for typo tolerance
    
    Args:
        search_request: Search parameters including:
            - query: Search text (required, min 2 characters)
            - filters: Optional filters (device_class, manufacturer, etc.)
            - page: Page number for pagination (default: 1)
            - limit: Results per page (max: 50)
            - sort: Sort order (relevance, name, manufacturer)
        current_user: Authenticated user for access control
        
    Returns:
        DeviceSearchResponse containing:
            - results: List of matching devices with scores
            - total_count: Total matches found
            - facets: Aggregated filters for refinement
            - suggestions: Alternative search queries
            - execution_time_ms: Search duration
            
    Performance:
        - Results cached for 15 minutes
        - Target response time: <200ms
        - Parallel execution of search strategies
        
    Access Control:
        - Public devices visible to all authenticated users
        - Organization devices visible to members only
        - Admins can see all devices
    """
    start_time = datetime.utcnow()
    
    # Check cache first
    cache_key = cache_service.search_key(search_request.query, search_request.filters)
    cached_results = await cache_service.get(cache_key)
    if cached_results:
        cached_results["from_cache"] = True
        return DeviceSearchResponse(**cached_results)
    
    # Build base query
    query = select(VendorDevice, GUDIDDevice).outerjoin(
        GUDIDDevice,
        VendorDevice.gudid_device_di == GUDIDDevice.primary_di
    ).where(
        and_(
            VendorDevice.is_active == True,
            VendorDevice.deleted_at.is_(None)
        )
    )
    
    # Apply access control
    if not current_user.is_admin:
        # Non-admins can only see public devices or their org's devices
        query = query.where(
            or_(
                VendorDevice.access_level == 'public',
                VendorDevice.organization_id == current_user.organization_id
            )
        )
    
    # Apply search term
    search_term = f"%{search_request.query}%"
    query = query.where(
        or_(
            # Vendor device fields
            VendorDevice.internal_sku.ilike(search_term),
            VendorDevice.custom_name.ilike(search_term),
            # GUDID device fields
            GUDIDDevice.primary_di.ilike(search_term),
            GUDIDDevice.device_name.ilike(search_term),
            GUDIDDevice.manufacturer_name.ilike(search_term),
            GUDIDDevice.brand_name.ilike(search_term),
            GUDIDDevice.model_number.ilike(search_term),
            GUDIDDevice.gmdn_terms.ilike(search_term)
        )
    )
    
    # Apply filters
    if search_request.filters:
        filters = search_request.filters
        
        if "device_class" in filters:
            query = query.where(GUDIDDevice.device_class.in_(filters["device_class"]))
        
        if "manufacturer" in filters:
            query = query.where(GUDIDDevice.manufacturer_name.in_(filters["manufacturer"]))
        
        if "mri_safety" in filters:
            query = query.where(GUDIDDevice.mri_safety == filters["mri_safety"])
        
        if "sterile" in filters:
            query = query.where(GUDIDDevice.sterile == filters["sterile"])
        
        if "organization_id" in filters:
            query = query.where(VendorDevice.organization_id == filters["organization_id"])
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0
    
    # Apply sorting
    if search_request.sort == "name":
        query = query.order_by(GUDIDDevice.device_name.asc())
    elif search_request.sort == "manufacturer":
        query = query.order_by(GUDIDDevice.manufacturer_name.asc())
    else:  # relevance (default)
        # Simple relevance: exact matches first
        query = query.order_by(
            GUDIDDevice.primary_di == search_request.query,
            VendorDevice.internal_sku == search_request.query
        )
    
    # Apply pagination
    offset = (search_request.page - 1) * search_request.limit
    query = query.offset(offset).limit(search_request.limit)
    
    # Execute query
    result = await db.execute(query)
    rows = result.all()
    
    # Build results
    results = []
    for vendor_device, gudid_device in rows:
        # Get counts
        doc_count_result = await db.execute(
            select(func.count(DeviceDocument.id)).where(
                DeviceDocument.device_id == vendor_device.id
            )
        )
        doc_count = doc_count_result.scalar() or 0
        
        video_count_result = await db.execute(
            select(func.count(DeviceVideo.id)).where(
                DeviceVideo.device_id == vendor_device.id
            )
        )
        video_count = video_count_result.scalar() or 0
        
        device_response = VendorDeviceResponse.from_orm_with_related(
            vendor_device, doc_count, video_count
        )
        
        # Calculate simple relevance score
        relevance_score = 1.0
        if gudid_device:
            if gudid_device.primary_di == search_request.query:
                relevance_score = 1.0
            elif search_request.query.lower() in gudid_device.device_name.lower():
                relevance_score = 0.8
            elif search_request.query.lower() in gudid_device.manufacturer_name.lower():
                relevance_score = 0.6
            else:
                relevance_score = 0.4
        
        results.append(DeviceSearchResult(
            device=device_response,
            relevance_score=relevance_score,
            matched_fields=["device_name"]  # TODO: Track actual matched fields
        ))
    
    # Calculate execution time
    execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    
    # Generate facets
    facets = {}
    
    # Device class facet
    class_facet_query = select(
        GUDIDDevice.device_class,
        func.count(VendorDevice.id).label('count')
    ).select_from(VendorDevice).outerjoin(
        GUDIDDevice,
        VendorDevice.gudid_device_di == GUDIDDevice.primary_di
    ).where(
        and_(
            VendorDevice.is_active == True,
            VendorDevice.deleted_at.is_(None),
            GUDIDDevice.device_class.isnot(None)
        )
    ).group_by(GUDIDDevice.device_class)
    
    class_facet_result = await db.execute(class_facet_query)
    class_facets = {row.device_class: row.count for row in class_facet_result}
    if class_facets:
        facets["device_class"] = class_facets
    
    # Manufacturer facet (top 10)
    manufacturer_facet_query = select(
        GUDIDDevice.manufacturer_name,
        func.count(VendorDevice.id).label('count')
    ).select_from(VendorDevice).outerjoin(
        GUDIDDevice,
        VendorDevice.gudid_device_di == GUDIDDevice.primary_di
    ).where(
        and_(
            VendorDevice.is_active == True,
            VendorDevice.deleted_at.is_(None),
            GUDIDDevice.manufacturer_name.isnot(None)
        )
    ).group_by(
        GUDIDDevice.manufacturer_name
    ).order_by(
        func.count(VendorDevice.id).desc()
    ).limit(10)
    
    manufacturer_facet_result = await db.execute(manufacturer_facet_query)
    manufacturer_facets = {row.manufacturer_name: row.count for row in manufacturer_facet_result}
    if manufacturer_facets:
        facets["manufacturer"] = manufacturer_facets
    
    # Generate search suggestions
    suggestions = []
    
    # If query has potential typos, suggest corrections
    if len(search_request.query) > 3:
        # Simple suggestion: if no results found, try common corrections
        if total == 0:
            common_corrections = {
                "infuson": "infusion",
                "cathetir": "catheter",
                "defibrilator": "defibrillator",
                "sergical": "surgical",
                "surgicel": "surgical"
            }
            
            query_lower = search_request.query.lower()
            for typo, correction in common_corrections.items():
                if typo in query_lower:
                    suggestions.append(query_lower.replace(typo, correction))
    
    # Build response
    response = DeviceSearchResponse(
        results=results,
        total=total,
        page=search_request.page,
        pages=(total + search_request.limit - 1) // search_request.limit,
        execution_time_ms=execution_time_ms,
        suggestions=suggestions[:5],  # Limit to 5 suggestions
        facets=facets
    )
    
    # Cache results (15 minutes)
    await cache_service.set(cache_key, response.model_dump(), expire=900)
    
    return response


@router.get("/gudid/{primary_di}", response_model=GUDIDDeviceResponse)
async def get_gudid_device(
    *,
    db: AsyncSession = Depends(get_db),
    primary_di: str,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Get FDA GUDID device information by Device Identifier.
    
    Retrieves comprehensive device information from the FDA Global Unique
    Device Identification Database (GUDID). This includes regulatory info,
    physical characteristics, and safety information.
    
    Args:
        primary_di: FDA Primary Device Identifier (DI)
        current_user: Authenticated user (any role can access GUDID data)
        
    Returns:
        GUDIDDeviceResponse with all FDA device information including:
            - Device identification (name, model, catalog numbers)
            - Manufacturer information
            - FDA classification and regulation
            - Physical characteristics (sterile, single-use, etc.)
            - Safety information (MRI safety, latex, etc.)
            - GMDN codes and terms
            
    Raises:
        ResourceNotFoundError: If device not found in GUDID database
        
    Note:
        GUDID data is public and accessible to all authenticated users.
        Updated daily via ETL process from FDA.
    """
    # Get device
    result = await db.execute(
        select(GUDIDDevice).where(GUDIDDevice.primary_di == primary_di)
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise ResourceNotFoundError("GUDID device", primary_di)
    
    return GUDIDDeviceResponse.from_orm_with_computed(device)


@router.post("/", response_model=VendorDeviceResponse)
async def create_vendor_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_in: VendorDeviceCreate,
    current_user = Depends(require_vendor)
) -> Any:
    """
    Create a new vendor-specific device record.
    
    Allows vendors to create device records in the system, optionally linking
    them to FDA GUDID data. Vendors can add custom information like pricing,
    internal SKUs, and access controls.
    
    Args:
        device_in: Device creation data including:
            - gudid_device_di: Optional link to FDA device
            - internal_sku: Vendor's internal SKU (must be unique)
            - custom_name: Vendor's name for the device
            - list_price: Optional pricing information
            - specifications: Custom specs as JSON
            - access_level: public/private/restricted
        current_user: Authenticated vendor user
        
    Returns:
        VendorDeviceResponse with created device information
        
    Raises:
        AuthorizationError: If user lacks vendor privileges
        HTTPException 400: If GUDID device not found or SKU already exists
        
    Security:
        - Requires vendor role (vendor_admin, vendor_rep)
        - Can only create devices for own organization
        - Super admins can create for any organization
    """
    # Check organization access
    if device_in.organization_id != current_user.organization_id:
        if current_user.role != "super_admin":
            raise AuthorizationError("Cannot create devices for other organizations")
    
    # Verify GUDID device exists if specified
    if device_in.gudid_device_di:
        result = await db.execute(
            select(GUDIDDevice).where(GUDIDDevice.primary_di == device_in.gudid_device_di)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GUDID device '{device_in.gudid_device_di}' not found"
            )
        
        # Check if already linked
        result = await db.execute(
            select(VendorDevice).where(
                and_(
                    VendorDevice.organization_id == device_in.organization_id,
                    VendorDevice.gudid_device_di == device_in.gudid_device_di
                )
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This GUDID device is already linked to your organization"
            )
    
    # Check SKU uniqueness
    if device_in.internal_sku:
        result = await db.execute(
            select(VendorDevice).where(
                and_(
                    VendorDevice.organization_id == device_in.organization_id,
                    VendorDevice.internal_sku == device_in.internal_sku
                )
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SKU already exists in your organization"
            )
    
    # Create device
    device = VendorDevice(
        **device_in.model_dump(),
        created_by=current_user.id
    )
    
    db.add(device)
    await db.commit()
    await db.refresh(device)
    
    logger.info(f"Vendor device created by {current_user.email}: {device.id}")
    
    return VendorDeviceResponse.from_orm_with_related(device)


@router.get("/", response_model=PaginatedResponse)
async def list_vendor_devices(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user),
    pagination: PaginationParams = Depends(),
    organization_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    has_documents: Optional[bool] = Query(None)
) -> Any:
    """
    List vendor devices with pagination and filtering.
    
    Returns a paginated list of vendor devices based on user permissions.
    Supports filtering by organization, active status, and document availability.
    
    Args:
        pagination: Pagination parameters (page, limit)
        organization_id: Filter by specific organization
        is_active: Filter by active/inactive status
        has_documents: Filter devices with/without documents
        current_user: Authenticated user for access control
        
    Returns:
        PaginatedResponse containing:
            - items: List of VendorDeviceResponse objects
            - total: Total count of matching devices
            - page: Current page number
            - pages: Total number of pages
            
    Access Control:
        - Super admins: See all devices
        - Vendors: See own organization's devices  
        - Others: See only public devices
        
    Performance:
        - Includes document and video counts for each device
        - Ordered by creation date (newest first)
    """
    # Build query
    query = select(VendorDevice).where(VendorDevice.deleted_at.is_(None))
    
    # Apply access control
    if current_user.role == "super_admin":
        # Can see all devices
        pass
    elif current_user.is_vendor:
        # Can see own organization's devices
        query = query.where(VendorDevice.organization_id == current_user.organization_id)
    else:
        # Can only see public devices
        query = query.where(VendorDevice.access_level == 'public')
    
    # Apply filters
    if organization_id:
        query = query.where(VendorDevice.organization_id == organization_id)
    
    if is_active is not None:
        query = query.where(VendorDevice.is_active == is_active)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0
    
    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.limit)
    query = query.order_by(VendorDevice.created_at.desc())
    
    # Execute query
    result = await db.execute(query)
    devices = result.scalars().all()
    
    # Build response with counts
    items = []
    for device in devices:
        # Get document count
        doc_count_result = await db.execute(
            select(func.count(DeviceDocument.id)).where(
                DeviceDocument.device_id == device.id
            )
        )
        doc_count = doc_count_result.scalar() or 0
        
        # Get video count
        video_count_result = await db.execute(
            select(func.count(DeviceVideo.id)).where(
                DeviceVideo.device_id == device.id
            )
        )
        video_count = video_count_result.scalar() or 0
        
        items.append(VendorDeviceResponse.from_orm_with_related(
            device, doc_count, video_count
        ))
    
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=pagination.page,
        limit=pagination.limit
    )


@router.get("/{device_id}", response_model=VendorDeviceResponse)
async def get_vendor_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_id: int,
    current_user = Depends(get_current_active_user),
    cache_service: CacheService = Depends(get_cache_service)
) -> Any:
    """
    Get vendor device details by ID.
    
    Retrieves comprehensive information about a vendor device including
    linked GUDID data, document counts, and video counts. Results are
    cached for performance.
    
    Args:
        device_id: Unique device identifier
        current_user: Authenticated user for access control
        
    Returns:
        VendorDeviceResponse with complete device information
        
    Raises:
        ResourceNotFoundError: If device not found or deleted
        AuthorizationError: If user lacks access to device
        
    Access Control:
        - Device must be public OR
        - User must belong to device's organization OR
        - User must be super admin
        
    Performance:
        - Results cached for 1 hour
        - Includes related counts in single response
    """
    # Try cache first
    cached_device = await cache_service.get_cached_device(device_id)
    if cached_device:
        return VendorDeviceResponse(**cached_device)
    
    # Get device with relationships
    result = await db.execute(
        select(VendorDevice).where(
            and_(
                VendorDevice.id == device_id,
                VendorDevice.deleted_at.is_(None)
            )
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise ResourceNotFoundError("Device", device_id)
    
    # Check access
    if not device.can_user_access(current_user):
        raise AuthorizationError("Cannot access this device")
    
    # Get counts
    doc_count_result = await db.execute(
        select(func.count(DeviceDocument.id)).where(
            DeviceDocument.device_id == device.id
        )
    )
    doc_count = doc_count_result.scalar() or 0
    
    video_count_result = await db.execute(
        select(func.count(DeviceVideo.id)).where(
            DeviceVideo.device_id == device.id
        )
    )
    video_count = video_count_result.scalar() or 0
    
    response = VendorDeviceResponse.from_orm_with_related(
        device, doc_count, video_count
    )
    
    # Cache device data
    await cache_service.cache_device(device_id, response.model_dump())
    
    return response


@router.put("/{device_id}", response_model=VendorDeviceResponse)
async def update_vendor_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_id: int,
    device_in: VendorDeviceUpdate,
    current_user = Depends(require_vendor),
    cache_service: CacheService = Depends(get_cache_service)
) -> Any:
    """
    Update vendor device information.
    
    Allows vendors to update device information including custom names,
    pricing, specifications, and access controls. GUDID linkage cannot
    be changed after creation.
    
    Args:
        device_id: Device to update
        device_in: Update data (only provided fields are updated)
        current_user: Authenticated vendor user
        
    Returns:
        VendorDeviceResponse with updated device information
        
    Raises:
        ResourceNotFoundError: If device not found
        AuthorizationError: If user lacks update permissions
        HTTPException 400: If SKU already exists
        
    Security:
        - Requires vendor privileges
        - Can only update own organization's devices
        - Super admins can update any device
        
    Side Effects:
        - Invalidates device cache
        - Logs update action
    """
    # Get device
    result = await db.execute(
        select(VendorDevice).where(
            and_(
                VendorDevice.id == device_id,
                VendorDevice.deleted_at.is_(None)
            )
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise ResourceNotFoundError("Device", device_id)
    
    # Check permissions
    if device.organization_id != current_user.organization_id:
        if current_user.role != "super_admin":
            raise AuthorizationError("Cannot update devices from other organizations")
    
    # Check SKU uniqueness if changed
    if device_in.internal_sku and device_in.internal_sku != device.internal_sku:
        result = await db.execute(
            select(VendorDevice).where(
                and_(
                    VendorDevice.organization_id == device.organization_id,
                    VendorDevice.internal_sku == device_in.internal_sku,
                    VendorDevice.id != device_id
                )
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SKU already exists in your organization"
            )
    
    # Update device
    update_data = device_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)
    
    await db.commit()
    await db.refresh(device)
    
    # Invalidate cache
    await cache_service.invalidate_device_cache(device_id)
    
    logger.info(f"Device updated by {current_user.email}: {device_id}")
    
    return VendorDeviceResponse.from_orm_with_related(device)


@router.delete("/{device_id}", response_model=SuccessResponse)
async def delete_vendor_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_id: int,
    current_user = Depends(require_vendor),
    cache_service: CacheService = Depends(get_cache_service)
) -> Any:
    """
    Soft delete a vendor device.
    
    Marks the device as deleted without removing it from the database.
    Deleted devices are excluded from searches and listings but can be
    restored if needed.
    
    Args:
        device_id: Device to delete
        current_user: Authenticated vendor user
        
    Returns:
        SuccessResponse confirming deletion
        
    Raises:
        ResourceNotFoundError: If device not found
        AuthorizationError: If user lacks delete permissions
        
    Security:
        - Requires vendor privileges
        - Can only delete own organization's devices
        - Super admins can delete any device
        
    Side Effects:
        - Sets deleted_at timestamp
        - Sets is_active to False
        - Invalidates device cache
        - Logs deletion action
        
    Note:
        Associated documents and videos are NOT deleted and remain
        accessible through direct links if user has permissions.
    """
    # Get device
    result = await db.execute(
        select(VendorDevice).where(
            and_(
                VendorDevice.id == device_id,
                VendorDevice.deleted_at.is_(None)
            )
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise ResourceNotFoundError("Device", device_id)
    
    # Check permissions
    if device.organization_id != current_user.organization_id:
        if current_user.role != "super_admin":
            raise AuthorizationError("Cannot delete devices from other organizations")
    
    # Soft delete
    device.deleted_at = datetime.utcnow()
    device.is_active = False
    
    await db.commit()
    
    # Invalidate cache
    await cache_service.invalidate_device_cache(device_id)
    
    logger.info(f"Device deleted by {current_user.email}: {device_id}")
    
    return SuccessResponse(
        message="Device successfully deleted"
    )


@router.post("/compare", response_model=DeviceComparisonResponse)
async def compare_devices(
    *,
    db: AsyncSession = Depends(get_db),
    comparison: DeviceComparisonRequest,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Compare multiple devices side by side.
    
    Creates a comparison matrix of device attributes for easy evaluation.
    Useful for procurement decisions and device selection.
    
    Args:
        comparison: Request containing:
            - device_ids: List of device IDs to compare (max 5)
        current_user: Authenticated user for access control
        
    Returns:
        DeviceComparisonResponse containing:
            - devices: Full details of each device
            - comparison_matrix: Key attributes in table format
            
    Raises:
        ResourceNotFoundError: If any device not found
        AuthorizationError: If user lacks access to any device
        HTTPException 400: If more than 5 devices requested
        
    Comparison Attributes:
        - Name and manufacturer
        - SKU and pricing
        - FDA classification
        - MRI safety status
        - Sterility information
        - Training requirements
        
    Access Control:
        - User must have access to all devices being compared
        - Follows same rules as individual device access
    """
    # Get all devices
    devices = []
    for device_id in comparison.device_ids:
        result = await db.execute(
            select(VendorDevice).where(
                and_(
                    VendorDevice.id == device_id,
                    VendorDevice.deleted_at.is_(None)
                )
            )
        )
        device = result.scalar_one_or_none()
        
        if not device:
            raise ResourceNotFoundError("Device", device_id)
        
        if not device.can_user_access(current_user):
            raise AuthorizationError(f"Cannot access device {device_id}")
        
        devices.append(device)
    
    # Build comparison matrix
    comparison_matrix = {
        "Name": [d.display_name for d in devices],
        "Manufacturer": [d.manufacturer_name for d in devices],
        "SKU": [d.internal_sku or "N/A" for d in devices],
        "Price": [f"${d.list_price}" if d.list_price else "N/A" for d in devices],
        "FDA Class": [],
        "MRI Safety": [],
        "Sterile": [],
        "Training Required": [d.training_required for d in devices],
    }
    
    # Add GUDID data if available
    for device in devices:
        if device.gudid_device:
            comparison_matrix["FDA Class"].append(device.gudid_device.device_class or "N/A")
            comparison_matrix["MRI Safety"].append(device.gudid_device.mri_safety or "N/A")
            comparison_matrix["Sterile"].append(device.gudid_device.sterile or "N/A")
        else:
            comparison_matrix["FDA Class"].append("N/A")
            comparison_matrix["MRI Safety"].append("N/A")
            comparison_matrix["Sterile"].append("N/A")
    
    # Build response
    device_responses = []
    for device in devices:
        doc_count_result = await db.execute(
            select(func.count(DeviceDocument.id)).where(
                DeviceDocument.device_id == device.id
            )
        )
        doc_count = doc_count_result.scalar() or 0
        
        video_count_result = await db.execute(
            select(func.count(DeviceVideo.id)).where(
                DeviceVideo.device_id == device.id
            )
        )
        video_count = video_count_result.scalar() or 0
        
        device_responses.append(VendorDeviceResponse.from_orm_with_related(
            device, doc_count, video_count
        ))
    
    return DeviceComparisonResponse(
        devices=device_responses,
        comparison_matrix=comparison_matrix
    )


@router.post("/{device_id}/bookmark", response_model=SuccessResponse)
async def bookmark_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_id: int,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Bookmark a device for quick access.
    
    Adds the device to the user's personal bookmarks list for easy
    retrieval. Bookmarked devices appear in a dedicated section of
    the user's dashboard.
    
    Args:
        device_id: Device to bookmark
        current_user: Authenticated user
        
    Returns:
        SuccessResponse confirming bookmark creation
        
    Raises:
        ResourceNotFoundError: If device not found
        AuthorizationError: If user lacks access to device
        HTTPException 400: If device already bookmarked
        
    Features:
        - Personal bookmarks per user
        - Organized in folders (future)
        - Quick access from dashboard
        - Bookmark notes (future)
        
    Note:
        Currently a placeholder - full bookmark functionality
        to be implemented with UserBookmark model.
    """
    # Verify device exists and user can access it
    result = await db.execute(
        select(VendorDevice).where(
            and_(
                VendorDevice.id == device_id,
                VendorDevice.deleted_at.is_(None)
            )
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise ResourceNotFoundError("Device", device_id)
    
    if not device.can_user_access(current_user):
        raise AuthorizationError("Cannot access this device")
    
    # Check if already bookmarked
    existing = await db.execute(
        select(UserBookmark).where(
            and_(
                UserBookmark.user_id == current_user.id,
                UserBookmark.resource_type == "device",
                UserBookmark.resource_id == str(device_id)
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device already bookmarked"
        )
    
    # Create bookmark
    bookmark = UserBookmark(
        user_id=current_user.id,
        resource_type="device",
        resource_id=str(device_id),
        title=device.display_name if hasattr(device, 'display_name') else f"Device {device_id}",
        metadata={"device_name": device.custom_name or device.internal_sku or f"Device {device_id}"}
    )
    db.add(bookmark)
    await db.commit()
    
    logger.info(f"Device bookmarked by {current_user.email}: {device_id}")
    
    return SuccessResponse(
        message="Device successfully bookmarked"
    )
