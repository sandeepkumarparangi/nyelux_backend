"""
Pydantic schemas for chat functionality.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from src.schemas.base import BaseSchema


# Base schemas
class ConversationBase(BaseSchema):
    device_id: Optional[int] = Field(None, description="Associated device ID")
    title: Optional[str] = Field(None, max_length=255, description="Conversation title")
    context_type: Optional[str] = Field(None, description="Context type: device_support, general_inquiry, training")


class MessageBase(BaseSchema):
    content: str = Field(..., description="Message content")


class CitationBase(BaseSchema):
    source_type: str = Field(..., description="Type of source: document, video, gudid, manual_entry")
    source_id: Optional[str] = Field(None, description="ID of the source")
    source_title: Optional[str] = Field(None, description="Title of the source")
    page_number: Optional[int] = Field(None, description="Page number if applicable")
    section_reference: Optional[str] = Field(None, description="Section reference")
    excerpt: Optional[str] = Field(None, description="Relevant excerpt")
    relevance_score: Optional[float] = Field(None, ge=0, le=1, description="Relevance score 0-1")


# Request schemas
class ConversationCreate(ConversationBase):
    pass


class MessageCreate(MessageBase):
    attachments: Optional[List[str]] = Field(None, description="List of attachment URLs")


# Response schemas
class CitationResponse(CitationBase):
    id: int
    source_url: Optional[str] = Field(None, description="URL to the source")


class MessageResponse(MessageBase):
    id: int
    conversation_id: int
    role: str = Field(..., description="Message role: user, assistant, system")
    tokens_used: Optional[int] = Field(None, description="Tokens used for this message")
    model_used: Optional[str] = Field(None, description="AI model used")
    has_citations: bool = Field(False, description="Whether message has citations")
    confidence_score: Optional[float] = Field(None, description="Confidence score 0-1")
    feedback_rating: Optional[int] = Field(None, ge=1, le=5, description="User feedback rating 1-5")
    feedback_comment: Optional[str] = Field(None, description="User feedback comment")
    citations: Optional[List[CitationResponse]] = Field(None, description="Message citations")
    created_at: datetime


class ConversationResponse(ConversationBase):
    id: int
    user_id: int
    status: str = Field(..., description="Conversation status: active, archived, deleted")
    total_messages: int = Field(0, description="Total number of messages")
    total_tokens_used: int = Field(0, description="Total tokens used")
    estimated_cost: float = Field(0.0, description="Estimated cost in USD")
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseSchema):
    conversations: List[ConversationResponse]
    total: int = Field(..., description="Total number of conversations")
    skip: int = Field(..., description="Number of conversations skipped")
    limit: int = Field(..., description="Maximum number of conversations returned")


# Analytics schemas
class ConversationStats(BaseSchema):
    total_conversations: int
    active_conversations: int
    total_messages: int
    total_tokens_used: int
    estimated_total_cost: float
    average_messages_per_conversation: float
    average_satisfaction_rating: Optional[float] = None


class TokenUsage(BaseSchema):
    conversation_id: int
    period: str = Field(..., description="Period: daily, weekly, monthly")
    tokens_used: int
    estimated_cost: float
    message_count: int
