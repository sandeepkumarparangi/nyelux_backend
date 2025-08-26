"""
Import all models to ensure SQLAlchemy relationships are properly configured
This file MUST import all models that have relationships
"""

# Import base first
from src.db.base_class import Base

# Import all models in the correct order to avoid circular dependencies
from src.db.models.organization import Organization, Department
from src.db.models.user import User
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.db.models.device_document import DeviceDocument
from src.db.models.document_chunk import DocumentChunk
from src.db.models.device_video import DeviceVideo
from src.db.models.device_incident import DeviceIncident
from src.db.models.incident_attachment import IncidentAttachment, IncidentComment
from src.db.models.search_history import SearchHistory, SavedSearch
from src.db.models.lead import Lead
from src.db.models.chat import ChatConversation, ChatMessage, ChatCitation
from src.db.models.calendar_event import CalendarEvent
from src.db.models.event_attendee import EventAttendee
from src.db.models.notification import Notification
from src.db.models.notification_delivery import NotificationDelivery
from src.db.models.notification_preferences import NotificationPreferences
from src.db.models.analytics_event import AnalyticsEvent
from src.db.models.device_analytics_daily import DeviceAnalyticsDaily
from src.db.models.audit_log import AuditLog
from src.db.models.api_key import APIKey
from src.db.models.background_job import BackgroundJob
from src.db.models.support_conversation import SupportConversation
from src.db.models.support_message import SupportMessage
from src.db.models.agent_availability import AgentAvailability
from src.db.models.team import Team, TeamMember
from src.db.models.note import Note, NoteComment
from src.db.models.note_version import NoteVersion
from src.db.models.note_activity import NoteActivity, NoteShare
from src.db.models.subscription import Subscription
from src.db.models.invoice import Invoice
from src.db.models.payment_method import PaymentMethod
from src.db.models.video_progress import VideoProgress
from src.db.models.note_mention import NoteMention
from src.db.models.availability_slot import AvailabilitySlot
from src.db.models.user_bookmarks import UserBookmark
from src.db.models.device_comparison import DeviceComparison
from src.db.models.user_credential import UserCredential
from src.db.models.user_certification import UserCertification
from src.db.models.training_record import TrainingRecord
from src.db.models.vendor_profile import (
    VendorProfile, VendorCustomContent, VendorAccessRequest, 
    VendorPageAnalytics, VendorChatKnowledge
)
from src.db.models.vendor_lead import VendorLead, VendorLeadActivity
from src.db.models.vendor_service import (
    VendorServiceRequest, VendorServiceCommunication, VendorRepAvailability
)

# Export all models
__all__ = [
    "Base",
    "Organization",
    "Department", 
    "User",
    "GUDIDDevice",
    "VendorDevice",
    "DeviceDocument",
    "DocumentChunk",
    "DeviceVideo",
    "DeviceIncident",
    "IncidentAttachment",
    "IncidentComment",
    "SearchHistory",
    "SavedSearch",
    "Lead",
    "ChatConversation",
    "ChatMessage",
    "ChatCitation",
    "CalendarEvent",
    "EventAttendee",
    "Notification",
    "NotificationDelivery",
    "NotificationPreferences",
    "AnalyticsEvent",
    "DeviceAnalyticsDaily",
    "AuditLog",
    "APIKey",
    "BackgroundJob",
    "SupportConversation",
    "SupportMessage",
    "AgentAvailability",
    "Team",
    "TeamMember",
    "Note",
    "NoteComment",
    "NoteVersion",
    "NoteActivity",
    "NoteShare",
    "Subscription",
    "Invoice",
    "PaymentMethod",
    "VideoProgress",
    "NoteMention",
    "AvailabilitySlot",
    "UserBookmark",
    "DeviceComparison",
    "UserCredential",
    "UserCertification",
    "TrainingRecord",
    "VendorProfile",
    "VendorCustomContent",
    "VendorAccessRequest",
    "VendorPageAnalytics",
    "VendorChatKnowledge",
    "VendorLead",
    "VendorLeadActivity",
    "VendorServiceRequest",
    "VendorServiceCommunication",
    "VendorRepAvailability"
]
