"""
Vendor Profile Model for public vendor pages and portal management.
Handles vendor-specific pages, content management, and access control.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, 
    UniqueConstraint, Index, CheckConstraint, DECIMAL
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from datetime import datetime

from src.db.base_class import Base


class VendorProfile(Base):
    """
    Vendor profile for public-facing vendor pages.
    Each vendor organization gets a dedicated page with custom content.
    """
    __tablename__ = "vendor_profiles"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Link to organization (one-to-one for vendor orgs)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, unique=True)
    
    # URL configuration (e.g., 'medtronic' for nyelux.com/vendor/medtronic)
    url_slug = Column(String(100), unique=True, nullable=False, index=True)
    
    # Public profile information
    display_name = Column(String(255), nullable=False)
    tagline = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    logo_url = Column(Text, nullable=True)
    cover_image_url = Column(Text, nullable=True)
    
    # Company information (public-facing)
    founded_year = Column(Integer, nullable=True)
    headquarters_location = Column(String(255), nullable=True)
    company_size = Column(String(50), nullable=True)  # e.g., "1000-5000 employees"
    
    # Contact information for public inquiries
    public_email = Column(String(255), nullable=True)
    public_phone = Column(String(20), nullable=True)
    support_email = Column(String(255), nullable=True)
    support_phone = Column(String(20), nullable=True)
    sales_email = Column(String(255), nullable=True)
    sales_phone = Column(String(20), nullable=True)
    
    # Social media and web presence
    website_url = Column(Text, nullable=True)
    linkedin_url = Column(Text, nullable=True)
    twitter_url = Column(Text, nullable=True)
    youtube_url = Column(Text, nullable=True)
    facebook_url = Column(Text, nullable=True)
    
    # Content sections (stored as JSON for flexibility)
    about_section = Column(JSONB, nullable=True)  # {"title": "", "content": "", "highlights": []}
    specialties = Column(ARRAY(String), nullable=True)
    certifications = Column(JSONB, nullable=True)  # [{"name": "", "issuer": "", "year": ""}]
    awards = Column(JSONB, nullable=True)  # [{"title": "", "year": "", "description": ""}]
    
    # Access control settings
    public_content_settings = Column(JSONB, default=dict, nullable=False)
    # {
    #   "show_pricing": false,
    #   "show_technical_specs": true,
    #   "show_training_materials": false,
    #   "show_support_docs": false,
    #   "require_registration_for_downloads": true
    # }
    
    # HCP access tiers configuration
    access_tiers = Column(JSONB, default=dict, nullable=False)
    # {
    #   "physician": ["pricing", "clinical_studies", "technical_specs"],
    #   "nurse": ["training_videos", "quick_guides"],
    #   "technician": ["service_manuals", "troubleshooting"]
    # }
    
    # Lead generation settings
    lead_capture_enabled = Column(Boolean, default=True, nullable=False)
    lead_form_fields = Column(JSONB, nullable=True)  # Custom form configuration
    lead_notification_emails = Column(ARRAY(String), nullable=True)
    
    # Analytics settings
    analytics_enabled = Column(Boolean, default=True, nullable=False)
    google_analytics_id = Column(String(50), nullable=True)
    
    # Chat customization
    chat_enabled = Column(Boolean, default=True, nullable=False)
    chat_welcome_message = Column(Text, nullable=True)
    chat_offline_message = Column(Text, nullable=True)
    chat_business_hours = Column(JSONB, nullable=True)  # {"monday": {"start": "09:00", "end": "17:00"}}
    
    # SEO settings
    meta_title = Column(String(255), nullable=True)
    meta_description = Column(Text, nullable=True)
    meta_keywords = Column(ARRAY(String), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_featured = Column(Boolean, default=False, nullable=False, index=True)  # For vendor directory
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metrics (cached for performance)
    total_devices = Column(Integer, default=0, nullable=False)
    total_documents = Column(Integer, default=0, nullable=False)
    total_videos = Column(Integer, default=0, nullable=False)
    
    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    organization = relationship("Organization", backref="vendor_profile")
    custom_content = relationship("VendorCustomContent", back_populates="vendor_profile", cascade="all, delete-orphan")
    access_requests = relationship("VendorAccessRequest", back_populates="vendor_profile", cascade="all, delete-orphan")
    page_analytics = relationship("VendorPageAnalytics", back_populates="vendor_profile", cascade="all, delete-orphan")
    chat_knowledge = relationship("VendorChatKnowledge", back_populates="vendor_profile", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("url_slug ~ '^[a-z0-9-]+$'", name='check_url_slug_format'),
        CheckConstraint("founded_year >= 1800 AND founded_year <= EXTRACT(YEAR FROM CURRENT_DATE)", name='check_founded_year'),
        Index('idx_vendor_profile_active', 'is_active', 'deleted_at'),
        Index('idx_vendor_profile_featured', 'is_featured', 'is_active'),
    )
    
    @property
    def full_url(self) -> str:
        """Get the full URL for this vendor's page"""
        # Using path-based routing for better SEO and simpler infrastructure
        return f"/vendor/{self.url_slug}"
    
    @property
    def is_published(self) -> bool:
        """Check if the profile is published and visible"""
        return self.is_active and self.published_at and self.published_at <= datetime.utcnow()
    
    def get_public_settings(self, key: str, default=False) -> bool:
        """Get a public content setting"""
        return self.public_content_settings.get(key, default) if self.public_content_settings else default
    
    def get_access_tier_permissions(self, role: str) -> list:
        """Get permissions for a specific HCP role"""
        if not self.access_tiers:
            return []
        return self.access_tiers.get(role, [])
    
    def __repr__(self):
        return f"<VendorProfile {self.url_slug}: {self.display_name}>"


