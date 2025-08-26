from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime

from src.db.base_class import Base


class SupportConversation(Base):
    """
    Real-time support chat sessions between users and vendor support agents.
    """
    __tablename__ = "support_conversations"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Participants
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True, index=True)
    
    # Conversation details
    subject = Column(String(500), nullable=True)
    priority = Column(String(20), nullable=False, default='medium')
    channel = Column(String(20), nullable=False, default='chat')
    status = Column(String(50), nullable=False, default='waiting')
    
    # Timing information
    queue_entered_at = Column(DateTime(timezone=True), nullable=False, server_default='now()')
    conversation_started_at = Column(DateTime(timezone=True), nullable=True)
    conversation_ended_at = Column(DateTime(timezone=True), nullable=True)
    wait_time_seconds = Column(Integer, nullable=True)
    resolution_time_seconds = Column(Integer, nullable=True)
    
    # Satisfaction metrics
    satisfaction_rating = Column(Integer, nullable=True)
    satisfaction_comment = Column(Text, nullable=True)
    
    # Relationships
    requester = relationship("User", foreign_keys=[requester_id], back_populates="support_conversations_as_requester")
    agent = relationship("User", foreign_keys=[agent_id], back_populates="support_conversations_as_agent")
    device = relationship("VendorDevice", back_populates="support_conversations")
    messages = relationship("SupportMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="SupportMessage.created_at")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name='check_support_priority'),
        CheckConstraint("channel IN ('chat', 'video', 'phone')", name='check_support_channel'),
        CheckConstraint("status IN ('waiting', 'active', 'on_hold', 'resolved', 'abandoned')", name='check_support_status'),
        CheckConstraint("satisfaction_rating >= 1 AND satisfaction_rating <= 5", name='check_satisfaction_rating'),
        CheckConstraint("wait_time_seconds >= 0", name='check_wait_time_positive'),
        CheckConstraint("resolution_time_seconds >= 0", name='check_resolution_time_positive'),
        Index('idx_support_status_priority', 'status', 'priority'),
        Index('idx_support_agent_active', 'agent_id', 'status'),
        Index('idx_support_queue_time', 'queue_entered_at'),
    )
    
    @property
    def is_active(self) -> bool:
        """Check if conversation is currently active"""
        return self.status == 'active'
    
    @property
    def is_waiting(self) -> bool:
        """Check if conversation is waiting for agent"""
        return self.status == 'waiting'
    
    @property
    def duration_seconds(self) -> int:
        """Calculate conversation duration in seconds"""
        if not self.conversation_started_at:
            return 0
        end_time = self.conversation_ended_at or datetime.utcnow()
        return int((end_time - self.conversation_started_at).total_seconds())
    
    def calculate_wait_time(self):
        """Calculate and set wait time"""
        if self.conversation_started_at:
            self.wait_time_seconds = int(
                (self.conversation_started_at - self.queue_entered_at).total_seconds()
            )
    
    def calculate_resolution_time(self):
        """Calculate and set resolution time"""
        if self.conversation_started_at and self.conversation_ended_at:
            self.resolution_time_seconds = int(
                (self.conversation_ended_at - self.conversation_started_at).total_seconds()
            )
    
    def start_conversation(self, agent_id: int):
        """Mark conversation as started with agent"""
        self.agent_id = agent_id
        self.status = 'active'
        self.conversation_started_at = datetime.utcnow()
        self.calculate_wait_time()
    
    def end_conversation(self, status: str = 'resolved'):
        """Mark conversation as ended"""
        self.status = status
        self.conversation_ended_at = datetime.utcnow()
        self.calculate_resolution_time()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "requester_id": self.requester_id,
            "agent_id": self.agent_id,
            "device_id": self.device_id,
            "subject": self.subject,
            "priority": self.priority,
            "channel": self.channel,
            "status": self.status,
            "queue_entered_at": self.queue_entered_at.isoformat() if self.queue_entered_at else None,
            "conversation_started_at": self.conversation_started_at.isoformat() if self.conversation_started_at else None,
            "conversation_ended_at": self.conversation_ended_at.isoformat() if self.conversation_ended_at else None,
            "wait_time_seconds": self.wait_time_seconds,
            "resolution_time_seconds": self.resolution_time_seconds,
            "duration_seconds": self.duration_seconds,
            "satisfaction_rating": self.satisfaction_rating,
            "message_count": len(self.messages) if self.messages else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<SupportConversation {self.id}: {self.status}>"
