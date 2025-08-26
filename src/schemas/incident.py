"""
Pydantic schemas for incident management.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime


# Base schemas
class IncidentBase(BaseModel):
    device_id: int = Field(..., description="Device ID this incident relates to")
    incident_type: str = Field(..., description="Type: malfunction, damage, safety_issue, user_error, other")
    incident_date: datetime = Field(..., description="When the incident occurred")
    description: str = Field(..., description="Detailed description of the incident")
    patient_impact: Optional[str] = Field(None, description="Impact: none, minor, moderate, severe, death")
    urgency: str = Field(..., description="Urgency: critical, high, medium, low")
    serial_number: Optional[str] = Field(None, max_length=100, description="Device serial number")
    lot_number: Optional[str] = Field(None, max_length=100, description="Device lot number")
    location: Optional[str] = Field(None, max_length=255, description="Where incident occurred")
    witnesses: Optional[List[str]] = Field(None, description="List of witness names")


# Request schemas
class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(BaseModel):
    assigned_to: Optional[int] = Field(None, description="User ID to assign to")
    status: Optional[str] = Field(None, description="Status: open, assigned, in_progress, pending_info, resolved, closed")
    resolution_summary: Optional[str] = Field(None, description="How the incident was resolved")
    root_cause: Optional[str] = Field(None, description="Root cause analysis")
    corrective_actions: Optional[str] = Field(None, description="Actions taken to prevent recurrence")
    vendor_ticket_id: Optional[str] = Field(None, max_length=100, description="External ticket reference")
    fda_reportable: Optional[bool] = Field(None, description="Is FDA reporting required")
    fda_report_number: Optional[str] = Field(None, max_length=100, description="FDA report number if filed")


class IncidentCommentCreate(BaseModel):
    comment_text: str = Field(..., min_length=1, description="Comment content")
    is_internal: bool = Field(False, description="Internal note (not visible to reporter)")


# Response schemas
class IncidentResponse(IncidentBase):
    id: int
    ticket_number: str = Field(..., description="Unique ticket identifier")
    organization_id: int
    reported_by: int
    assigned_to: Optional[int] = None
    status: str = Field("open", description="Current status")
    resolution_summary: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_actions: Optional[str] = None
    vendor_ticket_id: Optional[str] = None
    fda_reportable: bool = Field(False)
    fda_report_number: Optional[str] = None
    is_overdue: bool = Field(..., description="Is past SLA")
    requires_fda_reporting: bool = Field(..., description="Calculated FDA requirement")
    response_time_minutes: Optional[int] = None
    resolution_time_hours: Optional[float] = None
    assigned_at: Optional[datetime] = None
    first_response_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class IncidentCommentResponse(BaseModel):
    id: int
    incident_id: int
    user_id: int
    user_name: Optional[str] = Field(None, description="Comment author name")
    user_role: Optional[str] = Field(None, description="Comment author role")
    comment_text: str
    is_internal: bool = Field(False)
    is_from_reporter: bool = Field(..., description="Is from incident reporter")
    is_from_assignee: bool = Field(..., description="Is from assigned agent")
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class IncidentList(BaseModel):
    incidents: List[IncidentResponse]
    total: int = Field(..., description="Total number of incidents")
    skip: int = Field(..., description="Number of incidents skipped")
    limit: int = Field(..., description="Maximum number of incidents returned")


class IncidentStats(BaseModel):
    total_incidents: int
    open_incidents: int
    overdue_incidents: int
    average_response_time_minutes: float
    average_resolution_time_hours: float
    by_type: Dict[str, int]
    by_urgency: Dict[str, int]
    by_status: Dict[str, int]
    
    model_config = ConfigDict(from_attributes=True)


# Attachment schemas
class AttachmentUpload(BaseModel):
    attachment_type: str = Field("image", description="Type: image, document, log")
    description: Optional[str] = Field(None, description="Attachment description")


class AttachmentResponse(BaseModel):
    id: int
    incident_id: int
    attachment_type: str
    file_url: str
    file_size_bytes: Optional[int] = None
    description: Optional[str] = None
    uploaded_by: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
