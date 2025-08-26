"""
Database model validation module.
Tests all models and relationships are properly configured.
"""

from sqlalchemy.orm import configure_mappers
import logging

# Import ALL models at module level to ensure relationships are configured
from src.db.models import (
    Base,
    Organization,
    Department, 
    User,
    GUDIDDevice,
    VendorDevice,
    DeviceDocument,
    DocumentChunk,
    DeviceVideo,
    DeviceIncident,
    IncidentAttachment,
    IncidentComment,
    SearchHistory,
    SavedSearch,
    Lead,
    ChatConversation,
    ChatMessage,
    ChatCitation,
    CalendarEvent,
    EventAttendee,
    Notification,
    NotificationDelivery,
    NotificationPreferences,
    AnalyticsEvent,
    DeviceAnalyticsDaily,
    AuditLog,
    APIKey,
    BackgroundJob,
    SupportConversation,
    SupportMessage,
    AgentAvailability,
    Team,
    TeamMember,
    Note,
    NoteComment,
    NoteVersion,
    NoteActivity,
    NoteShare,
    Subscription,
    Invoice,
    PaymentMethod,
    VideoProgress,
    NoteMention,
    AvailabilitySlot,
    UserBookmark,
    DeviceComparison,
    UserCredential,
    UserCertification,
    TrainingRecord,
    VendorProfile,
    VendorCustomContent,
    VendorAccessRequest,
    VendorPageAnalytics,
    VendorChatKnowledge,
    VendorLead,
    VendorLeadActivity,
    VendorServiceRequest,
    VendorServiceCommunication,
    VendorRepAvailability
)

logger = logging.getLogger(__name__)

def validate_models():
    """
    Validate all SQLAlchemy models and relationships are properly configured.
    This will raise an exception if there are any relationship issues.
    """
    try:
        # Force SQLAlchemy to configure all mappers
        # This will raise an error if relationships are misconfigured
        configure_mappers()
        
        logger.info("✅ All database models validated successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Model validation failed: {e}")
        raise

def check_relationships():
    """
    Check specific relationships that have been problematic.
    """
    from src.db.models.vendor_device import VendorDevice
    from src.db.models.chat import ChatConversation
    from src.db.models.user import User
    from src.db.models.training_record import TrainingRecord
    
    # Check VendorDevice relationships
    vendor_device_relationships = VendorDevice.__mapper__.relationships.keys()
    assert 'chat_conversations' in vendor_device_relationships, \
        "VendorDevice missing chat_conversations relationship"
    assert 'training_records' in vendor_device_relationships, \
        "VendorDevice missing training_records relationship"
    
    # Check ChatConversation has device relationship
    chat_relationships = ChatConversation.__mapper__.relationships.keys()
    assert 'device' in chat_relationships, \
        "ChatConversation missing device relationship"
    
    # Check User relationships
    user_relationships = User.__mapper__.relationships.keys()
    assert 'chat_conversations' in user_relationships, \
        "User missing chat_conversations relationship"
    assert 'training_records' in user_relationships, \
        "User missing training_records relationship"
    
    # Check TrainingRecord relationships
    training_relationships = TrainingRecord.__mapper__.relationships.keys()
    assert 'device' in training_relationships, \
        "TrainingRecord missing device relationship"
    assert 'user' in training_relationships, \
        "TrainingRecord missing user relationship"
    
    logger.info("✅ Critical relationships verified")
    return True
