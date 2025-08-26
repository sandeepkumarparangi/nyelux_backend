from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean,
    Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base_class import Base

class Notification(Base):
    """
    User notification queue.
    Supports multiple delivery channels and priority levels.
    """
    __tablename__ = "notifications"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User association
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Notification details
    type = Column(String(50), nullable=False, index=True)
    priority = Column(String(20), default='medium', nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    action_url = Column(Text, nullable=True)
    
    # Additional data
    data = Column(JSONB, nullable=True)
    
    # Status tracking
    read_at = Column(DateTime(timezone=True), nullable=True, index=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Relationships
    user = relationship("User", back_populates="notifications")
    deliveries = relationship("NotificationDelivery", back_populates="notification", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "type IN ('device_recall', 'device_update', 'new_message', 'meeting_reminder', "
            "'training_available', 'incident_update', 'system_alert', 'other')", 
            name='check_notification_type'
        ),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name='check_priority'),
        Index('idx_user_unread', 'user_id', 'read_at', postgresql_where='read_at IS NULL'),
        Index('idx_created', 'created_at'),
        Index('idx_expires', 'expires_at', postgresql_where='expires_at IS NOT NULL'),
    )
    
    @property
    def is_read(self) -> bool:
        """Check if notification has been read"""
        return self.read_at is not None
    
    @property
    def is_expired(self) -> bool:
        """Check if notification has expired"""
        if not self.expires_at:
            return False
        from datetime import datetime
        return self.expires_at < datetime.utcnow()
    
    @property
    def is_active(self) -> bool:
        """Check if notification is active (unread and not expired)"""
        return not self.is_read and not self.is_expired and self.dismissed_at is None
    
    def mark_as_read(self):
        """Mark notification as read"""
        from datetime import datetime
        if not self.read_at:
            self.read_at = datetime.utcnow()
    
    def dismiss(self):
        """Dismiss notification without reading"""
        from datetime import datetime
        if not self.dismissed_at:
            self.dismissed_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "type": self.type,
            "priority": self.priority,
            "title": self.title,
            "body": self.body,
            "action_url": self.action_url,
            "data": self.data,
            "is_read": self.is_read,
            "is_expired": self.is_expired,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<Notification {self.id}: {self.type}>"
