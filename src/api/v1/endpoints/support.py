"""
Support and incident management API endpoints.
Handles incident reporting, tracking, and communication.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
import logging

from src.api.deps import get_db, get_current_user
from src.db.models.user import User
from src.db.models.device_incident import DeviceIncident
from src.db.models.incident_attachment import IncidentAttachment, IncidentComment
from src.db.models.support_conversation import SupportConversation
from src.schemas.incident import (
    IncidentCreate,
    IncidentUpdate,
    IncidentResponse,
    IncidentList,
    IncidentCommentCreate,
    IncidentCommentResponse,
    IncidentStats
)
from src.schemas.support import (
    SupportConversationCreate,
    SupportConversationResponse,
    SupportConversationDetail,
    SupportMessageCreate,
    SupportMessageResponse,
    SupportMetrics
)
from src.services.support_service import SupportService
from src.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)
router = APIRouter()

# Create service instances for this router
support_service = SupportService()
analytics_service = AnalyticsService()


@router.post("/incidents", response_model=Dict[str, Any])
async def create_incident(
    request: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Create a new device incident report.
    
    - **device_id**: Device involved in the incident
    - **incident_type**: Type of incident (malfunction, damage, safety_issue, user_error, other)
    - **incident_date**: When the incident occurred
    - **description**: Detailed description of the incident
    - **urgency**: Urgency level (critical, high, medium, low)
    - **patient_impact**: Impact on patient (none, minor, moderate, severe, death)
    - **serial_number**: Device serial number (optional)
    - **lot_number**: Device lot number (optional)
    - **location**: Where the incident occurred
    - **witnesses**: List of witness names
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must belong to an organization to report incidents"
        )
    
    try:
        incident = await support_service.create_incident(
            db=db,
            device_id=request.device_id,
            reported_by=current_user.id,
            organization_id=current_user.organization_id,
            incident_type=request.incident_type,
            incident_date=request.incident_date,
            description=request.description,
            urgency=request.urgency,
            patient_impact=request.patient_impact,
            serial_number=request.serial_number,
            lot_number=request.lot_number,
            location=request.location,
            witnesses=request.witnesses
        )
        
        # Track analytics
        await analytics_service.track_event(
            db=db,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="incident_create",
            event_category="support",
            resource_type="incident",
            resource_id=str(incident.id),
            metadata={
                "device_id": request.device_id,
                "incident_type": request.incident_type,
                "urgency": request.urgency,
                "fda_reportable": incident.fda_reportable
            }
        )
        
        return {
            "id": incident.id,
            "ticket_number": incident.ticket_number,
            "status": incident.status,
            "assigned_to": incident.assigned_to,
            "fda_reportable": incident.fda_reportable,
            "created_at": incident.created_at.isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/incidents", response_model=List[Dict[str, Any]])
async def list_incidents(
    device_id: Optional[int] = None,
    status: Optional[str] = None,
    urgency: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    List incidents for the user's organization.
    
    - **device_id**: Filter by device
    - **status**: Filter by status (open, assigned, in_progress, pending_info, resolved, closed)
    - **urgency**: Filter by urgency (critical, high, medium, low)
    """
    # Build query
    stmt = select(DeviceIncident).where(
        DeviceIncident.organization_id == current_user.organization_id
    )
    
    # Apply filters
    if device_id:
        stmt = stmt.where(DeviceIncident.device_id == device_id)
    
    if status:
        stmt = stmt.where(DeviceIncident.status == status)
    
    if urgency:
        stmt = stmt.where(DeviceIncident.urgency == urgency)
    
    # Order by urgency and creation date
    urgency_order = func.case(
        (DeviceIncident.urgency == "critical", 1),
        (DeviceIncident.urgency == "high", 2),
        (DeviceIncident.urgency == "medium", 3),
        (DeviceIncident.urgency == "low", 4),
        else_=5
    )
    
    stmt = stmt.order_by(urgency_order, DeviceIncident.created_at.desc())
    stmt = stmt.offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    incidents = result.scalars().all()
    
    # Format response
    return [
        {
            "id": inc.id,
            "ticket_number": inc.ticket_number,
            "device_id": inc.device_id,
            "incident_type": inc.incident_type,
            "description": inc.description[:200] + "..." if len(inc.description) > 200 else inc.description,
            "urgency": inc.urgency,
            "status": inc.status,
            "patient_impact": inc.patient_impact,
            "fda_reportable": inc.fda_reportable,
            "reported_by": inc.reported_by,
            "assigned_to": inc.assigned_to,
            "created_at": inc.created_at.isoformat(),
            "updated_at": inc.updated_at.isoformat()
        }
        for inc in incidents
    ]


