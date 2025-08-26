from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index, 
    CheckConstraint, UniqueConstraint, Time
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

from src.db.base_class import Base


class NotificationPreferences(Base):
    """
    User notification preferences and settings.
    """
    __tablename__ = "notification_preferences"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User association (one-to-one)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Channel preferences
    email_enabled = Column(Boolean, nullable=False, default=True)
    sms_enabled = Column(Boolean, nullable=False, default=False)
    push_enabled = Column(Boolean, nullable=False, default=True)
    in_app_enabled = Column(Boolean, nullable=False, default=True)
    
    # Quiet hours
    quiet_hours_start = Column(Time, nullable=True)
    quiet_hours_end = Column(Time, nullable=True)
    timezone = Column(String(50), nullable=True)
    
    # Category preferences (JSONB for flexibility)
    categories = Column(JSONB, nullable=False, default=lambda: {}, comment="{category: {enabled: bool, channels: [str]}}")
    
    # Frequency settings
    frequency = Column(JSONB, nullable=False, default=lambda: {}, comment="{type: 'immediate'|'digest', digest_time: 'HH:MM'}")
    
    # Relationships
    user = relationship("User", backref="preferences_settings", uselist=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_notif_pref_user', 'user_id'),
    )
    
    @property
    def is_in_quiet_hours(self) -> bool:
        """Check if currently in quiet hours"""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        from datetime import datetime
        import pytz
        
        # Get current time in user's timezone
        tz = pytz.timezone(self.timezone or 'UTC')
        now = datetime.now(tz)
        current_time = now.time()
        
        # Handle overnight quiet hours
        if self.quiet_hours_start <= self.quiet_hours_end:
            return self.quiet_hours_start <= current_time <= self.quiet_hours_end
        else:
            return current_time >= self.quiet_hours_start or current_time <= self.quiet_hours_end
    
    def is_channel_enabled(self, channel: str) -> bool:
        """Check if specific channel is enabled"""
        channel_map = {
            'email': self.email_enabled,
            'sms': self.sms_enabled,
            'push': self.push_enabled,
            'in_app': self.in_app_enabled
        }
        return channel_map.get(channel, False)
    
    def is_category_enabled(self, category: str, channel: str = None) -> bool:
        """Check if specific category is enabled for a channel"""
        try:
            cat_prefs = self.categories.get(category, {}) if self.categories else {}
            
            if not cat_prefs.get('enabled', True):
                return False
            
            if channel and 'channels' in cat_prefs:
                return channel in cat_prefs['channels']
            
            return True
        except:
            return True  # Default to enabled if parsing fails
    
    def should_send_notification(self, category: str, channel: str) -> bool:
        """Determine if notification should be sent"""
        # Check if channel is enabled globally
        if not self.is_channel_enabled(channel):
            return False
        
        # Check category preferences
        if not self.is_category_enabled(category, channel):
            return False
        
        # Check quiet hours (except for urgent notifications)
        if category not in ['urgent', 'critical'] and self.is_in_quiet_hours:
            return False
        
        return True
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "user_id": self.user_id,
            "email_enabled": self.email_enabled,
            "sms_enabled": self.sms_enabled,
            "push_enabled": self.push_enabled,
            "in_app_enabled": self.in_app_enabled,
            "quiet_hours_start": self.quiet_hours_start.isoformat() if self.quiet_hours_start else None,
            "quiet_hours_end": self.quiet_hours_end.isoformat() if self.quiet_hours_end else None,
            "timezone": self.timezone,
            "is_in_quiet_hours": self.is_in_quiet_hours,
            "categories": self.categories or {},
            "frequency": self.frequency or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<NotificationPreferences user_{self.user_id}>"