class VendorCustomContent(Base):
    """
    Custom content sections for vendor profiles.
    Allows vendors to add custom Q&A, FAQs, and other content.
    """
    __tablename__ = "vendor_custom_content"
    
    id = Column(Integer, primary_key=True, index=True)
    vendor_profile_id = Column(Integer, ForeignKey("vendor_profiles.id"), nullable=False)
    
    # Content type and structure
    content_type = Column(String(50), nullable=False)  # faq, qa_pair, announcement, case_study
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    
    # Additional metadata
    category = Column(String(100), nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    
    # Media attachments
    image_url = Column(Text, nullable=True)
    video_url = Column(Text, nullable=True)
    document_urls = Column(ARRAY(Text), nullable=True)
    
    # Access control
    is_public = Column(Boolean, default=True, nullable=False)
    required_roles = Column(ARRAY(String), nullable=True)  # If not public, which roles can see
    
    # Ordering and display
    display_order = Column(Integer, default=0, nullable=False)
    is_featured = Column(Boolean, default=False, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    published_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    vendor_profile = relationship("VendorProfile", back_populates="custom_content")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("content_type IN ('faq', 'qa_pair', 'announcement', 'case_study', 'guide', 'whitepaper')", 
                       name='check_content_type'),
        Index('idx_vendor_content_profile', 'vendor_profile_id', 'is_active'),
        Index('idx_vendor_content_type', 'content_type', 'is_active'),
    )
    
    def __repr__(self):
        return f"<VendorCustomContent {self.content_type}: {self.title}>"


class VendorAccessRequest(Base):
    """
    Tracks HCP requests for access to vendor's restricted content.
    Vendors can approve/deny access to need-to-know information.
    """
    __tablename__ = "vendor_access_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    vendor_profile_id = Column(Integer, ForeignKey("vendor_profiles.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Request details
    request_type = Column(String(50), nullable=False)  # content_access, demo_request, pricing_info
    requested_access_level = Column(String(50), nullable=True)  # basic, advanced, full
    message = Column(Text, nullable=True)  # Optional message from HCP
    
    # HCP information snapshot (for vendor review)
    user_role = Column(String(50), nullable=False)
    user_organization = Column(String(255), nullable=True)
    user_department = Column(String(100), nullable=True)
    user_title = Column(String(100), nullable=True)
    
    # Approval workflow
    status = Column(String(20), default='pending', nullable=False)  # pending, approved, denied, expired
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approval_notes = Column(Text, nullable=True)
    
    # Access grant details (if approved)
    access_granted_until = Column(DateTime(timezone=True), nullable=True)
    granted_permissions = Column(JSONB, nullable=True)  # Specific permissions granted
    
    # Tracking
    request_source = Column(String(50), nullable=True)  # product_page, chat, email
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True)  # If request is for specific device
    
    # Timestamps
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Auto-deny if not reviewed
    
    # Relationships
    vendor_profile = relationship("VendorProfile", back_populates="access_requests")
    user = relationship("User", foreign_keys=[user_id], backref="vendor_access_requests")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    device = relationship("VendorDevice")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('vendor_profile_id', 'user_id', 'request_type', 'status', 
                        name='uq_vendor_user_request_active'),
        CheckConstraint("status IN ('pending', 'approved', 'denied', 'expired', 'revoked')", 
                       name='check_request_status'),
        CheckConstraint("request_type IN ('content_access', 'demo_request', 'pricing_info', 'training_access', 'support_access')", 
                       name='check_request_type'),
        Index('idx_vendor_access_status', 'vendor_profile_id', 'status'),
        Index('idx_vendor_access_user', 'user_id', 'status'),
    )
    
    @property
    def is_active(self) -> bool:
        """Check if access is currently active"""
        if self.status != 'approved':
            return False
        if self.access_granted_until and self.access_granted_until < datetime.utcnow():
            return False
        return True
    
    def __repr__(self):
        return f"<VendorAccessRequest {self.user_id} -> {self.vendor_profile_id}: {self.status}>"


