from sqlalchemy import (
    Column, Integer, String, ForeignKey, Text, Boolean, Index
)
from sqlalchemy.orm import relationship

from src.db.base_class import Base


class SupportMessage(Base):
    """
    Individual messages within support chat conversations.
    """
    __tablename__ = "support_messages"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Conversation association
    conversation_id = Column(Integer, ForeignKey("support_conversations.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Message content
    message_type = Column(String(20), nullable=False, default='text')
    message_content = Column(Text, nullable=False)
    attachment_url = Column(Text, nullable=True)
    
    # Message metadata
    is_automated = Column(Boolean, nullable=False, default=False, comment="System-generated message")
    
    # Relationships
    conversation = relationship("SupportConversation", back_populates="messages")
    sender = relationship("User", back_populates="support_messages")
    
    # Indexes
    __table_args__ = (
        Index('idx_support_msg_conversation', 'conversation_id', 'created_at'),
        Index('idx_support_msg_sender', 'sender_id', 'created_at'),
    )
    
    @property
    def is_from_agent(self) -> bool:
        """Check if message is from support agent"""
        if self.conversation and self.conversation.agent_id:
            return self.sender_id == self.conversation.agent_id
        return False
    
    @property
    def is_from_requester(self) -> bool:
        """Check if message is from the requester"""
        if self.conversation:
            return self.sender_id == self.conversation.requester_id
        return False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender.full_name if self.sender else None,
            "sender_role": "agent" if self.is_from_agent else "requester",
            "message_type": self.message_type,
            "message_content": self.message_content,
            "attachment_url": self.attachment_url,
            "is_automated": self.is_automated,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<SupportMessage {self.id}: {self.message_type}>"
