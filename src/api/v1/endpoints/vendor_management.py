"""
Vendor Management API endpoints.
For vendor admins to manage their profile, content, and leads.
Requires authentication and vendor role.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.orm import selectinload
import logging
import secrets

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.vendor_profile import (
    VendorProfile, VendorCustomContent, VendorAccessRequest,
    VendorPageAnalytics, VendorChatKnowledge
)
from src.db.models.vendor_lead import VendorLead, VendorLeadActivity
from src.db.models.vendor_service import (
    VendorServiceRequest, VendorServiceCommunication, VendorRepAvailability
)
from src.schemas.vendor_portal import (
    VendorProfileCreate, VendorProfileUpdate, VendorProfileResponse,
    VendorCustomContentCreate, VendorCustomContentUpdate, VendorCustomContentResponse,
    VendorAccessRequestReview, VendorAccessRequestResponse,
    VendorLeadUpdate, VendorLeadResponse, VendorLeadActivityCreate,
    ServiceRequestUpdate, ServiceRequestComplete, ServiceRequestResponse,
    ServiceCommunicationCreate, ServiceCommunicationResponse,
    VendorChatKnowledgeCreate, VendorChatKnowledgeUpdate, VendorChatKnowledgeResponse,
    RepAvailabilityCreate, RepAvailabilityUpdate, RepAvailabilityResponse,
    VendorPageAnalyticsResponse
)
from src.api.deps import get_current_user
# TODO: Implement file service
# from src.services.file_service import upload_file, delete_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vendor-admin", tags=["vendor-management"])


# Helper functions for role checking
async def require_vendor_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require user to be vendor admin."""
    if current_user.role not in ['vendor_admin', 'super_admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor admin access required"
        )
    return current_user


async def require_vendor_rep(current_user: User = Depends(get_current_user)) -> User:
    """Require user to be vendor rep or admin."""
    if current_user.role not in ['vendor_rep', 'vendor_admin', 'super_admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor representative access required"
        )
    return current_user


# Placeholder for file upload
async def upload_file(file, folder, max_size_mb):
    """Placeholder for file upload"""
    # TODO: Implement actual S3 upload
    return f"https://storage.nyelux.com/{folder}/{file.filename}"


async def delete_file(file_url):
    """Placeholder for file deletion"""
    # TODO: Implement actual S3 deletion
    pass


# Profile Management Endpoints

@router.get("/profile", response_model=VendorProfileResponse)
async def get_vendor_profile(
    current_user: User = Depends(require_vendor_admin),
    db: AsyncSession = Depends(get_db)
) -> VendorProfileResponse:
    """Get vendor's own profile."""
    result = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == current_user.organization_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    return profile


@router.post("/profile", response_model=VendorProfileResponse)
async def create_vendor_profile(
    profile_data: VendorProfileCreate,
    current_user: User = Depends(require_vendor_admin),
    db: AsyncSession = Depends(get_db)
) -> VendorProfileResponse:
    """
    Create vendor profile.
    Only super admin can create profiles for vendors.
    """
    # Check if user is super admin
    if current_user.role != 'super_admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can create vendor profiles"
        )
    
    # Check if profile already exists
    existing = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == profile_data.organization_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor profile already exists for this organization"
        )
    
    # Check if URL slug is unique
    slug_exists = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.url_slug == profile_data.url_slug)
    )
    if slug_exists.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL slug already in use"
        )
    
    # Create profile
    profile = VendorProfile(
        **profile_data.dict(),
        created_by=current_user.id,
        published_at=datetime.utcnow()  # Auto-publish on creation
    )
    
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    
    logger.info(f"Vendor profile created: {profile.url_slug}")
    
    return profile


# Lead Management Endpoints

@router.get("/leads", response_model=List[VendorLeadResponse])
async def get_vendor_leads(
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
    lead_score_min: Optional[int] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_vendor_rep),
    db: AsyncSession = Depends(get_db)
) -> List[VendorLeadResponse]:
    """Get leads for vendor."""
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == current_user.organization_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Build query
    query = select(VendorLead).where(
        VendorLead.vendor_profile_id == profile.id
    )
    
    # Apply filters
    if status:
        query = query.where(VendorLead.status == status)
    
    if assigned_to:
        query = query.where(VendorLead.assigned_to == assigned_to)
    elif current_user.role == 'vendor_rep':
        # Vendor reps only see their assigned leads
        query = query.where(VendorLead.assigned_to == current_user.id)
    
    if lead_score_min:
        query = query.where(VendorLead.lead_score >= lead_score_min)
    
    # Order by score and recency
    query = query.order_by(
        VendorLead.lead_score.desc(),
        VendorLead.created_at.desc()
    )
    
    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    leads = result.scalars().all()
    
    return leads


