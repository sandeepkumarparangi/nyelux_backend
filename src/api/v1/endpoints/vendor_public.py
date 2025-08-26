"""
Vendor Portal Public API endpoints.
Handles public vendor pages, device listings, and chat.
No authentication required for public endpoints.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
import logging

from src.db.session import get_db
from src.db.models.vendor_profile import VendorProfile, VendorCustomContent, VendorChatKnowledge
from src.db.models.vendor_device import VendorDevice
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_lead import VendorLead, VendorLeadActivity
from src.db.models.vendor_service import VendorServiceRequest
from src.db.models.organization import Organization
from src.schemas.vendor_portal import (
    VendorProfilePublic, VendorDevicePublic, VendorPageDeviceList,
    VendorLeadCapture, VendorCustomContentResponse
)
from src.core.deps import get_client_ip
# TODO: Implement analytics service
# from src.services.analytics_service import track_page_view, track_lead_capture

async def track_page_view(**kwargs):
    """Placeholder for analytics tracking"""
    pass

async def track_lead_capture(**kwargs):
    """Placeholder for lead tracking"""
    pass

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vendor", tags=["vendor-public"])


@router.get("/{url_slug}", response_model=VendorProfilePublic)
async def get_vendor_public_profile(
    url_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> VendorProfilePublic:
    """
    Get public vendor profile page data.
    This is the main endpoint for vendor pages like nyelux.com/vendor/medtronic
    """
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True,
                VendorProfile.deleted_at.is_(None)
            )
        )
        .options(selectinload(VendorProfile.organization))
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor page not found"
        )
    
    # Check if published
    if not vendor_profile.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor page not published yet"
        )
    
    # Track page view
    await track_page_view(
        vendor_profile_id=vendor_profile.id,
        page_type="profile",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        referrer=request.headers.get("Referer")
    )
    
    logger.info(f"Public vendor profile viewed: {url_slug}")
    
    return vendor_profile


@router.get("/{url_slug}/devices", response_model=VendorPageDeviceList)
async def get_vendor_devices(
    url_slug: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    device_class: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> VendorPageDeviceList:
    """
    Get all devices for a vendor's public page.
    Includes both FDA GUDID devices and vendor-specific devices.
    """
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True,
                VendorProfile.deleted_at.is_(None)
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile or not vendor_profile.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor page not found"
        )
    
    # Build device query
    query = select(VendorDevice).where(
        and_(
            VendorDevice.organization_id == vendor_profile.organization_id,
            VendorDevice.is_active == True,
            VendorDevice.deleted_at.is_(None),
            or_(
                VendorDevice.access_level == 'public',
                VendorDevice.access_level == 'restricted'  # Show existence but not all details
            )
        )
    ).options(selectinload(VendorDevice.gudid_device))
    
    # Apply filters
    if search:
        search_term = f"%{search}%"
        query = query.join(GUDIDDevice, isouter=True).where(
            or_(
                VendorDevice.custom_name.ilike(search_term),
                VendorDevice.internal_sku.ilike(search_term),
                GUDIDDevice.device_name.ilike(search_term),
                GUDIDDevice.manufacturer_name.ilike(search_term)
            )
        )
    
    if device_class:
        query = query.join(GUDIDDevice).where(
            GUDIDDevice.device_class == device_class
        )
    
    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total_count = count_result.scalar()
    
    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    devices = result.scalars().all()
    
    # Track device list view
    await track_page_view(
        vendor_profile_id=vendor_profile.id,
        page_type="device_list",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent")
    )
    
    # Convert to public format
    public_devices = []
    for device in devices:
        public_device = VendorDevicePublic(
            id=device.id,
            display_name=device.display_name,
            manufacturer_name=device.manufacturer_name,
            device_class=device.gudid_device.device_class if device.gudid_device else None,
            custom_name=device.custom_name,
            features=device.get_features_list() if device.access_level == 'public' else [],
            training_required=device.training_required,
            certification_required=device.certification_required,
            is_available=device.is_available
        )
        public_devices.append(public_device)
    
    return VendorPageDeviceList(
        vendor_profile=VendorProfilePublic.from_orm(vendor_profile),
        devices=public_devices,
        total_count=total_count,
        page=page,
        limit=limit
    )


@router.get("/{url_slug}/device/{device_id}")
async def get_vendor_device_detail(
    url_slug: str,
    device_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed information about a specific device.
    Returns different levels of detail based on access.
    """
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile or not vendor_profile.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor page not found"
        )
    
    # Get device
    result = await db.execute(
        select(VendorDevice)
        .where(
            and_(
                VendorDevice.id == device_id,
                VendorDevice.organization_id == vendor_profile.organization_id,
                VendorDevice.is_active == True
            )
        )
        .options(selectinload(VendorDevice.gudid_device))
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    # Track device view
    await track_page_view(
        vendor_profile_id=vendor_profile.id,
        page_type="device_detail",
        device_id=device_id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent")
    )
    
    # Build response based on access level
    response = {
        "id": device.id,
        "display_name": device.display_name,
        "manufacturer_name": device.manufacturer_name,
        "custom_name": device.custom_name,
        "training_required": device.training_required,
        "certification_required": device.certification_required,
        "is_available": device.is_available,
        "chat_enabled": vendor_profile.chat_enabled
    }
    
    # Add FDA data if available
    if device.gudid_device:
        response["fda_data"] = {
            "device_name": device.gudid_device.device_name,
            "device_class": device.gudid_device.device_class,
            "device_description": device.gudid_device.device_description,
            "mri_safety": device.gudid_device.mri_safety,
            "sterile": device.gudid_device.sterile,
            "single_use": device.gudid_device.single_use,
            "implantable": device.gudid_device.implantable,
            "life_supporting": device.gudid_device.life_supporting,
            "rx_required": device.gudid_device.rx_required
        }
    
    # Add public features and specifications
    if device.access_level == 'public':
        response["features"] = device.get_features_list()
        response["specifications"] = device.get_specifications_list()
        
        # Check public content settings
        if vendor_profile.get_public_settings("show_pricing", False):
            response["list_price"] = float(device.list_price) if device.list_price else None
            response["currency_code"] = device.currency_code
    else:
        response["access_restricted"] = True
        response["request_access_available"] = True
    
    return response


@router.get("/{url_slug}/content", response_model=List[VendorCustomContentResponse])
async def get_vendor_public_content(
    url_slug: str,
    content_type: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> List[VendorCustomContentResponse]:
    """
    Get public custom content for vendor page.
    Includes FAQs, Q&A pairs, announcements, etc.
    """
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile or not vendor_profile.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor page not found"
        )
    
    # Build content query
    query = select(VendorCustomContent).where(
        and_(
            VendorCustomContent.vendor_profile_id == vendor_profile.id,
            VendorCustomContent.is_active == True,
            VendorCustomContent.is_public == True
        )
    )
    
    # Apply filters
    if content_type:
        query = query.where(VendorCustomContent.content_type == content_type)
    
    if category:
        query = query.where(VendorCustomContent.category == category)
    
    # Order by display order and featured status
    query = query.order_by(
        VendorCustomContent.is_featured.desc(),
        VendorCustomContent.display_order,
        VendorCustomContent.created_at.desc()
    )
    
    # Execute query
    result = await db.execute(query)
    content_items = result.scalars().all()
    
    return content_items


@router.post("/{url_slug}/lead")
async def capture_vendor_lead(
    url_slug: str,
    lead_data: VendorLeadCapture,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Capture lead from vendor page.
    This is our main value proposition for vendors.
    """
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile or not vendor_profile.lead_capture_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lead capture not available"
        )
    
    # Check for duplicate lead
    existing = await db.execute(
        select(VendorLead)
        .where(
            and_(
                VendorLead.vendor_profile_id == vendor_profile.id,
                VendorLead.email == lead_data.email,
                VendorLead.status != 'lost'
            )
        )
    )
    if existing.scalar_one_or_none():
        return {"success": True, "message": "Thank you for your interest!"}
    
    # Create new lead
    lead = VendorLead(
        vendor_profile_id=vendor_profile.id,
        organization_id=vendor_profile.organization_id,
        email=lead_data.email,
        first_name=lead_data.first_name,
        last_name=lead_data.last_name,
        phone=lead_data.phone,
        organization_name=lead_data.organization_name,
        organization_type=lead_data.organization_type,
        job_title=lead_data.job_title,
        department=lead_data.department,
        role=lead_data.role,
        city=lead_data.city,
        state_province=lead_data.state_province,
        country=lead_data.country,
        source_type=lead_data.source_type,
        source_url=lead_data.source_url,
        device_id=lead_data.device_id,
        referrer_url=lead_data.referrer_url,
        utm_source=lead_data.utm_source,
        utm_medium=lead_data.utm_medium,
        utm_campaign=lead_data.utm_campaign,
        interested_devices=lead_data.interested_devices,
        search_queries=lead_data.search_queries,
        email_opt_in=lead_data.email_opt_in,
        phone_opt_in=lead_data.phone_opt_in,
        preferred_contact_method=lead_data.preferred_contact_method,
        preferred_contact_time=lead_data.preferred_contact_time,
        consent_given=lead_data.consent_given,
        privacy_policy_version=lead_data.privacy_policy_version,
        consent_timestamp=datetime.utcnow() if lead_data.consent_given else None,
        consent_ip=get_client_ip(request),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        session_id=request.headers.get("X-Session-ID")
    )
    
    # Calculate initial lead score
    lead.lead_score = lead.calculate_lead_score()
    
    db.add(lead)
    await db.commit()
    
    # Create initial activity
    activity = VendorLeadActivity(
        lead_id=lead.id,
        activity_type="lead_captured",
        activity_description=f"Lead captured from {lead_data.source_type}",
        metadata={
            "source": lead_data.source_type,
            "device_id": lead_data.device_id,
            "utm_source": lead_data.utm_source,
            "utm_medium": lead_data.utm_medium,
            "utm_campaign": lead_data.utm_campaign
        }
    )
    db.add(activity)
    await db.commit()
    
    # Track lead capture
    await track_lead_capture(
        vendor_profile_id=vendor_profile.id,
        lead_id=lead.id,
        source_type=lead_data.source_type
    )
    
    # TODO: Send notification to vendor if configured
    # TODO: Send welcome email to lead if opted in
    
    logger.info(f"Lead captured for vendor {url_slug}: {lead.email}")
    
    return {
        "success": True,
        "message": "Thank you for your interest! A representative will contact you soon.",
        "lead_id": lead.id
    }


@router.get("/{url_slug}/chat/knowledge")
async def get_vendor_chat_knowledge(
    url_slug: str,
    device_id: Optional[int] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get public Q&A knowledge for vendor chat.
    This supplements the RAG system with vendor-specific answers.
    """
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True,
                VendorProfile.chat_enabled == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor chat not available"
        )
    
    # Build knowledge query
    query = select(VendorChatKnowledge).where(
        and_(
            VendorChatKnowledge.vendor_profile_id == vendor_profile.id,
            VendorChatKnowledge.is_active == True,
            VendorChatKnowledge.approved == True,
            VendorChatKnowledge.is_public == True
        )
    )
    
    # Apply filters
    if device_id:
        query = query.where(
            or_(
                VendorChatKnowledge.device_id == device_id,
                VendorChatKnowledge.device_id.is_(None)
            )
        )
    
    if category:
        query = query.where(VendorChatKnowledge.category == category)
    
    # Order by usage and effectiveness
    query = query.order_by(
        VendorChatKnowledge.usage_count.desc(),
        VendorChatKnowledge.helpful_count.desc()
    )
    
    # Execute query
    result = await db.execute(query.limit(50))  # Limit to top 50 Q&As
    knowledge_items = result.scalars().all()
    
    # Format response
    response = []
    for item in knowledge_items:
        response.append({
            "id": item.id,
            "question": item.question,
            "answer": item.answer,
            "category": item.category,
            "device_id": item.device_id,
            "keywords": item.keywords,
            "effectiveness_score": item.effectiveness_score
        })
    
    return response


@router.get("/directory")
async def get_vendor_directory(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    specialties: Optional[List[str]] = Query(None),
    featured_only: bool = False,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get vendor directory for discovery.
    Lists all active vendor profiles.
    """
    # Build query
    query = select(VendorProfile).where(
        and_(
            VendorProfile.is_active == True,
            VendorProfile.published_at.isnot(None),
            VendorProfile.deleted_at.is_(None)
        )
    )
    
    # Apply filters
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                VendorProfile.display_name.ilike(search_term),
                VendorProfile.tagline.ilike(search_term),
                VendorProfile.description.ilike(search_term)
            )
        )
    
    if specialties:
        # Filter by any matching specialty
        query = query.where(
            VendorProfile.specialties.overlap(specialties)
        )
    
    if featured_only:
        query = query.where(VendorProfile.is_featured == True)
    
    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total_count = count_result.scalar()
    
    # Order by featured first, then alphabetically
    query = query.order_by(
        VendorProfile.is_featured.desc(),
        VendorProfile.display_name
    )
    
    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    vendors = result.scalars().all()
    
    # Format response
    vendor_list = []
    for vendor in vendors:
        vendor_list.append({
            "id": vendor.id,
            "display_name": vendor.display_name,
            "url_slug": vendor.url_slug,
            "tagline": vendor.tagline,
            "logo_url": vendor.logo_url,
            "specialties": vendor.specialties,
            "is_featured": vendor.is_featured,
            "total_devices": vendor.total_devices,
            "url": vendor.full_url
        })
    
    return {
        "vendors": vendor_list,
        "total_count": total_count,
        "page": page,
        "limit": limit,
        "total_pages": (total_count + limit - 1) // limit
    }
