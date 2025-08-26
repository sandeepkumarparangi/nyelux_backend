"""
Pydantic schemas for support and live chat.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime


# Base schemas
class SupportConversationBase(BaseModel):
    device_id: Optional[int] = Field(None, description="Device this support request relates to")
    subject: Optional[str] = Field(None, max_length=500, description="Support request subject")
    priority: str = Field("medium", description="Priority: low, medium, high, urgent")
    channel: str = Field("chat", description="Support channel: chat, video, phone")


class SupportMessageBase(BaseModel):
    message_content: str = Field(..., description="Message text content")
    message_type: str = Field("text", description="Type: text, image, file")
    attachment_url: Optional[str] = Field(None, description="URL for attachments")


# Request schemas
class SupportConversationCreate(SupportConversationBase):
    pass


class SupportMessageCreate(SupportMessageBase):
    pass


class AgentAvailabilityUpdate(BaseModel):
    available: bool = Field(..., description="Is agent available")
    available_channels: List[str] = Field(..., description="Channels agent can handle")
    max_capacity: int = Field(5, ge=1, le=20, description="Max concurrent conversations")
    skills: Optional[List[str]] = Field(None, description="Agent skills/specialties")
    languages: Optional[List[str]] = Field(None, description="Languages agent speaks")


# Response schemas
class SupportConversationResponse(SupportConversationBase):
    id: int
    requester_id: int
    agent_id: Optional[int] = None
    status: str = Field(..., description="Status: waiting, active, on_hold, resolved, abandoned")
    queue_entered_at: datetime
    conversation_started_at: Optional[datetime] = None
    conversation_ended_at: Optional[datetime] = None
    wait_time_seconds: Optional[int] = None
    resolution_time_seconds: Optional[int] = None
    satisfaction_rating: Optional[int] = Field(None, ge=1, le=5)
    satisfaction_comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class SupportMessageResponse(SupportMessageBase):
    id: int
    conversation_id: int
    sender_id: int
    sender_name: Optional[str] = Field(None, description="Sender's display name")
    sender_role: Optional[str] = Field(None, description="Sender's role")
    is_automated: bool = Field(False, description="Is this an automated message")
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class SupportConversationDetail(SupportConversationResponse):
    messages: List[SupportMessageResponse] = Field(..., description="Conversation messages")
    requester_name: Optional[str] = Field(None, description="Requester's name")
    agent_name: Optional[str] = Field(None, description="Agent's name")
    device_name: Optional[str] = Field(None, description="Device name if applicable")
    
    model_config = ConfigDict(from_attributes=True)


class AgentAvailabilityResponse(BaseModel):
    id: int
    agent_id: int
    agent_name: str
    organization_id: int
    available: bool
    available_channels: List[str]
    current_capacity: int = Field(..., description="Current active conversations")
    max_capacity: int = Field(..., description="Maximum capacity")
    skills: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    last_status_change: datetime
    
    model_config = ConfigDict(from_attributes=True)


class SupportQueueStatus(BaseModel):
    waiting_count: int = Field(..., description="Number of people waiting")
    average_wait_time_seconds: int = Field(..., description="Average wait time")
    available_agents: int = Field(..., description="Number of available agents")
    estimated_wait_seconds: int = Field(..., description="Estimated wait for new request")
    
    model_config = ConfigDict(from_attributes=True)


class SupportMetrics(BaseModel):
    total_conversations: int
    average_wait_time_seconds: float
    average_resolution_time_seconds: float
    satisfaction_average: Optional[float] = None
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    by_channel: Dict[str, int]
    hourly_distribution: Dict[int, int] = Field(..., description="Conversations by hour of day")
    
    model_config = ConfigDict(from_attributes=True)