@router.put("/leads/{lead_id}")
async def update_lead(
    lead_id: int,
    lead_data: VendorLeadUpdate,
    current_user: User = Depends(require_vendor_rep),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Update lead status and information."""
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == current_user.organization_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Get lead
    result = await db.execute(
        select(VendorLead)
        .where(
            and_(
                VendorLead.id == lead_id,
                VendorLead.vendor_profile_id == profile.id
            )
        )
    )
    lead = result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    # Check permission
    if current_user.role == 'vendor_rep' and lead.assigned_to != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update leads assigned to you"
        )
    
    # Track status change
    old_status = lead.status
    
    # Update lead
    update_data = lead_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(lead, field, value)
    
    # Handle status-specific updates
    if lead_data.status and lead_data.status != old_status:
        if lead_data.status == 'contacted':
            lead.first_contact_at = lead.first_contact_at or datetime.utcnow()
            lead.last_contact_at = datetime.utcnow()
        elif lead_data.status == 'qualified':
            lead.qualified = True
            lead.qualified_at = datetime.utcnow()
            lead.qualified_by = current_user.id
        elif lead_data.status == 'converted':
            lead.converted = True
            lead.converted_at = datetime.utcnow()
    
    # Recalculate lead score
    lead.lead_score = lead.calculate_lead_score()
    
    lead.updated_at = datetime.utcnow()
    
    # Create activity log
    activity = VendorLeadActivity(
        lead_id=lead.id,
        activity_type='status_changed' if lead_data.status else 'note_added',
        activity_description=f"Status changed from {old_status} to {lead.status}" if lead_data.status else "Lead updated",
        user_id=current_user.id,
        metadata={
            "old_status": old_status,
            "new_status": lead.status,
            "updated_fields": list(update_data.keys())
        }
    )
    db.add(activity)
    
    await db.commit()
    
    return {
        "success": True,
        "lead_id": lead.id,
        "new_status": lead.status,
        "lead_score": lead.lead_score
    }


@router.post("/leads/{lead_id}/activity")
async def add_lead_activity(
    lead_id: int,
    activity_data: VendorLeadActivityCreate,
    current_user: User = Depends(require_vendor_rep),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Add activity to lead."""
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == current_user.organization_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Get lead
    result = await db.execute(
        select(VendorLead)
        .where(
            and_(
                VendorLead.id == lead_id,
                VendorLead.vendor_profile_id == profile.id
            )
        )
    )
    lead = result.scalar_one_or_none()
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    
    # Create activity
    activity = VendorLeadActivity(
        lead_id=lead_id,
        user_id=current_user.id,
        **activity_data.dict(exclude={'lead_id'})
    )
    
    # Update lead last contact
    if activity_data.activity_type in ['call_made', 'email_sent', 'meeting_held']:
        lead.last_contact_at = datetime.utcnow()
    
    db.add(activity)
    await db.commit()
    
    return {
        "success": True,
        "activity_id": activity.id,
        "lead_id": lead_id
    }


# Service Request Management

@router.get("/service-requests", response_model=List[ServiceRequestResponse])
async def get_service_requests(
    status: Optional[str] = None,
    urgency: Optional[str] = None,
    assigned_to_me: bool = False,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_vendor_rep),
    db: AsyncSession = Depends(get_db)
) -> List[ServiceRequestResponse]:
    """Get service requests for vendor."""
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == current_user.organization_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Build query
    query = select(VendorServiceRequest).where(
        VendorServiceRequest.vendor_profile_id == profile.id
    ).options(
        selectinload(VendorServiceRequest.requester),
        selectinload(VendorServiceRequest.device)
    )
    
    # Apply filters
    if status:
        query = query.where(VendorServiceRequest.status == status)
    
    if urgency:
        query = query.where(VendorServiceRequest.urgency == urgency)
    
    if assigned_to_me:
        query = query.where(VendorServiceRequest.assigned_rep_id == current_user.id)
    
    # Order by urgency and creation time
    query = query.order_by(
        VendorServiceRequest.urgency,
        VendorServiceRequest.created_at
    )
    
    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    requests = result.scalars().all()
    
    return requests


