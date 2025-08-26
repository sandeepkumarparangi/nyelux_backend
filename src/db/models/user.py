from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, ARRAY,
    UniqueConstraint, Index, CheckConstraint, LargeBinary
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import TYPE_CHECKING

from src.db.base_class import Base

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from src.db.models.organization import Organization, Department
    from src.db.models.device_document import DeviceDocument
    from src.db.models.device_video import DeviceVideo
    from src.db.models.note import Note
    from src.db.models.device_incident import DeviceIncident
    from src.db.models.incident_attachment import IncidentComment
    from src.db.models.support_conversation import SupportConversation
    from src.db.models.calendar_event import CalendarEvent
    from src.db.models.notification import Notification

class User(Base):
    """User model for authentication and authorization."""
    __tablename__ = "users"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Authentication fields
    email = Column(String(255), unique=True, index=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    phone = Column(String(20), nullable=True)
    phone_verified = Column(Boolean, default=False, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # Organization association
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    
    # Role management
    role = Column(String(50), nullable=False)
    sub_role = Column(String(50), nullable=True)
    
    # Profile information
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    title = Column(String(100), nullable=True)
    avatar_url = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    
    # MFA settings
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(255), nullable=True)
    mfa_backup_codes = Column(ARRAY(String), nullable=True)
    mfa_secret_encrypted = Column(LargeBinary, nullable=True)
    mfa_backup_codes_hash = Column(Text, nullable=True)
    
    # Email verification fields
    email_verification_token_hash = Column(String(255), nullable=True, index=True)
    email_verification_expires = Column(DateTime(timezone=True), nullable=True)
    
    # Preferences
    language_preference = Column(String(10), default='en', nullable=False)
    timezone = Column(String(50), default='America/New_York', nullable=False)
    notification_preferences = Column(JSONB, default=dict, nullable=False)
    
    # Account status
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    
    # Security
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(String(255), nullable=True, index=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)
    
    # SSO fields
    google_id = Column(String(255), nullable=True, unique=True, index=True)
    azure_id = Column(String(255), nullable=True, unique=True, index=True)
    saml_id = Column(String(255), nullable=True, unique=True, index=True)
    saml_name_id = Column(String(255), nullable=True)  # SAML NameID for logout
    created_via = Column(String(50), default="registration")  # registration, google_oauth, saml, invitation, bulk_import, vendor_provision
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    require_password_change = Column(Boolean, default=False)
    
    # Vendor access fields
    vendor_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)  # Which vendor granted access
    vendor_device_access = Column(ARRAY(String), nullable=True)  # List of device DIs user can access
    vendor_access_level = Column(String(50), nullable=True)  # viewer, user, admin
    access_expires_at = Column(DateTime(timezone=True), nullable=True)
    access_granted_at = Column(DateTime(timezone=True), nullable=True)
    access_granted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    access_updated_at = Column(DateTime(timezone=True), nullable=True)
    access_updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    access_revoked_at = Column(DateTime(timezone=True), nullable=True)
    access_revoked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    access_revoked_reason = Column(Text, nullable=True)
    
    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Relationships with proper string references to avoid circular imports
    organization = relationship("Organization", back_populates="users", foreign_keys=[organization_id])
    department = relationship("Department", back_populates="users", foreign_keys=[department_id])
    
    # Document relationships
    created_documents = relationship(
        "DeviceDocument", 
        foreign_keys="DeviceDocument.created_by",
        back_populates="created_by_user"
    )
    
    # Video relationships
    created_videos = relationship(
        "DeviceVideo",
        foreign_keys="DeviceVideo.created_by",
        back_populates="created_by_user"
    )
    video_progress = relationship(
        "VideoProgress",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    # Note relationships
    notes = relationship(
        "Note",
        foreign_keys="Note.created_by",
        back_populates="created_by_user",
        cascade="all, delete-orphan"
    )
    note_activities = relationship(
        "NoteActivity",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    # Note mention relationships
    mentions_received = relationship(
        "NoteMention",
        foreign_keys="NoteMention.mentioned_user_id",
        back_populates="mentioned_user",
        cascade="all, delete-orphan"
    )
    mentions_created = relationship(
        "NoteMention",
        foreign_keys="NoteMention.mentioned_by_user_id",
        back_populates="mentioned_by_user",
        cascade="all, delete-orphan"
    )
    # NoteCollaboration model not implemented yet
    # note_collaborations = relationship(
    #     "NoteCollaboration",
    #     back_populates="user",
    #     cascade="all, delete-orphan"
    # )
    
    # Incident relationships
    reported_incidents = relationship(
        "DeviceIncident",
        foreign_keys="DeviceIncident.reported_by",
        back_populates="reporter"
    )
    assigned_incidents = relationship(
        "DeviceIncident",
        foreign_keys="DeviceIncident.assigned_to",
        back_populates="assignee"
    )
    incident_comments = relationship(
        "IncidentComment",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    # SavedSearch model is now implemented
    saved_searches = relationship(
        "SavedSearch",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    uploaded_attachments = relationship(
        "IncidentAttachment",
        foreign_keys="IncidentAttachment.uploaded_by",
        back_populates="uploader",
        cascade="all, delete-orphan"
    )
    
    # Support relationships
    support_conversations_as_requester = relationship(
        "SupportConversation",
        foreign_keys="SupportConversation.requester_id",
        back_populates="requester"
    )
    support_conversations_as_agent = relationship(
        "SupportConversation",
        foreign_keys="SupportConversation.agent_id",
        back_populates="agent"
    )
    support_messages = relationship(
        "SupportMessage",
        back_populates="sender",
        cascade="all, delete-orphan"
    )
    agent_availability = relationship(
        "AgentAvailability",
        back_populates="agent",
        uselist=False
    )
    
    # Calendar relationships
    hosted_events = relationship(
        "CalendarEvent",
        foreign_keys="CalendarEvent.host_id",
        back_populates="host"
    )
    created_events = relationship(
        "CalendarEvent",
        foreign_keys="CalendarEvent.created_by",
        back_populates="creator"
    )
    event_attendances = relationship(
        "EventAttendee",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    availability_slots = relationship(
        "AvailabilitySlot",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    # Notification relationships
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    notification_preferences_rel = relationship(
        "NotificationPreferences",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    # Analytics relationships
    analytics_events = relationship(
        "AnalyticsEvent",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    search_history = relationship(
        "SearchHistory",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    # Other relationships
    bookmarks = relationship(
        "UserBookmark",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    comparisons = relationship(
        "DeviceComparison",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    audit_logs = relationship(
        "AuditLog",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    api_keys = relationship(
        "APIKey",
        foreign_keys="APIKey.created_by",
        back_populates="created_by_user",
        cascade="all, delete-orphan"
    )
    chat_conversations = relationship(
        "ChatConversation",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    credentials = relationship(
        "UserCredential",
        foreign_keys="UserCredential.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    certifications = relationship(
        "UserCertification",
        foreign_keys="UserCertification.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    training_records = relationship(
        "TrainingRecord",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    
    # Team relationships
    team_memberships = relationship(
        "TeamMember",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    created_teams = relationship(
        "Team",
        foreign_keys="Team.created_by",
        back_populates="created_by_user"
    )
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_user_email_active', 'email', 'deleted_at'),
        Index('idx_user_org_role', 'organization_id', 'role'),
        Index('idx_user_last_activity', 'last_activity_at'),
        CheckConstraint('failed_login_attempts >= 0', name='check_failed_attempts_positive'),
        CheckConstraint("role IN ('super_admin', 'org_admin', 'vendor_admin', 'vendor_rep', 'clinical_admin', 'physician', 'nurse', 'technician', 'read_only')", name='check_valid_role'),
    )
    
    @property
    def is_active(self) -> bool:
        """Check if user account is active"""
        return self.deleted_at is None and (
            self.locked_until is None or self.locked_until < datetime.utcnow()
        )
    
    @property
    def full_name(self) -> str:
        """Get user's full name"""
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts) or self.email
    
    @property
    def is_admin(self) -> bool:
        """Check if user has admin privileges"""
        return self.role in ['super_admin', 'org_admin', 'vendor_admin', 'clinical_admin']
    
    @property
    def is_vendor(self) -> bool:
        """Check if user is a vendor representative"""
        return self.role in ['vendor_admin', 'vendor_rep']
    
    @property
    def is_healthcare_professional(self) -> bool:
        """Check if user is a healthcare professional (HCP)"""
        return self.role in ['physician', 'nurse', 'technician', 'clinical_admin']
    
    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