class VendorPageAnalytics(Base):
    """
    Analytics for vendor profile pages.
    Tracks visits, interactions, and conversions.
    """
    __tablename__ = "vendor_page_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    vendor_profile_id = Column(Integer, ForeignKey("vendor_profiles.id"), nullable=False)
    
    # Date for aggregation
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Traffic metrics
    page_views = Column(Integer, default=0, nullable=False)
    unique_visitors = Column(Integer, default=0, nullable=False)
    avg_time_on_page = Column(Integer, default=0, nullable=False)  # In seconds
    bounce_rate = Column(DECIMAL(5, 2), default=0, nullable=False)  # Percentage
    
    # Engagement metrics
    device_clicks = Column(Integer, default=0, nullable=False)
    document_downloads = Column(Integer, default=0, nullable=False)
    video_plays = Column(Integer, default=0, nullable=False)
    chat_initiations = Column(Integer, default=0, nullable=False)
    
    # Lead generation metrics
    leads_captured = Column(Integer, default=0, nullable=False)
    access_requests = Column(Integer, default=0, nullable=False)
    demo_requests = Column(Integer, default=0, nullable=False)
    contact_form_submissions = Column(Integer, default=0, nullable=False)
    
    # Traffic sources
    traffic_sources = Column(JSONB, nullable=True)
    # {
    #   "direct": 100,
    #   "search": 50,
    #   "social": 20,
    #   "referral": 30
    # }
    
    # Device breakdown
    device_types = Column(JSONB, nullable=True)
    # {
    #   "desktop": 150,
    #   "mobile": 100,
    #   "tablet": 20
    # }
    
    # Geographic data
    visitor_locations = Column(JSONB, nullable=True)
    # {
    #   "US": 200,
    #   "CA": 50,
    #   "UK": 20
    # }
    
    # Top content
    top_devices_viewed = Column(JSONB, nullable=True)  # [{"device_id": 1, "views": 50}]
    top_documents_downloaded = Column(JSONB, nullable=True)
    top_search_queries = Column(JSONB, nullable=True)
    
    # Relationships
    vendor_profile = relationship("VendorProfile", back_populates="page_analytics")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('vendor_profile_id', 'date', name='uq_vendor_analytics_date'),
        Index('idx_vendor_analytics_date', 'vendor_profile_id', 'date'),
    )
    
    def __repr__(self):
        return f"<VendorPageAnalytics {self.vendor_profile_id} - {self.date}>"


class VendorChatKnowledge(Base):
    """
    Custom knowledge base entries for vendor-specific chat responses.
    Supplements the RAG system with vendor-specific Q&A pairs.
    """
    __tablename__ = "vendor_chat_knowledge"
    
    id = Column(Integer, primary_key=True, index=True)
    vendor_profile_id = Column(Integer, ForeignKey("vendor_profiles.id"), nullable=False)
    
    # Knowledge entry
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    
    # Categorization
    category = Column(String(100), nullable=True)
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True)  # If specific to a device
    
    # Keywords for matching
    keywords = Column(ARRAY(String), nullable=True)
    
    # Access control
    is_public = Column(Boolean, default=True, nullable=False)
    required_roles = Column(ARRAY(String), nullable=True)
    
    # Usage tracking
    usage_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Quality metrics
    helpful_count = Column(Integer, default=0, nullable=False)
    not_helpful_count = Column(Integer, default=0, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    approved = Column(Boolean, default=True, nullable=False)  # For moderation
    
    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    vendor_profile = relationship("VendorProfile", back_populates="chat_knowledge")
    device = relationship("VendorDevice")
    
    # Constraints
    __table_args__ = (
        Index('idx_vendor_knowledge_profile', 'vendor_profile_id', 'is_active'),
        Index('idx_vendor_knowledge_device', 'device_id', 'is_active'),
    )
    
    @property
    def effectiveness_score(self) -> float:
        """Calculate effectiveness based on feedback"""
        total = self.helpful_count + self.not_helpful_count
        if total == 0:
            return 0.0
        return (self.helpful_count / total) * 100
    
    def __repr__(self):
        return f"<VendorChatKnowledge {self.id}: {self.question[:50]}...>"