@router.put("/service-requests/{request_id}")
async def update_service_request(
    request_id: int,
    update_data: ServiceRequestUpdate,
    current_user: User = Depends(require_vendor_rep),
    db: AsyncSession = Depends(get_db)
) -> ServiceRequestResponse:
    """Update service request (assign, schedule, etc)."""
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == current_user.organization_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Get service request
    result = await db.execute(
        select(VendorServiceRequest)
        .where(
            and_(
                VendorServiceRequest.id == request_id,
                VendorServiceRequest.vendor_profile_id == profile.id
            )
        )
    )
    service_request = result.scalar_one_or_none()
    
    if not service_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service request not found"
        )
    
    # Track status changes
    old_status = service_request.status
    
    # Update request
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(service_request, field, value)
    
    # Handle status-specific logic
    if update_data.status and update_data.status != old_status:
        # Update status history
        if not service_request.status_history:
            service_request.status_history = []
        
        service_request.status_history.append({
            "status": update_data.status,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": current_user.id,
            "notes": update_data.assignment_notes
        })
        
        # Handle assignment
        if update_data.status == 'assigned' and update_data.assigned_rep_id:
            service_request.assigned_at = datetime.utcnow()
            
            # Calculate response time
            response_time = (datetime.utcnow() - service_request.created_at).total_seconds() / 60
            service_request.response_time_minutes = int(response_time)
    
    service_request.updated_at = datetime.utcnow()
    
    # Add communication log
    if update_data.status != old_status:
        communication = VendorServiceCommunication(
            service_request_id=request_id,
            sender_id=current_user.id,
            sender_type='vendor_rep',
            message_type='status_update',
            message=f"Status changed from {old_status} to {service_request.status}"
        )
        db.add(communication)
    
    await db.commit()
    await db.refresh(service_request)
    
    return service_request


