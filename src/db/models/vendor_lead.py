"""
Vendor Lead Management Model.
Handles lead generation from vendor pages and chat interactions.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, 
    UniqueConstraint, Index, CheckConstraint, DECIMAL
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, INET
from datetime import datetime

from src.db.base_class import Base


class VendorLead(Base):
    """
    Leads generated from vendor profile pages.
    Tracks visitor interest and conversion funnel.
    """
    __tablename__ = "vendor_leads"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Lead source
    vendor_profile_id = Column(Integer, ForeignKey("vendor_profiles.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)  # Vendor org
    
    # Lead information
    email = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # Professional information
    organization_name = Column(String(255), nullable=True)
    organization_type = Column(String(50), nullable=True)  # hospital, clinic, private_practice
    job_title = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    role = Column(String(50), nullable=True)  # physician, nurse, technician, administrator
    
    # Location
    city = Column(String(100), nullable=True)
    state_province = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    
    # Lead source details
    source_type = Column(String(50), nullable=False)  # chat, device_view, download, contact_form
    source_url = Column(Text, nullable=True)
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True)
    referrer_url = Column(Text, nullable=True)
    utm_source = Column(String(100), nullable=True)
    utm_medium = Column(String(100), nullable=True)
    utm_campaign = Column(String(100), nullable=True)
    
    # Interest indicators
    interested_devices = Column(ARRAY(Integer), nullable=True)  # Device IDs viewed
    downloaded_documents = Column(ARRAY(Integer), nullable=True)  # Document IDs
    watched_videos = Column(ARRAY(Integer), nullable=True)  # Video IDs
    search_queries = Column(ARRAY(Text), nullable=True)  # What they searched for
    chat_questions = Column(JSONB, nullable=True)  # Questions asked in chat
    
    # Lead scoring
    lead_score = Column(Integer, default=0, nullable=False)  # 0-100
    scoring_factors = Column(JSONB, nullable=True)
    # {
    #   "engagement_score": 30,
    #   "profile_completeness": 20,
    #   "organization_fit": 25,
    #   "behavior_score": 25
    # }
    
    # Lead status
    status = Column(String(50), default='new', nullable=False)
    # new, contacted, qualified, unqualified, converted, lost
    
    # Assignment and follow-up
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)  # Sales rep
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    first_contact_at = Column(DateTime(timezone=True), nullable=True)
    last_contact_at = Column(DateTime(timezone=True), nullable=True)
    next_follow_up = Column(DateTime(timezone=True), nullable=True)
    
    # Qualification
    qualified = Column(Boolean, nullable=True)
    qualified_at = Column(DateTime(timezone=True), nullable=True)
    qualified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    qualification_notes = Column(Text, nullable=True)
    
    # Conversion tracking
    converted = Column(Boolean, default=False, nullable=False)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    converted_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    conversion_value = Column(DECIMAL(10, 2), nullable=True)
    
    # Communication preferences
    email_opt_in = Column(Boolean, default=True, nullable=False)
    phone_opt_in = Column(Boolean, default=False, nullable=False)
    preferred_contact_method = Column(String(20), nullable=True)  # email, phone, text
    preferred_contact_time = Column(String(50), nullable=True)  # morning, afternoon, evening
    
    # GDPR compliance
    consent_given = Column(Boolean, default=False, nullable=False)
    consent_timestamp = Column(DateTime(timezone=True), nullable=True)
    consent_ip = Column(INET, nullable=True)
    privacy_policy_version = Column(String(20), nullable=True)
    
    # Additional context
    notes = Column(Text, nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    custom_fields = Column(JSONB, nullable=True)  # For vendor-specific fields
    
    # Session tracking
    session_id = Column(String(100), nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Timestamps
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    vendor_profile = relationship("VendorProfile")
    organization = relationship("Organization")
    device = relationship("VendorDevice")
    assigned_rep = relationship("User", foreign_keys=[assigned_to])
    qualified_user = relationship("User", foreign_keys=[qualified_by])
    converted_user = relationship("User", foreign_keys=[converted_to_user_id])
    activities = relationship("VendorLeadActivity", back_populates="lead", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("lead_score >= 0 AND lead_score <= 100", name='check_lead_score_range'),
        CheckConstraint("status IN ('new', 'contacted', 'qualified', 'unqualified', 'converted', 'lost', 'nurturing')", 
                       name='check_lead_status'),
        CheckConstraint("preferred_contact_method IN ('email', 'phone', 'text', 'any')", 
                       name='check_contact_method'),
        Index('idx_vendor_lead_status', 'vendor_profile_id', 'status'),
        Index('idx_vendor_lead_score', 'vendor_profile_id', 'lead_score'),
        Index('idx_vendor_lead_assigned', 'assigned_to', 'status'),
        Index('idx_vendor_lead_email', 'email', 'vendor_profile_id'),
    )
    
    @property
    def is_hot_lead(self) -> bool:
        """Check if this is a hot lead based on score and recency"""
        if self.lead_score >= 70:
            return True
        # Recent engagement (last 24 hours)
        from datetime import datetime, timedelta
        if self.created_at >= datetime.utcnow() - timedelta(hours=24) and self.lead_score >= 50:
            return True
        return False
    
    @property
    def days_since_contact(self) -> int:
        """Calculate days since last contact"""
        if not self.last_contact_at:
            return -1
        delta = datetime.utcnow() - self.last_contact_at
        return delta.days
    
    def calculate_lead_score(self) -> int:
        """
        Calculate lead score based on various factors.
        This is a simplified version - can be enhanced with ML.
        """
        score = 0
        
        # Profile completeness (max 20)
        if self.first_name and self.last_name:
            score += 5
        if self.organization_name:
            score += 5
        if self.job_title:
            score += 5
        if self.phone:
            score += 5
        
        # Engagement (max 40)
        if self.interested_devices:
            score += min(len(self.interested_devices) * 5, 15)
        if self.downloaded_documents:
            score += min(len(self.downloaded_documents) * 3, 10)
        if self.watched_videos:
            score += min(len(self.watched_videos) * 3, 10)
        if self.chat_questions:
            score += 5
        
        # Organization fit (max 25)
        if self.organization_type == 'hospital':
            score += 15
        elif self.organization_type == 'clinic':
            score += 10
        elif self.organization_type == 'private_practice':
            score += 5
        
        if self.role in ['physician', 'administrator']:
            score += 10
        elif self.role in ['nurse', 'technician']:
            score += 5
        
        # Behavior (max 15)
        if self.email_opt_in:
            score += 5
        if self.phone_opt_in:
            score += 5
        if self.consent_given:
            score += 5
        
        return min(score, 100)
    
    def __repr__(self):
        return f"<VendorLead {self.email} - Score: {self.lead_score}>"


class VendorLeadActivity(Base):
    """
    Activity log for vendor leads.
    Tracks all interactions and touchpoints.
    """
    __tablename__ = "vendor_lead_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("vendor_leads.id"), nullable=False)
    
    # Activity details
    activity_type = Column(String(50), nullable=False)
    # email_sent, email_opened, email_clicked, call_made, call_received,
    # meeting_scheduled, demo_given, proposal_sent, note_added
    
    activity_description = Column(Text, nullable=True)
    
    # Related entities
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who performed the activity
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True)
    document_id = Column(Integer, ForeignKey("device_documents.id"), nullable=True)
    
    # Communication details
    communication_channel = Column(String(20), nullable=True)  # email, phone, chat, in_person
    communication_direction = Column(String(10), nullable=True)  # inbound, outbound
    
    # Outcome
    outcome = Column(String(50), nullable=True)  # success, no_answer, left_message, scheduled_callback
    next_action = Column(String(100), nullable=True)
    next_action_date = Column(DateTime(timezone=True), nullable=True)
    
    # Activity metadata
    activity_metadata = Column(JSONB, nullable=True)  # Additional activity-specific data
    
    # Relationships
    lead = relationship("VendorLead", back_populates="activities")
    user = relationship("User")
    device = relationship("VendorDevice")
    document = relationship("DeviceDocument")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("activity_type IN ('email_sent', 'email_opened', 'email_clicked', 'call_made', 'call_received', " +
                       "'meeting_scheduled', 'meeting_held', 'demo_given', 'proposal_sent', 'note_added', " +
                       "'status_changed', 'assignment_changed', 'document_sent', 'chat_interaction')",
                       name='check_activity_type'),
        Index('idx_lead_activity_lead', 'lead_id', 'created_at'),
        Index('idx_lead_activity_user', 'user_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<VendorLeadActivity {self.activity_type} for Lead {self.lead_id}>"
