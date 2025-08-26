from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, DECIMAL, Date,
    Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, INET

from src.db.base_class import Base

class AnalyticsEvent(Base):
    """
    Track all user interactions for analytics.
    High-volume table optimized for write performance.
    """
    __tablename__ = "analytics_events"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User and organization
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    
    # Event details
    event_type = Column(String(100), nullable=False, index=True)
    event_category = Column(String(50), nullable=True, index=True)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(255), nullable=True)
    action = Column(String(100), nullable=True)
    label = Column(Text, nullable=True)
    value = Column(DECIMAL(10, 2), nullable=True)
    
    # Additional event data
    event_metadata = Column(JSONB, nullable=True)
    
    # Page context
    page_url = Column(Text, nullable=True)
    referrer_url = Column(Text, nullable=True)
    
    # Client information
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    device_type = Column(String(20), nullable=True)  # desktop, mobile, tablet
    browser = Column(String(50), nullable=True)
    os = Column(String(50), nullable=True)
    
    # Geolocation
    country_code = Column(String(2), nullable=True)
    region = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    
    # Timestamp is critical for analytics
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Relationships
    user = relationship("User", back_populates="analytics_events")
    
    # Indexes optimized for common queries
    __table_args__ = (
        # Composite indexes for performance
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_org_type_created', 'organization_id', 'event_type', 'created_at'),
        Index('idx_session', 'session_id'),
        Index('idx_resource', 'resource_type', 'resource_id'),
        
        # Partial indexes for specific event types
        Index('idx_page_views', 'created_at', 'page_url', 
              postgresql_where="event_type = 'page_view'"),
        Index('idx_device_views', 'resource_id', 'created_at',
              postgresql_where="event_type = 'device_view'"),
    )
    
    @classmethod
    def track_page_view(cls, user_id: int, page_url: str, session_id: str, **kwargs):
        """Factory method for page view events"""
        return cls(
            user_id=user_id,
            session_id=session_id,
            event_type='page_view',
            event_category='navigation',
            page_url=page_url,
            **kwargs
        )
    
    @classmethod
    def track_search(cls, user_id: int, query: str, results_count: int, **kwargs):
        """Factory method for search events"""
        return cls(
            user_id=user_id,
            event_type='search',
            event_category='engagement',
            action='search_performed',
            label=query,
            value=results_count,
            **kwargs
        )
    
    @classmethod
    def track_device_view(cls, user_id: int, device_id: int, **kwargs):
        """Factory method for device view events"""
        return cls(
            user_id=user_id,
            event_type='device_view',
            event_category='engagement',
            resource_type='device',
            resource_id=str(device_id),
            **kwargs
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "event_category": self.event_category,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "label": self.label,
            "value": float(self.value) if self.value else None,
            "page_url": self.page_url,
            "device_type": self.device_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<AnalyticsEvent {self.event_type}:{self.id}>"
