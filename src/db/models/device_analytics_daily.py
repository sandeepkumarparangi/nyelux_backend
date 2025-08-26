from sqlalchemy import (
    Column, Integer, Date, ForeignKey, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from datetime import date, timedelta

from src.db.base_class import Base


class DeviceAnalyticsDaily(Base):
    """
    Pre-aggregated daily metrics for device performance.
    Populated by background jobs for fast dashboard queries.
    """
    __tablename__ = "device_analytics_daily"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Device and organization
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    
    # Date
    date = Column(Date, nullable=False)
    
    # View metrics
    view_count = Column(Integer, nullable=False, default=0)
    unique_viewers = Column(Integer, nullable=False, default=0)
    
    # Search metrics
    search_appearances = Column(Integer, nullable=False, default=0, comment="Times shown in search results")
    search_clicks = Column(Integer, nullable=False, default=0, comment="Times clicked from search")
    
    # Content engagement
    document_downloads = Column(Integer, nullable=False, default=0)
    video_views = Column(Integer, nullable=False, default=0)
    
    # Support metrics
    chat_sessions = Column(Integer, nullable=False, default=0)
    incidents_reported = Column(Integer, nullable=False, default=0)
    
    # Engagement metrics
    average_engagement_time = Column(Integer, nullable=True, comment="Average time spent in seconds")
    
    # Relationships
    device = relationship("VendorDevice")
    organization = relationship("Organization")
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('device_id', 'organization_id', 'date', name='uq_device_org_date'),
        CheckConstraint("view_count >= 0", name='check_views_positive'),
        CheckConstraint("unique_viewers >= 0", name='check_viewers_positive'),
        CheckConstraint("unique_viewers <= view_count", name='check_viewers_lte_views'),
        CheckConstraint("search_clicks <= search_appearances", name='check_clicks_lte_appearances'),
        Index('idx_analytics_date_device', 'date', 'device_id'),
        Index('idx_analytics_device_date', 'device_id', 'date'),
        Index('idx_analytics_org_date', 'organization_id', 'date'),
    )
    
    @property
    def click_through_rate(self) -> float:
        """Calculate search click-through rate"""
        if self.search_appearances == 0:
            return 0.0
        return (self.search_clicks / self.search_appearances) * 100
    
    @property
    def engagement_score(self) -> float:
        """Calculate overall engagement score (0-100)"""
        # Weighted score based on different interactions
        weights = {
            'views': 1,
            'downloads': 5,
            'videos': 3,
            'chats': 10,
            'incidents': 2  # Lower weight as incidents aren't necessarily positive
        }
        
        score = (
            (self.unique_viewers * weights['views']) +
            (self.document_downloads * weights['downloads']) +
            (self.video_views * weights['videos']) +
            (self.chat_sessions * weights['chats']) +
            (self.incidents_reported * weights['incidents'])
        )
        
        # Normalize to 0-100 scale (adjust max_score based on expected values)
        max_score = 1000
        return min(100, (score / max_score) * 100)
    
    @property
    def is_today(self) -> bool:
        """Check if this is today's data"""
        return self.date == date.today()
    
    @property
    def is_current_week(self) -> bool:
        """Check if this is from current week"""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        return self.date >= week_start
    
    @property
    def is_current_month(self) -> bool:
        """Check if this is from current month"""
        today = date.today()
        return self.date.year == today.year and self.date.month == today.month
    
    @classmethod
    def aggregate_period(cls, daily_records: list) -> dict:
        """Aggregate multiple daily records into period totals"""
        if not daily_records:
            return {
                'view_count': 0,
                'unique_viewers': 0,
                'search_appearances': 0,
                'search_clicks': 0,
                'document_downloads': 0,
                'video_views': 0,
                'chat_sessions': 0,
                'incidents_reported': 0,
                'average_engagement_time': 0,
                'click_through_rate': 0.0,
                'engagement_score': 0.0,
            }
        
        # Sum all metrics
        totals = {
            'view_count': sum(r.view_count for r in daily_records),
            'unique_viewers': sum(r.unique_viewers for r in daily_records),
            'search_appearances': sum(r.search_appearances for r in daily_records),
            'search_clicks': sum(r.search_clicks for r in daily_records),
            'document_downloads': sum(r.document_downloads for r in daily_records),
            'video_views': sum(r.video_views for r in daily_records),
            'chat_sessions': sum(r.chat_sessions for r in daily_records),
            'incidents_reported': sum(r.incidents_reported for r in daily_records),
        }
        
        # Calculate averages
        engagement_times = [r.average_engagement_time for r in daily_records if r.average_engagement_time]
        totals['average_engagement_time'] = sum(engagement_times) // len(engagement_times) if engagement_times else 0
        
        # Calculate rates
        totals['click_through_rate'] = (
            (totals['search_clicks'] / totals['search_appearances'] * 100) 
            if totals['search_appearances'] > 0 else 0.0
        )
        
        # Average engagement score
        totals['engagement_score'] = sum(r.engagement_score for r in daily_records) / len(daily_records)
        
        return totals
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "device_id": self.device_id,
            "organization_id": self.organization_id,
            "date": self.date.isoformat() if self.date else None,
            "view_count": self.view_count,
            "unique_viewers": self.unique_viewers,
            "search_appearances": self.search_appearances,
            "search_clicks": self.search_clicks,
            "click_through_rate": round(self.click_through_rate, 1),
            "document_downloads": self.document_downloads,
            "video_views": self.video_views,
            "chat_sessions": self.chat_sessions,
            "incidents_reported": self.incidents_reported,
            "average_engagement_time": self.average_engagement_time,
            "engagement_score": round(self.engagement_score, 1),
        }
    
    def __repr__(self):
        return f"<DeviceAnalyticsDaily device_{self.device_id} on {self.date}>"
