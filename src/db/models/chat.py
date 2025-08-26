from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, DECIMAL,
    Index, CheckConstraint
)
from sqlalchemy.orm import relationship

from src.db.base_class import Base

class ChatConversation(Base):
    """
    AI chat conversation management.
    Tracks conversations between users and the AI assistant.
    """
    __tablename__ = "chat_conversations"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User and device association
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True, index=True)
    
    # Conversation metadata
    title = Column(String(255), nullable=True)
    context_type = Column(String(50), nullable=True)  # device_support, general_inquiry, training
    status = Column(String(20), default='active', nullable=False)
    
    # Usage tracking
    total_messages = Column(Integer, default=0, nullable=False)
    total_tokens_used = Column(Integer, default=0, nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="chat_conversations")
    device = relationship("VendorDevice", back_populates="chat_conversations")
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.created_at")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived', 'deleted')", name='check_conversation_status'),
        CheckConstraint("total_messages >= 0", name='check_messages_positive'),
        CheckConstraint("total_tokens_used >= 0", name='check_tokens_positive'),
        Index('idx_user_last_message', 'user_id', 'last_message_at'),
        Index('idx_conversation_status', 'status'),
    )
    
    @property
    def is_active(self) -> bool:
        """Check if conversation is active"""
        return self.status == 'active'
    
    @property
    def estimated_cost(self) -> float:
        """Estimate cost based on token usage"""
        # GPT-4 pricing (approximate)
        cost_per_1k_tokens = 0.03  # Average of input/output pricing
        return (self.total_tokens_used / 1000) * cost_per_1k_tokens
    
    def add_message(self, role: str, content: str, tokens_used: int = 0):
        """Add a message to the conversation"""
        from datetime import datetime
        self.total_messages += 1
        self.total_tokens_used += tokens_used
        self.last_message_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "title": self.title or f"Conversation {self.id}",
            "context_type": self.context_type,
            "status": self.status,
            "total_messages": self.total_messages,
            "total_tokens_used": self.total_tokens_used,
            "estimated_cost": round(self.estimated_cost, 2),
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<ChatConversation {self.id}: {self.title or 'Untitled'}>"


class ChatMessage(Base):
    """
    Individual chat messages within a conversation.
    """
    __tablename__ = "chat_messages"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Conversation association
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id"), nullable=False, index=True)
    
    # Message content
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    
    # AI metadata
    tokens_used = Column(Integer, nullable=True)
    model_used = Column(String(50), nullable=True)
    
    # Quality metrics
    has_citations = Column(Boolean, default=False, nullable=False)
    confidence_score = Column(DECIMAL(3, 2), nullable=True)  # 0.00 to 1.00
    
    # User feedback
    feedback_rating = Column(Integer, nullable=True)  # 1-5 stars
    feedback_comment = Column(Text, nullable=True)
    
    # Relationships
    conversation = relationship("ChatConversation", back_populates="messages")
    citations = relationship("ChatCitation", back_populates="message", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name='check_message_role'),
        CheckConstraint("tokens_used >= 0", name='check_message_tokens_positive'),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", name='check_confidence_range'),
        CheckConstraint("feedback_rating >= 1 AND feedback_rating <= 5", name='check_rating_range'),
        Index('idx_conversation_created', 'conversation_id', 'created_at'),
    )
    
    @property
    def is_from_user(self) -> bool:
        """Check if message is from user"""
        return self.role == 'user'
    
    @property
    def is_from_assistant(self) -> bool:
        """Check if message is from assistant"""
        return self.role == 'assistant'
    
    @property
    def has_positive_feedback(self) -> bool:
        """Check if message has positive feedback"""
        return self.feedback_rating is not None and self.feedback_rating >= 4
    
    def to_dict(self, include_citations: bool = False) -> dict:
        """Convert to dictionary for API responses"""
        result = {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "tokens_used": self.tokens_used,
            "model_used": self.model_used,
            "has_citations": self.has_citations,
            "confidence_score": float(self.confidence_score) if self.confidence_score else None,
            "feedback_rating": self.feedback_rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_citations and self.citations:
            result["citations"] = [citation.to_dict() for citation in self.citations]
        
        return result
    
    def __repr__(self):
        return f"<ChatMessage {self.id}: {self.role}>"


class ChatCitation(Base):
    """
    Source citations for AI responses.
    Links to documents, videos, or other sources.
    """
    __tablename__ = "chat_citations"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Message association
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    
    # Citation details
    source_type = Column(String(50), nullable=False)  # document, video, gudid, manual_entry
    source_id = Column(String(255), nullable=True)  # ID of the source
    source_title = Column(Text, nullable=True)
    
    # Location within source
    page_number = Column(Integer, nullable=True)
    section_reference = Column(Text, nullable=True)
    excerpt = Column(Text, nullable=True)
    
    # Quality metric
    relevance_score = Column(DECIMAL(3, 2), nullable=True)  # 0.00 to 1.00
    
    # Relationships
    message = relationship("ChatMessage", back_populates="citations")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("source_type IN ('document', 'video', 'gudid', 'manual_entry')", name='check_citation_type'),
        CheckConstraint("relevance_score >= 0 AND relevance_score <= 1", name='check_relevance_range'),
        Index('idx_message_citations', 'message_id'),
    )
    
    def get_source_url(self) -> str:
        """Get URL to the source"""
        # This would be implemented based on source type
        # For now, return a placeholder
        if self.source_type == 'document':
            return f"/api/v1/documents/{self.source_id}"
        elif self.source_type == 'video':
            return f"/api/v1/videos/{self.source_id}"
        elif self.source_type == 'gudid':
            return f"/api/v1/devices/gudid/{self.source_id}"
        return None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_title": self.source_title,
            "source_url": self.get_source_url(),
            "page_number": self.page_number,
            "section_reference": self.section_reference,
            "excerpt": self.excerpt,
            "relevance_score": float(self.relevance_score) if self.relevance_score else None,
        }
    
    def __repr__(self):
        return f"<ChatCitation {self.id}: {self.source_type}>"
