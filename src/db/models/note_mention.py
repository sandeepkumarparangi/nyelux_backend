"""
Note mention tracking for team collaboration.
Handles @mentions in notes and related notifications.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index, 
    UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime

from src.db.base_class import Base


class NoteMention(Base):
    """
    Tracks @mentions in notes for notification and collaboration.
    """
    __tablename__ = "note_mentions"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Note association
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False)
    
    # Mentioned user
    mentioned_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Mentioning user (who created the mention)
    mentioned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Mention details
    mention_text = Column(String(500), nullable=False)  # The surrounding text context
    mention_position = Column(Integer, nullable=False)  # Character position in note content
    
    # Notification tracking
    notification_sent = Column(Boolean, nullable=False, default=False)
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # User interaction
    viewed = Column(Boolean, nullable=False, default=False)
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    note = relationship("Note", back_populates="mentions")
    mentioned_user = relationship("User", foreign_keys=[mentioned_user_id], back_populates="mentions_received")
    mentioned_by_user = relationship("User", foreign_keys=[mentioned_by_user_id], back_populates="mentions_created")
    
    # Indexes
    __table_args__ = (
        Index('idx_mention_note', 'note_id'),
        Index('idx_mention_user', 'mentioned_user_id'),
        Index('idx_mention_by_user', 'mentioned_by_user_id'),
        Index('idx_mention_viewed', 'mentioned_user_id', 'viewed'),
        UniqueConstraint('note_id', 'mentioned_user_id', 'mention_position', 
                         name='uq_note_user_position'),
    )
    
    def mark_viewed(self):
        """Mark mention as viewed"""
        self.viewed = True
        self.viewed_at = datetime.utcnow()
    
    def mark_acknowledged(self):
        """Mark mention as acknowledged"""
        self.acknowledged = True
        self.acknowledged_at = datetime.utcnow()
        # Also mark as viewed if not already
        if not self.viewed:
            self.mark_viewed()
    
    def send_notification(self):
        """Mark that notification has been sent"""
        self.notification_sent = True
        self.notification_sent_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "note_id": self.note_id,
            "mentioned_user_id": self.mentioned_user_id,
            "mentioned_by_user_id": self.mentioned_by_user_id,
            "mention_text": self.mention_text,
            "mention_position": self.mention_position,
            "notification_sent": self.notification_sent,
            "viewed": self.viewed,
            "viewed_at": self.viewed_at.isoformat() if self.viewed_at else None,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<NoteMention Note:{self.note_id} User:{self.mentioned_user_id}>"


# NoteActivity and NoteShare are now imported from note_activity.py to avoid duplication
