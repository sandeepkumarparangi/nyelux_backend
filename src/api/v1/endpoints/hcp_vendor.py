"""
HCP Vendor Interaction API endpoints.
For healthcare professionals to interact with vendors.
Requires authentication and HCP role.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
import logging
import secrets

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.vendor_profile import (
    VendorProfile, VendorAccessRequest, VendorCustomContent
)
from src.db.models.vendor_service import VendorServiceRequest, VendorServiceCommunication
from src.db.models.vendor_device import VendorDevice
from src.schemas.vendor_portal import (
    VendorAccessRequestCreate, VendorAccessRequestResponse,
    ServiceRequestCreate, ServiceRequestResponse,
    ServiceCommunicationCreate, ServiceCommunicationResponse
)
from src.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hcp/vendor", tags=["hcp-vendor"])


# Helper function for HCP role checking
async def require_hcp(current_user: User = Depends(get_current_user)) -> User:
    """Require user to be healthcare professional."""
    if current_user.role not in ['physician', 'nurse', 'technician', 'clinical_admin', 'super_admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Healthcare professional access required"
        )
    return current_user


# Generate unique request number
def generate_request_number() -> str:
    """Generate unique service request number."""
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    random_suffix = secrets.token_hex(3).upper()
    return f"SR-{timestamp}-{random_suffix}"


# Access Request Endpoints

@router.post("/access-request", response_model=VendorAccessRequestResponse)
async def request_vendor_access(
    request_data: VendorAccessRequestCreate,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> VendorAccessRequestResponse:
    """
    Request access to vendor's restricted content.
    HCPs can request access to pricing, technical specs, etc.
    """
    # Verify vendor profile exists
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.id == request_data.vendor_profile_id,
                VendorProfile.is_active == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Check if user already has active access
    existing = await db.execute(
        select(VendorAccessRequest)
        .where(
            and_(
                VendorAccessRequest.vendor_profile_id == request_data.vendor_profile_id,
                VendorAccessRequest.user_id == current_user.id,
                VendorAccessRequest.request_type == request_data.request_type,
                VendorAccessRequest.status.in_(['pending', 'approved'])
            )
        )
    )
    
    if existing.scalar_one_or_none():
        existing_request = existing.scalar_one_or_none()
        if existing_request.status == 'approved' and existing_request.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have active access"
            )
        elif existing_request.status == 'pending':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have a pending access request"
            )
    
    # Create access request
    access_request = VendorAccessRequest(
        vendor_profile_id=request_data.vendor_profile_id,
        user_id=current_user.id,
        request_type=request_data.request_type,
        requested_access_level=request_data.requested_access_level,
        message=request_data.message,
        device_id=request_data.device_id,
        user_role=current_user.role,
        user_organization=current_user.organization.name if current_user.organization else None,
        user_department=current_user.department.name if current_user.department else None,
        user_title=current_user.title,
        request_source='hcp_portal',
        expires_at=datetime.utcnow() + timedelta(days=7)  # Auto-expire after 7 days
    )
    
    db.add(access_request)
    await db.commit()
    await db.refresh(access_request)
    
    # TODO: Send notification to vendor
    
    logger.info(f"Access request created: User {current_user.id} -> Vendor {vendor_profile.id}")
    
    return access_request


@router.get("/my-access-requests", response_model=List[VendorAccessRequestResponse])
async def get_my_access_requests(
    status: Optional[str] = None,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> List[VendorAccessRequestResponse]:
    """Get user's own access requests to vendors."""
    query = select(VendorAccessRequest).where(
        VendorAccessRequest.user_id == current_user.id
    ).options(
        selectinload(VendorAccessRequest.vendor_profile),
        selectinload(VendorAccessRequest.device)
    )
    
    if status:
        query = query.where(VendorAccessRequest.status == status)
    
    query = query.order_by(VendorAccessRequest.created_at.desc())
    
    result = await db.execute(query)
    requests = result.scalars().all()
    
    return requests