@router.get("/incidents/{incident_id}", response_model=Dict[str, Any])
async def get_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get detailed incident information including comments and attachments."""
    # Get incident
    incident = await db.get(DeviceIncident, incident_id)
    
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found"
        )
    
    # Check access
    if incident.organization_id != current_user.organization_id:
        if incident.reported_by != current_user.id and incident.assigned_to != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this incident"
            )
    
    # Get comments
    comments_stmt = select(IncidentComment).where(
        IncidentComment.incident_id == incident_id
    ).order_by(IncidentComment.created_at)
    
    comments_result = await db.execute(comments_stmt)
    comments = comments_result.scalars().all()
    
    # Get attachments
    attachments_stmt = select(IncidentAttachment).where(
        IncidentAttachment.incident_id == incident_id
    )
    
    attachments_result = await db.execute(attachments_stmt)
    attachments = attachments_result.scalars().all()
    
    # Format response
    return {
        "id": incident.id,
        "ticket_number": incident.ticket_number,
        "device_id": incident.device_id,
        "incident_type": incident.incident_type,
        "incident_date": incident.incident_date.isoformat(),
        "description": incident.description,
        "urgency": incident.urgency,
        "status": incident.status,
        "patient_impact": incident.patient_impact,
        "serial_number": incident.serial_number,
        "lot_number": incident.lot_number,
        "location": incident.location,
        "witnesses": incident.witnesses,
        "fda_reportable": incident.fda_reportable,
        "fda_report_number": incident.fda_report_number,
        "reported_by": incident.reported_by,
        "assigned_to": incident.assigned_to,
        "resolution_summary": incident.resolution_summary,
        "root_cause": incident.root_cause,
        "corrective_actions": incident.corrective_actions,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
        "first_response_at": incident.first_response_at.isoformat() if incident.first_response_at else None,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "comments": [
            {
                "id": comment.id,
                "user_id": comment.user_id,
                "comment_text": comment.comment_text,
                "is_internal": comment.is_internal,
                "created_at": comment.created_at.isoformat()
            }
            for comment in comments
        ],
        "attachments": [
            {
                "id": att.id,
                "attachment_type": att.attachment_type,
                "file_url": att.file_url,
                "file_size_bytes": att.file_size_bytes,
                "description": att.description,
                "uploaded_by": att.uploaded_by,
                "created_at": att.created_at.isoformat()
            }
            for att in attachments
        ]
    }


@router.put("/incidents/{incident_id}", response_model=Dict[str, Any])
async def update_incident(
    incident_id: int,
    update: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Update incident status and resolution details.
    
    - **status**: New status
    - **resolution_summary**: Summary of how the incident was resolved
    - **root_cause**: Root cause analysis
    - **corrective_actions**: Actions taken to prevent recurrence
    """
    try:
        incident = await support_service.update_incident_status(
            db=db,
            incident_id=incident_id,
            user_id=current_user.id,
            new_status=update.status,
            resolution_summary=update.resolution_summary,
            root_cause=update.root_cause,
            corrective_actions=update.corrective_actions
        )
        
        # Track analytics
        await analytics_service.track_event(
            db=db,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="incident_update",
            event_category="support",
            resource_type="incident",
            resource_id=str(incident_id),
            metadata={"new_status": update.status}
        )
        
        return {
            "id": incident.id,
            "ticket_number": incident.ticket_number,
            "status": incident.status,
            "updated_at": incident.updated_at.isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/incidents/{incident_id}/comments", response_model=Dict[str, Any])
async def add_incident_comment(
    incident_id: int,
    comment_text: str = Form(...),
    is_internal: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Add a comment to an incident.
    
    - **comment_text**: Comment text
    - **is_internal**: Whether this is an internal note (vendor only)
    """
    try:
        comment = await support_service.add_comment(
            db=db,
            incident_id=incident_id,
            user_id=current_user.id,
            comment_text=comment_text,
            is_internal=is_internal
        )
        
        return {
            "id": comment.id,
            "comment_text": comment.comment_text,
            "is_internal": comment.is_internal,
            "created_at": comment.created_at.isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/incidents/{incident_id}/attachments", response_model=Dict[str, Any])
async def upload_incident_attachment(
    incident_id: int,
    file: UploadFile = File(...),
    attachment_type: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Upload an attachment to an incident.
    
    - **file**: File to upload (image, document)
    - **attachment_type**: Type of attachment (photo, document, report)
    - **description**: Optional description
    """
    # Validate attachment type
    valid_types = ["photo", "document", "report", "other"]
    if attachment_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid attachment type. Must be one of: {', '.join(valid_types)}"
        )
    
    # Read file content
    content = await file.read()
    
    try:
        attachment = await support_service.add_attachment(
            db=db,
            incident_id=incident_id,
            user_id=current_user.id,
            file_content=content,
            filename=file.filename,
            attachment_type=attachment_type,
            description=description
        )
        
        return {
            "id": attachment.id,
            "attachment_type": attachment.attachment_type,
            "file_url": attachment.file_url,
            "file_size_bytes": attachment.file_size_bytes,
            "description": attachment.description,
            "created_at": attachment.created_at.isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/metrics", response_model=Dict[str, Any])
async def get_support_metrics(
    device_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get support metrics for the organization.
    
    - **device_id**: Filter by specific device
    - **start_date**: Start date for metrics
    - **end_date**: End date for metrics
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization required"
        )
    
    metrics = await support_service.get_incident_metrics(
        db=db,
        organization_id=current_user.organization_id,
        device_id=device_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return metrics


@router.get("/conversations/active", response_model=List[Dict[str, Any]])
async def get_active_support_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get active support chat conversations.
    For support agents to see their assigned chats.
    """
    # Check if user is a support agent
    if current_user.role not in ["vendor_admin", "vendor_rep", "super_admin"]:
        # Regular users see their own conversations
        stmt = select(SupportConversation).where(
            and_(
                SupportConversation.requester_id == current_user.id,
                SupportConversation.status.in_(["waiting", "active"])
            )
        )
    else:
        # Agents see assigned conversations
        stmt = select(SupportConversation).where(
            and_(
                SupportConversation.agent_id == current_user.id,
                SupportConversation.status == "active"
            )
        )
    
    stmt = stmt.order_by(SupportConversation.queue_entered_at)
    
    result = await db.execute(stmt)
    conversations = result.scalars().all()
    
    return [
        {
            "id": conv.id,
            "requester_id": conv.requester_id,
            "agent_id": conv.agent_id,
            "device_id": conv.device_id,
            "subject": conv.subject,
            "priority": conv.priority,
            "status": conv.status,
            "queue_entered_at": conv.queue_entered_at.isoformat(),
            "conversation_started_at": conv.conversation_started_at.isoformat() if conv.conversation_started_at else None,
            "wait_time_seconds": conv.wait_time_seconds
        }
        for conv in conversations
    ]


@router.post("/conversations/{conversation_id}/rate", response_model=Dict[str, str])
async def rate_support_conversation(
    conversation_id: int,
    rating: int = Query(..., ge=1, le=5),
    comment: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Rate a completed support conversation.
    
    - **rating**: Rating from 1-5
    - **comment**: Optional feedback comment
    """
    conversation = await db.get(SupportConversation, conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.requester_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester can rate the conversation"
        )
    
    if conversation.status not in ["resolved", "abandoned"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only rate completed conversations"
        )
    
    # Update rating
    conversation.satisfaction_rating = rating
    conversation.satisfaction_comment = comment
    
    await db.commit()
    
    return {"message": "Thank you for your feedback"}
