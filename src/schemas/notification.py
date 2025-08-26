"""
Notification schemas.
"""
from datetime import datetime, time
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

from src.schemas.base import BaseSchema, TimestampMixin


# Notification types
NotificationType = Literal[
    "device_recall",
    "device_update", 
    "new_message",
    "meeting_reminder",
    "training_available",
    "incident_update",
    "incident_assigned",
    "incident_escalation",
    "meeting_response",
    "meeting_cancelled",
    "system_alert"
]

NotificationPriority = Literal["low", "medium", "high", "urgent"]
NotificationChannel = Literal["email", "sms", "push", "in_app"]
DeliveryStatus = Literal["pending", "sent", "delivered", "failed", "bounced"]


# Notification Schemas
class NotificationBase(BaseSchema):
    """Base notification schema"""
    type: NotificationType
    priority: NotificationPriority = "medium"
    title: str = Field(..., min_length=1, max_length=500)
    body: str
    action_url: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None


class NotificationCreate(NotificationBase):
    """Create notification schema"""
    user_id: int


class NotificationInDB(NotificationBase, TimestampMixin):
    """Notification database schema"""
    id: int
    user_id: int
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None


class NotificationDeliveryInfo(BaseSchema):
    """Notification delivery information"""
    channel: NotificationChannel
    status: DeliveryStatus
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class NotificationResponse(NotificationInDB):
    """Notification response with delivery status"""
    deliveries: List[NotificationDeliveryInfo] = []
    is_read: bool = False
    is_dismissed: bool = False
    
    @classmethod
    def from_orm_with_deliveries(cls, notification, deliveries):
        """Create response with delivery information"""
        data = notification.__dict__.copy()
        data["is_read"] = notification.read_at is not None
        data["is_dismissed"] = notification.dismissed_at is not None
        data["deliveries"] = [
            NotificationDeliveryInfo(
                channel=d.channel,
                status=d.status,
                sent_at=d.sent_at,
                delivered_at=d.delivered_at,
                failed_at=d.failed_at,
                error_message=d.error_message
            )
            for d in deliveries
        ]
        return cls(**data)


# Notification Actions
class NotificationMarkRead(BaseSchema):
    """Mark notifications as read"""
    notification_ids: List[int]


class NotificationBulkAction(BaseSchema):
    """Bulk notification actions"""
    notification_ids: List[int]
    action: Literal["mark_read", "dismiss"]


# Notification Preferences
class NotificationChannelPreference(BaseSchema):
    """Channel preference settings"""
    email: bool = True
    sms: bool = False
    push: bool = True
    in_app: bool = True


class NotificationPreferencesBase(BaseSchema):
    """Base notification preferences"""
    email_enabled: bool = True
    sms_enabled: bool = False
    push_enabled: bool = True
    in_app_enabled: bool = True
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    timezone: str = Field("UTC", max_length=50)
    categories: Dict[str, NotificationChannelPreference] = {}
    frequency: Dict[str, Literal["immediate", "digest", "daily", "weekly"]] = {
        "email": "immediate",
        "sms": "immediate", 
        "push": "immediate",
        "in_app": "immediate"
    }


class NotificationPreferencesUpdate(BaseSchema):
    """Update notification preferences"""
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    timezone: Optional[str] = Field(None, max_length=50)
    categories: Optional[Dict[str, NotificationChannelPreference]] = None
    frequency: Optional[Dict[str, Literal["immediate", "digest", "daily", "weekly"]]] = None


class NotificationPreferencesResponse(NotificationPreferencesBase):
    """Notification preferences response"""
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


# Notification Statistics
class NotificationStats(BaseSchema):
    """Notification statistics"""
    unread_count: int
    by_type: Dict[str, int]
    by_priority: Dict[str, int]


# Test Notification
class TestNotificationRequest(BaseSchema):
    """Request to send test notification"""
    channel: NotificationChannel


# Push Subscription
class PushSubscription(BaseSchema):
    """Web push subscription"""
    endpoint: str
    keys: Dict[str, str]


# Email Templates
class EmailTemplateData(BaseSchema):
    """Data for email templates"""
    recipient_name: Optional[str] = None
    subject: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    action_url: Optional[str] = None
    action_text: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None
