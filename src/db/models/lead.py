"""
Lead model for tracking potential customers.

CRITICAL for business: Captures and scores leads from public access.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, DECIMAL, Enum, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from src.db.base_class import Base


class LeadSource(str, enum.Enum):
    """Lead source tracking"""
    SEARCH_LIMIT = "search_limit"  # Hit anonymous search limit
    INFO_REQUEST = "info_request"  # Requested device information
    DEMO_REQUEST = "demo_request"  # Requested product demo
    CONTACT_FORM = "contact_form"  # Filled contact form
    WEBINAR = "webinar"  # Webinar registration
    CONTENT_DOWNLOAD = "content_download"  # Downloaded gated content
    TRIAL_SIGNUP = "trial_signup"  # Started free trial


class LeadStatus(str, enum.Enum):
    """Lead lifecycle status"""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    OPPORTUNITY = "opportunity"
    CUSTOMER = "customer"
    LOST = "lost"


class Lead(Base):
    """
    Lead tracking for sales and marketing.
    
    Captures visitor behavior and progressive information disclosure
    to convert anonymous users into qualified leads.
    """
    __tablename__ = 'leads'
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Visitor tracking
    visitor_id = Column(String(100), unique=True, index=True)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    referrer = Column(Text)
    
    # Contact information (progressive capture)
    email = Column(String(255), unique=True, index=True, nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(20))
    title = Column(String(100))
    
    # Organization information
    organization_name = Column(String(255))
    organization_type = Column(String(50))  # hospital, clinic, vendor
    organization_size = Column(String(50))  # 1-10, 11-50, 51-200, etc
    department = Column(String(100))
    
    # Lead scoring and qualification
    lead_score = Column(Integer, default=0)  # 0-100
    lead_source = Column(Enum(LeadSource), nullable=False)
    lead_status = Column(Enum(LeadStatus), default=LeadStatus.NEW)
    
    # Behavioral data
    search_queries = Column(JSON)  # List of searches performed
    devices_viewed = Column(JSON)  # List of device IDs viewed
    search_count = Column(Integer, default=0)
    page_views = Column(Integer, default=0)
    time_on_site_seconds = Column(Integer, default=0)
    info_requests = Column(Integer, default=0)
    
    # Marketing attribution
    utm_source = Column(String(100))
    utm_medium = Column(String(100))
    utm_campaign = Column(String(100))
    utm_term = Column(String(100))
    utm_content = Column(String(100))
    
    # Sales tracking
    assigned_to = Column(String(100))  # Sales rep email/ID
    contacted_at = Column(DateTime(timezone=True))
    qualified_at = Column(DateTime(timezone=True))
    converted_at = Column(DateTime(timezone=True))
    lost_reason = Column(Text)
    
    # Activity tracking
    last_activity_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    notes = Column(Text)
    
    # Conversion
    converted_user_id = Column(Integer)  # If converted to registered user
    converted_organization_id = Column(Integer)  # If converted to customer
    
    # Email marketing
    email_verified = Column(Boolean, default=False)
    email_opt_in = Column(Boolean, default=True)
    unsubscribed_at = Column(DateTime(timezone=True))
    
    def calculate_lead_score(self) -> int:
        """
        Calculate lead score based on engagement and profile.
        
        Scoring factors:
        - Email provided: +10
        - Name provided: +10
        - Organization provided: +15
        - Phone provided: +5
        - Each search: +2 (max 20)
        - Each device view: +3 (max 30)
        - Info request: +20
        - Time on site: +1 per minute (max 10)
        """
        score = 0
        
        # Profile completeness
        if self.email:
            score += 10
        if self.first_name and self.last_name:
            score += 10
        if self.organization_name:
            score += 15
        if self.phone:
            score += 5
        
        # Engagement
        if self.search_count:
            score += min(self.search_count * 2, 20)
        if self.devices_viewed:
            score += min(len(self.devices_viewed) * 3, 30)
        if self.info_requests:
            score += self.info_requests * 20
        if self.time_on_site_seconds:
            score += min(self.time_on_site_seconds // 60, 10)
        
        # Source bonus
        if self.lead_source == LeadSource.DEMO_REQUEST:
            score += 20
        elif self.lead_source == LeadSource.TRIAL_SIGNUP:
            score += 30
        
        self.lead_score = min(score, 100)
        return self.lead_score
    
    def is_qualified(self) -> bool:
        """Check if lead meets qualification criteria."""
        return (
            self.lead_score >= 50 and
            self.email and
            self.organization_name and
            (self.first_name or self.last_name)
        )
    
    def days_since_last_activity(self) -> int:
        """Calculate days since last activity."""
        if self.last_activity_at:
            return (datetime.utcnow() - self.last_activity_at).days
        return 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "organization_name": self.organization_name,
            "lead_score": self.lead_score,
            "lead_source": self.lead_source.value if self.lead_source else None,
            "lead_status": self.lead_status.value if self.lead_status else None,
            "is_qualified": self.is_qualified(),
            "days_since_activity": self.days_since_last_activity(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
        }
