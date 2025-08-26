"""
Pydantic schemas for vendor portal functionality.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, HttpUrl, validator
from enum import Enum


# Enums
class VendorPageAccessLevel(str, Enum):
    PUBLIC = "public"
    REGISTERED = "registered"
    APPROVED = "approved"


class LeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    CONVERTED = "converted"
    LOST = "lost"
    NURTURING = "nurturing"


class ServiceRequestStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class ServiceUrgency(str, Enum):
    EMERGENCY = "emergency"  # 2 hour response
    URGENT = "urgent"  # 24 hour response
    ROUTINE = "routine"  # 72 hour response
    SCHEDULED = "scheduled"  # Pre-planned


# Vendor Profile Schemas
class VendorProfileBase(BaseModel):
    display_name: str
    url_slug: str = Field(..., pattern="^[a-z0-9-]+$")
    tagline: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[HttpUrl] = None
    cover_image_url: Optional[HttpUrl] = None
    
    # Company info
    founded_year: Optional[int] = Field(None, ge=1800, le=datetime.now().year)
    headquarters_location: Optional[str] = None
    company_size: Optional[str] = None
    
    # Contact
    public_email: Optional[EmailStr] = None
    public_phone: Optional[str] = None
    support_email: Optional[EmailStr] = None
    support_phone: Optional[str] = None
    sales_email: Optional[EmailStr] = None
    sales_phone: Optional[str] = None
    
    # Social media
    website_url: Optional[HttpUrl] = None
    linkedin_url: Optional[HttpUrl] = None
    twitter_url: Optional[HttpUrl] = None
    youtube_url: Optional[HttpUrl] = None
    facebook_url: Optional[HttpUrl] = None
    
    # Content
    specialties: Optional[List[str]] = []
    certifications: Optional[List[Dict[str, Any]]] = []
    awards: Optional[List[Dict[str, Any]]] = []
    
    # Settings
    lead_capture_enabled: bool = True
    analytics_enabled: bool = True
    chat_enabled: bool = True
    
    # SEO
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = []


class VendorProfileCreate(VendorProfileBase):
    organization_id: int


class VendorProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    tagline: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[HttpUrl] = None
    cover_image_url: Optional[HttpUrl] = None
    
    # Add all optional fields for updates
    founded_year: Optional[int] = None
    headquarters_location: Optional[str] = None
    company_size: Optional[str] = None
    
    # Contact updates
    public_email: Optional[EmailStr] = None
    public_phone: Optional[str] = None
    support_email: Optional[EmailStr] = None
    support_phone: Optional[str] = None
    sales_email: Optional[EmailStr] = None
    sales_phone: Optional[str] = None
    
    # Social media updates
    website_url: Optional[HttpUrl] = None
    linkedin_url: Optional[HttpUrl] = None
    twitter_url: Optional[HttpUrl] = None
    youtube_url: Optional[HttpUrl] = None
    facebook_url: Optional[HttpUrl] = None
    
    # Content updates
    specialties: Optional[List[str]] = None
    certifications: Optional[List[Dict[str, Any]]] = None
    awards: Optional[List[Dict[str, Any]]] = None
    
    # Settings updates
    public_content_settings: Optional[Dict[str, bool]] = None
    access_tiers: Optional[Dict[str, List[str]]] = None
    lead_form_fields: Optional[Dict[str, Any]] = None
    chat_welcome_message: Optional[str] = None
    chat_offline_message: Optional[str] = None
    chat_business_hours: Optional[Dict[str, Dict[str, str]]] = None
    
    # SEO updates
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[List[str]] = None


class VendorProfileResponse(VendorProfileBase):
    id: int
    organization_id: int
    is_active: bool
    is_featured: bool
    published_at: Optional[datetime] = None
    total_devices: int
    total_documents: int
    total_videos: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class VendorProfilePublic(BaseModel):
    """Public view of vendor profile"""
    id: int
    display_name: str
    url_slug: str
    tagline: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    
    # Limited company info
    founded_year: Optional[int] = None
    headquarters_location: Optional[str] = None
    company_size: Optional[str] = None
    
    # Public contact only
    public_email: Optional[str] = None
    website_url: Optional[str] = None
    
    # Social media
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    
    # Content
    specialties: List[str] = []
    certifications: List[Dict[str, Any]] = []
    
    # Metrics
    total_devices: int
    total_documents: int
    total_videos: int
    
    # Features
    chat_enabled: bool
    
    class Config:
        orm_mode = True


# Custom Content Schemas
class VendorCustomContentBase(BaseModel):
    content_type: str = Field(..., pattern="^(faq|qa_pair|announcement|case_study|guide|whitepaper)$")
    title: str = Field(..., max_length=500)
    content: str
    category: Optional[str] = None
    tags: Optional[List[str]] = []
    image_url: Optional[HttpUrl] = None
    video_url: Optional[HttpUrl] = None
    document_urls: Optional[List[HttpUrl]] = []
    is_public: bool = True
    required_roles: Optional[List[str]] = []
    display_order: int = 0
    is_featured: bool = False


class VendorCustomContentCreate(VendorCustomContentBase):
    vendor_profile_id: int


class VendorCustomContentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    image_url: Optional[HttpUrl] = None
    video_url: Optional[HttpUrl] = None
    document_urls: Optional[List[HttpUrl]] = None
    is_public: Optional[bool] = None
    required_roles: Optional[List[str]] = None
    display_order: Optional[int] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None


class VendorCustomContentResponse(VendorCustomContentBase):
    id: int
    vendor_profile_id: int
    is_active: bool
    published_at: datetime
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


# Access Request Schemas
class VendorAccessRequestBase(BaseModel):
    request_type: str = Field(..., pattern="^(content_access|demo_request|pricing_info|training_access|support_access)$")
    requested_access_level: Optional[str] = None
    message: Optional[str] = None
    device_id: Optional[int] = None


class VendorAccessRequestCreate(VendorAccessRequestBase):
    vendor_profile_id: int


class VendorAccessRequestReview(BaseModel):
    status: str = Field(..., pattern="^(approved|denied)$")
    approval_notes: Optional[str] = None
    access_granted_until: Optional[datetime] = None
    granted_permissions: Optional[Dict[str, Any]] = None


class VendorAccessRequestResponse(VendorAccessRequestBase):
    id: int
    vendor_profile_id: int
    user_id: int
    user_role: str
    user_organization: Optional[str] = None
    user_department: Optional[str] = None
    user_title: Optional[str] = None
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    approval_notes: Optional[str] = None
    access_granted_until: Optional[datetime] = None
    granted_permissions: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


# Lead Schemas
class VendorLeadBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    
    # Professional info
    organization_name: Optional[str] = None
    organization_type: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    
    # Location
    city: Optional[str] = None
    state_province: Optional[str] = None
    country: Optional[str] = None
    
    # Preferences
    email_opt_in: bool = True
    phone_opt_in: bool = False
    preferred_contact_method: Optional[str] = None
    preferred_contact_time: Optional[str] = None
    
    # GDPR
    consent_given: bool = False
    privacy_policy_version: Optional[str] = None


class VendorLeadCapture(VendorLeadBase):
    """Lead capture from public page"""
    vendor_profile_id: int
    source_type: str
    source_url: Optional[str] = None
    device_id: Optional[int] = None
    referrer_url: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    
    # Interest tracking
    interested_devices: Optional[List[int]] = []
    search_queries: Optional[List[str]] = []


class VendorLeadUpdate(BaseModel):
    status: Optional[LeadStatus] = None
    assigned_to: Optional[int] = None
    qualified: Optional[bool] = None
    qualification_notes: Optional[str] = None
    next_follow_up: Optional[datetime] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class VendorLeadResponse(VendorLeadBase):
    id: int
    vendor_profile_id: int
    organization_id: int
    lead_score: int
    status: str
    assigned_to: Optional[int] = None
    assigned_at: Optional[datetime] = None
    qualified: Optional[bool] = None
    converted: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class VendorLeadActivityCreate(BaseModel):
    lead_id: int
    activity_type: str
    activity_description: Optional[str] = None
    device_id: Optional[int] = None
    communication_channel: Optional[str] = None
    communication_direction: Optional[str] = None
    outcome: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


# Service Request Schemas
class ServiceRequestBase(BaseModel):
    service_type: str
    urgency: ServiceUrgency
    device_id: Optional[int] = None
    device_serial_number: Optional[str] = None
    device_location: Optional[str] = None
    issue_description: str
    symptoms: Optional[List[str]] = []
    error_codes: Optional[List[str]] = []
    preferred_dates: Optional[List[Dict[str, Any]]] = None
    availability_notes: Optional[str] = None
    on_site_required: bool = True


class ServiceRequestCreate(ServiceRequestBase):
    vendor_profile_id: int


class ServiceRequestUpdate(BaseModel):
    assigned_rep_id: Optional[int] = None
    scheduled_date: Optional[datetime] = None
    scheduled_duration_minutes: Optional[int] = None
    status: Optional[ServiceRequestStatus] = None
    assignment_notes: Optional[str] = None
    internal_notes: Optional[str] = None


class ServiceRequestComplete(BaseModel):
    service_report: str
    parts_used: Optional[List[Dict[str, Any]]] = None
    follow_up_required: bool = False
    follow_up_notes: Optional[str] = None
    actual_cost: Optional[str] = None
    invoice_number: Optional[str] = None


class ServiceRequestResponse(ServiceRequestBase):
    id: int
    request_number: str
    vendor_profile_id: int
    organization_id: int
    requester_id: int
    requester_organization_id: int
    assigned_rep_id: Optional[int] = None
    assigned_at: Optional[datetime] = None
    scheduled_date: Optional[datetime] = None
    status: str
    sla_deadline: Optional[datetime] = None
    is_overdue: bool
    service_completed_at: Optional[datetime] = None
    satisfaction_rating: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class ServiceCommunicationCreate(BaseModel):
    service_request_id: int
    message_type: str
    message: str
    attachments: Optional[List[Dict[str, Any]]] = None
    is_internal: bool = False
    proposed_dates: Optional[List[Dict[str, Any]]] = None


class ServiceCommunicationResponse(BaseModel):
    id: int
    service_request_id: int
    sender_id: int
    sender_type: str
    message_type: str
    message: str
    attachments: Optional[List[Dict[str, Any]]] = None
    is_internal: bool
    read_by: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    
    class Config:
        orm_mode = True


# Chat Knowledge Schemas
class VendorChatKnowledgeCreate(BaseModel):
    vendor_profile_id: int
    question: str
    answer: str
    category: Optional[str] = None
    device_id: Optional[int] = None
    keywords: Optional[List[str]] = []
    is_public: bool = True
    required_roles: Optional[List[str]] = []


class VendorChatKnowledgeUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    keywords: Optional[List[str]] = None
    is_public: Optional[bool] = None
    required_roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    approved: Optional[bool] = None


class VendorChatKnowledgeResponse(BaseModel):
    id: int
    vendor_profile_id: int
    question: str
    answer: str
    category: Optional[str] = None
    device_id: Optional[int] = None
    keywords: List[str] = []
    is_public: bool
    required_roles: List[str] = []
    usage_count: int
    helpful_count: int
    not_helpful_count: int
    effectiveness_score: float
    is_active: bool
    approved: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


# Analytics Schemas
class VendorPageAnalyticsResponse(BaseModel):
    id: int
    vendor_profile_id: int
    date: datetime
    page_views: int
    unique_visitors: int
    avg_time_on_page: int
    bounce_rate: float
    device_clicks: int
    document_downloads: int
    video_plays: int
    chat_initiations: int
    leads_captured: int
    access_requests: int
    demo_requests: int
    contact_form_submissions: int
    traffic_sources: Optional[Dict[str, int]] = None
    device_types: Optional[Dict[str, int]] = None
    visitor_locations: Optional[Dict[str, int]] = None
    top_devices_viewed: Optional[List[Dict[str, Any]]] = None
    top_documents_downloaded: Optional[List[Dict[str, Any]]] = None
    top_search_queries: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        orm_mode = True


# Rep Availability Schemas
class RepAvailabilityCreate(BaseModel):
    user_id: int
    vendor_profile_id: int
    date: datetime
    start_time: datetime
    end_time: datetime
    max_appointments: int = 1
    available_service_types: List[str]
    coverage_area: Optional[Dict[str, Any]] = None
    is_recurring: bool = False
    recurrence_pattern: Optional[Dict[str, Any]] = None


class RepAvailabilityUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    max_appointments: Optional[int] = None
    available_service_types: Optional[List[str]] = None
    coverage_area: Optional[Dict[str, Any]] = None
    is_available: Optional[bool] = None
    block_reason: Optional[str] = None


class RepAvailabilityResponse(BaseModel):
    id: int
    user_id: int
    vendor_profile_id: int
    date: datetime
    start_time: datetime
    end_time: datetime
    max_appointments: int
    booked_appointments: int
    available_service_types: List[str]
    coverage_area: Optional[Dict[str, Any]] = None
    is_available: bool
    has_capacity: bool
    capacity_percentage: float
    created_at: datetime
    
    class Config:
        orm_mode = True


# Vendor Device List Schema
class VendorDevicePublic(BaseModel):
    """Public view of vendor device"""
    id: int
    display_name: str
    manufacturer_name: str
    device_class: Optional[str] = None
    custom_name: Optional[str] = None
    features: Optional[List[Any]] = []
    training_required: bool
    certification_required: bool
    is_available: bool
    
    class Config:
        orm_mode = True


class VendorPageDeviceList(BaseModel):
    """Response for vendor page device listing"""
    vendor_profile: VendorProfilePublic
    devices: List[VendorDevicePublic]
    total_count: int
    page: int
    limit: int
    
    class Config:
        orm_mode = True
