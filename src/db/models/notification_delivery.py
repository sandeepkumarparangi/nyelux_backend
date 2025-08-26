from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index, 
    CheckConstraint, UniqueConstraint, Time
)
from sqlalchemy.orm import relationship
from datetime import datetime

from src.db.base_class import Base


class NotificationDelivery(Base):
    """
    Track notification delivery status across different channels.
    Records delivery attempts and results for each notification.
    """
    __tablename__ = "notification_deliveries"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Notification association
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=False)
    
    # Delivery details
    channel = Column(String(20), nullable=False)
    recipient_address = Column(Text, nullable=True, comment="Email, phone number, device token, etc.")
    
    # Status tracking
    status = Column(String(20), nullable=False, default='pending')
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Retry information
    retry_count = Column(Integer, nullable=False, default=0)
    
    # Relationships
    notification = relationship("Notification", back_populates="deliveries")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'sms', 'push', 'in_app')", name='check_delivery_channel'),
        CheckConstraint("status IN ('pending', 'sent', 'delivered', 'failed', 'bounced')", name='check_delivery_status'),
        CheckConstraint("retry_count >= 0", name='check_retry_positive'),
        Index('idx_delivery_notification', 'notification_id', 'channel'),
        Index('idx_delivery_status', 'status', 'created_at'),
    )
    
    @property
    def is_successful(self) -> bool:
        """Check if delivery was successful"""
        return self.status == 'delivered'
    
    @property
    def is_failed(self) -> bool:
        """Check if delivery failed"""
        return self.status in ['failed', 'bounced']
    
    @property
    def should_retry(self) -> bool:
        """Check if delivery should be retried"""
        MAX_RETRIES = 3
        return (self.status == 'failed' and 
                self.retry_count < MAX_RETRIES and 
                'bounced' not in (self.error_message or '').lower())
    
    @property
    def delivery_time_seconds(self) -> int:
        """Calculate delivery time in seconds"""
        if self.sent_at and self.delivered_at:
            return int((self.delivered_at - self.sent_at).total_seconds())
        return 0
    
    def mark_sent(self):
        """Mark notification as sent"""
        self.status = 'sent'
        self.sent_at = datetime.utcnow()
    
    def mark_delivered(self):
        """Mark notification as delivered"""
        self.status = 'delivered'
        self.delivered_at = datetime.utcnow()
    
    def mark_failed(self, error_message: str):
        """Mark notification as failed"""
        self.status = 'failed'
        self.failed_at = datetime.utcnow()
        self.error_message = error_message
        self.retry_count += 1
    
    def mark_bounced(self, error_message: str):
        """Mark notification as bounced (permanent failure)"""
        self.status = 'bounced'
        self.failed_at = datetime.utcnow()
        self.error_message = error_message
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "notification_id": self.notification_id,
            "channel": self.channel,
            "recipient_address": self.recipient_address,
            "status": self.status,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "delivery_time_seconds": self.delivery_time_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<NotificationDelivery {self.id}: {self.channel} - {self.status}>"