@router.post("/service-requests/{request_id}/complete")
async def complete_service_request(
    request_id: int,
    completion_data: ServiceRequestComplete,
    current_user: User = Depends(require_vendor_rep),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Mark service request as completed."""
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == current_user.organization_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Get service request
    result = await db.execute(
        select(VendorServiceRequest)
        .where(
            and_(
                VendorServiceRequest.id == request_id,
                VendorServiceRequest.vendor_profile_id == profile.id,
                VendorServiceRequest.assigned_rep_id == current_user.id
            )
        )
    )
    service_request = result.scalar_one_or_none()
    
    if not service_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service request not found or not assigned to you"
        )
    
    # Complete the request
    service_request.status = 'completed'
    service_request.service_completed_at = datetime.utcnow()
    service_request.service_report = completion_data.service_report
    service_request.parts_used = completion_data.parts_used
    service_request.follow_up_required = completion_data.follow_up_required
    service_request.follow_up_notes = completion_data.follow_up_notes
    service_request.actual_cost = completion_data.actual_cost
    service_request.invoice_number = completion_data.invoice_number
    
    # Calculate resolution time
    resolution_time = (datetime.utcnow() - service_request.created_at).total_seconds() / 60
    service_request.resolution_time_minutes = int(resolution_time)
    
    # Check SLA
    if service_request.sla_deadline:
        service_request.sla_met = datetime.utcnow() <= service_request.sla_deadline
    
    # Add completion report as communication
    communication = VendorServiceCommunication(
        service_request_id=request_id,
        sender_id=current_user.id,
        sender_type='vendor_rep',
        message_type='completion_report',
        message=completion_data.service_report
    )
    db.add(communication)
    
    await db.commit()
    
    return {
        "success": True,
        "request_id": request_id,
        "completed_at": service_request.service_completed_at,
        "sla_met": service_request.sla_met
    }


# Analytics Endpoints

@router.get("/analytics/overview")
async def get_vendor_analytics_overview(
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(require_vendor_admin),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get analytics overview for vendor."""
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(VendorProfile.organization_id == current_user.organization_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Default date range (last 30 days)
    if not date_to:
        date_to = datetime.utcnow()
    if not date_from:
        date_from = date_to - timedelta(days=30)
    
    # Get analytics data
    analytics_query = select(
        func.sum(VendorPageAnalytics.page_views).label('total_page_views'),
        func.sum(VendorPageAnalytics.unique_visitors).label('total_unique_visitors'),
        func.sum(VendorPageAnalytics.leads_captured).label('total_leads'),
        func.sum(VendorPageAnalytics.access_requests).label('total_access_requests'),
        func.sum(VendorPageAnalytics.device_clicks).label('total_device_clicks'),
        func.sum(VendorPageAnalytics.document_downloads).label('total_downloads'),
        func.sum(VendorPageAnalytics.chat_initiations).label('total_chats'),
        func.avg(VendorPageAnalytics.avg_time_on_page).label('avg_time_on_page'),
        func.avg(VendorPageAnalytics.bounce_rate).label('avg_bounce_rate')
    ).where(
        and_(
            VendorPageAnalytics.vendor_profile_id == profile.id,
            VendorPageAnalytics.date >= date_from,
            VendorPageAnalytics.date <= date_to
        )
    )
    
    result = await db.execute(analytics_query)
    analytics = result.one()
    
    # Get lead statistics
    leads_query = select(
        func.count(VendorLead.id).label('total_leads'),
        func.count(VendorLead.id).filter(VendorLead.status == 'new').label('new_leads'),
        func.count(VendorLead.id).filter(VendorLead.qualified == True).label('qualified_leads'),
        func.count(VendorLead.id).filter(VendorLead.converted == True).label('converted_leads'),
        func.avg(VendorLead.lead_score).label('avg_lead_score')
    ).where(
        and_(
            VendorLead.vendor_profile_id == profile.id,
            VendorLead.created_at >= date_from,
            VendorLead.created_at <= date_to
        )
    )
    
    result = await db.execute(leads_query)
    lead_stats = result.one()
    
    # Get service request statistics
    service_query = select(
        func.count(VendorServiceRequest.id).label('total_requests'),
        func.count(VendorServiceRequest.id).filter(
            VendorServiceRequest.status == 'completed'
        ).label('completed_requests'),
        func.count(VendorServiceRequest.id).filter(
            VendorServiceRequest.sla_met == True
        ).label('sla_met_count'),
        func.avg(VendorServiceRequest.satisfaction_rating).label('avg_satisfaction')
    ).where(
        and_(
            VendorServiceRequest.vendor_profile_id == profile.id,
            VendorServiceRequest.created_at >= date_from,
            VendorServiceRequest.created_at <= date_to
        )
    )
    
    result = await db.execute(service_query)
    service_stats = result.one()
    
    return {
        "date_range": {
            "from": date_from.isoformat(),
            "to": date_to.isoformat()
        },
        "traffic": {
            "page_views": analytics.total_page_views or 0,
            "unique_visitors": analytics.total_unique_visitors or 0,
            "avg_time_on_page": float(analytics.avg_time_on_page or 0),
            "bounce_rate": float(analytics.avg_bounce_rate or 0)
        },
        "engagement": {
            "device_clicks": analytics.total_device_clicks or 0,
            "document_downloads": analytics.total_downloads or 0,
            "chat_initiations": analytics.total_chats or 0,
            "access_requests": analytics.total_access_requests or 0
        },
        "leads": {
            "total": lead_stats.total_leads or 0,
            "new": lead_stats.new_leads or 0,
            "qualified": lead_stats.qualified_leads or 0,
            "converted": lead_stats.converted_leads or 0,
            "avg_score": float(lead_stats.avg_lead_score or 0),
            "conversion_rate": (
                (lead_stats.converted_leads / lead_stats.total_leads * 100)
                if lead_stats.total_leads > 0 else 0
            )
        },
        "service": {
            "total_requests": service_stats.total_requests or 0,
            "completed": service_stats.completed_requests or 0,
            "sla_compliance": (
                (service_stats.sla_met_count / service_stats.completed_requests * 100)
                if service_stats.completed_requests > 0 else 100
            ),
            "satisfaction": float(service_stats.avg_satisfaction or 0)
        }
    }