@router.get("/accessible-content/{vendor_profile_id}")
async def get_accessible_vendor_content(
    vendor_profile_id: int,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get vendor content accessible to the current HCP.
    Returns different content based on access level.
    """
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.id == vendor_profile_id,
                VendorProfile.is_active == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Check user's access level
    access_query = select(VendorAccessRequest).where(
        and_(
            VendorAccessRequest.vendor_profile_id == vendor_profile_id,
            VendorAccessRequest.user_id == current_user.id,
            VendorAccessRequest.status == 'approved'
        )
    ).order_by(VendorAccessRequest.reviewed_at.desc())
    
    result = await db.execute(access_query)
    access_requests = result.scalars().all()
    
    # Determine what content user can access
    accessible_content = {
        "public": True,  # Everyone gets public content
        "pricing": False,
        "technical_specs": False,
        "training_materials": False,
        "support_docs": False
    }
    
    granted_permissions = set()
    for request in access_requests:
        if request.is_active:
            # Collect all granted permissions
            if request.granted_permissions:
                for perm in request.granted_permissions.get('permissions', []):
                    granted_permissions.add(perm)
    
    # Check role-based access from vendor's access tiers
    role_permissions = vendor_profile.get_access_tier_permissions(current_user.role)
    granted_permissions.update(role_permissions)
    
    # Update accessible content
    for perm in granted_permissions:
        if perm in accessible_content:
            accessible_content[perm] = True
    
    # Get content based on access
    content_query = select(VendorCustomContent).where(
        and_(
            VendorCustomContent.vendor_profile_id == vendor_profile_id,
            VendorCustomContent.is_active == True
        )
    )
    
    # Filter by access level
    if not accessible_content.get('training_materials'):
        content_query = content_query.where(
            VendorCustomContent.content_type != 'training'
        )
    
    # Apply role-based filtering
    content_query = content_query.where(
        or_(
            VendorCustomContent.is_public == True,
            VendorCustomContent.required_roles.contains([current_user.role])
        )
    )
    
    result = await db.execute(content_query)
    content_items = result.scalars().all()
    
    return {
        "access_level": accessible_content,
        "content": [
            {
                "id": item.id,
                "type": item.content_type,
                "title": item.title,
                "content": item.content if accessible_content.get(item.content_type, False) else None,
                "category": item.category,
                "is_restricted": not item.is_public
            }
            for item in content_items
        ]
    }


# Service Request Endpoints

@router.post("/service-request", response_model=ServiceRequestResponse)
async def create_service_request(
    request_data: ServiceRequestCreate,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> ServiceRequestResponse:
    """
    Create service request to vendor.
    HCPs can request maintenance, training, demos, etc.
    """
    # Verify vendor profile exists
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.id == request_data.vendor_profile_id,
                VendorProfile.is_active == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # Verify device if specified
    if request_data.device_id:
        device_result = await db.execute(
            select(VendorDevice)
            .where(
                and_(
                    VendorDevice.id == request_data.device_id,
                    VendorDevice.organization_id == vendor_profile.organization_id
                )
            )
        )
        if not device_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )
    
    # Create service request
    service_request = VendorServiceRequest(
        request_number=generate_request_number(),
        vendor_profile_id=request_data.vendor_profile_id,
        organization_id=vendor_profile.organization_id,
        requester_id=current_user.id,
        requester_organization_id=current_user.organization_id,
        service_type=request_data.service_type,
        urgency=request_data.urgency,
        device_id=request_data.device_id,
        device_serial_number=request_data.device_serial_number,
        device_location=request_data.device_location,
        issue_description=request_data.issue_description,
        symptoms=request_data.symptoms,
        error_codes=request_data.error_codes,
        preferred_dates=request_data.preferred_dates,
        availability_notes=request_data.availability_notes,
        on_site_required=request_data.on_site_required,
        status='pending'
    )
    
    # Calculate SLA deadline
    service_request.sla_deadline = service_request.calculate_sla_deadline()
    
    db.add(service_request)
    await db.commit()
    await db.refresh(service_request)
    
    # Create initial communication
    initial_message = VendorServiceCommunication(
        service_request_id=service_request.id,
        sender_id=current_user.id,
        sender_type='hcp',
        message_type='text',
        message=request_data.issue_description
    )
    db.add(initial_message)
    await db.commit()
    
    # TODO: Send notification to vendor
    
    logger.info(f"Service request created: {service_request.request_number}")
    
    return service_request


@router.get("/my-service-requests", response_model=List[ServiceRequestResponse])
async def get_my_service_requests(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> List[ServiceRequestResponse]:
    """Get user's service requests to vendors."""
    query = select(VendorServiceRequest).where(
        VendorServiceRequest.requester_id == current_user.id
    ).options(
        selectinload(VendorServiceRequest.vendor_profile),
        selectinload(VendorServiceRequest.device),
        selectinload(VendorServiceRequest.assigned_rep)
    )
    
    if status:
        query = query.where(VendorServiceRequest.status == status)
    
    query = query.order_by(
        VendorServiceRequest.urgency,
        VendorServiceRequest.created_at.desc()
    )
    
    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    requests = result.scalars().all()
    
    return requests


@router.get("/service-request/{request_number}")
async def get_service_request_details(
    request_number: str,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get detailed service request information."""
    result = await db.execute(
        select(VendorServiceRequest)
        .where(
            and_(
                VendorServiceRequest.request_number == request_number,
                VendorServiceRequest.requester_id == current_user.id
            )
        )
        .options(
            selectinload(VendorServiceRequest.vendor_profile),
            selectinload(VendorServiceRequest.device),
            selectinload(VendorServiceRequest.assigned_rep),
            selectinload(VendorServiceRequest.communications)
        )
    )
    service_request = result.scalar_one_or_none()
    
    if not service_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service request not found"
        )
    
    # Format response
    return {
        "request": {
            "request_number": service_request.request_number,
            "service_type": service_request.service_type,
            "urgency": service_request.urgency,
            "status": service_request.status,
            "issue_description": service_request.issue_description,
            "device": {
                "id": service_request.device.id if service_request.device else None,
                "name": service_request.device.display_name if service_request.device else None,
                "serial_number": service_request.device_serial_number,
                "location": service_request.device_location
            },
            "scheduled_date": service_request.scheduled_date,
            "assigned_rep": {
                "id": service_request.assigned_rep.id if service_request.assigned_rep else None,
                "name": f"{service_request.assigned_rep.first_name} {service_request.assigned_rep.last_name}" 
                        if service_request.assigned_rep else None
            },
            "sla_deadline": service_request.sla_deadline,
            "is_overdue": service_request.is_overdue,
            "created_at": service_request.created_at,
            "updated_at": service_request.updated_at
        },
        "communications": [
            {
                "id": comm.id,
                "sender_type": comm.sender_type,
                "message_type": comm.message_type,
                "message": comm.message,
                "attachments": comm.attachments,
                "created_at": comm.created_at
            }
            for comm in service_request.communications
            if not comm.is_internal  # Don't show internal vendor notes
        ]
    }


@router.post("/service-request/{request_number}/message")
async def add_service_request_message(
    request_number: str,
    message_data: ServiceCommunicationCreate,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> ServiceCommunicationResponse:
    """Add message to service request."""
    # Get service request
    result = await db.execute(
        select(VendorServiceRequest)
        .where(
            and_(
                VendorServiceRequest.request_number == request_number,
                VendorServiceRequest.requester_id == current_user.id
            )
        )
    )
    service_request = result.scalar_one_or_none()
    
    if not service_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service request not found"
        )
    
    # Create communication
    communication = VendorServiceCommunication(
        service_request_id=service_request.id,
        sender_id=current_user.id,
        sender_type='hcp',
        message_type=message_data.message_type,
        message=message_data.message,
        attachments=message_data.attachments,
        proposed_dates=message_data.proposed_dates
    )
    
    db.add(communication)
    await db.commit()
    await db.refresh(communication)
    
    # TODO: Send notification to assigned rep
    
    return communication


@router.post("/service-request/{request_number}/feedback")
async def submit_service_feedback(
    request_number: str,
    rating: int = Query(..., ge=1, le=5),
    feedback: Optional[str] = None,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """Submit feedback for completed service request."""
    # Get service request
    result = await db.execute(
        select(VendorServiceRequest)
        .where(
            and_(
                VendorServiceRequest.request_number == request_number,
                VendorServiceRequest.requester_id == current_user.id,
                VendorServiceRequest.status == 'completed'
            )
        )
    )
    service_request = result.scalar_one_or_none()
    
    if not service_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Completed service request not found"
        )
    
    # Update feedback
    service_request.satisfaction_rating = rating
    service_request.satisfaction_feedback = feedback
    
    # Add feedback as communication
    feedback_message = VendorServiceCommunication(
        service_request_id=service_request.id,
        sender_id=current_user.id,
        sender_type='hcp',
        message_type='feedback_request',
        message=f"Rating: {rating}/5. Feedback: {feedback or 'No additional feedback'}",
        metadata={"rating": rating}
    )
    db.add(feedback_message)
    
    await db.commit()
    
    return {"message": "Feedback submitted successfully"}


# Vendor Following/Subscription

@router.post("/follow/{vendor_profile_id}")
async def follow_vendor(
    vendor_profile_id: int,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """Follow/subscribe to a vendor for updates."""
    # This would typically update a user preference or create a subscription record
    # For now, we'll store in user's notification preferences
    
    # Verify vendor exists
    result = await db.execute(
        select(VendorProfile)
        .where(
            and_(
                VendorProfile.id == vendor_profile_id,
                VendorProfile.is_active == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    # TODO: Implement actual subscription mechanism
    # For now, we'll just log it
    logger.info(f"User {current_user.id} followed vendor {vendor_profile_id}")
    
    return {"message": f"Successfully followed {vendor_profile.display_name}"}


@router.delete("/unfollow/{vendor_profile_id}")
async def unfollow_vendor(
    vendor_profile_id: int,
    current_user: User = Depends(require_hcp),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """Unfollow/unsubscribe from a vendor."""
    # TODO: Implement actual unsubscription mechanism
    logger.info(f"User {current_user.id} unfollowed vendor {vendor_profile_id}")
    
    return {"message": "Successfully unfollowed vendor"}
