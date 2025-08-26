"""
Analytics schemas.
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

from src.schemas.base import BaseSchema, TimestampMixin


# Analytics Event Schemas
class AnalyticsEventCreate(BaseSchema):
    """Create analytics event"""
    event_type: str = Field(..., max_length=100)
    event_category: Literal["engagement", "search", "support", "system"]
    resource_type: Optional[str] = Field(None, max_length=50)
    resource_id: Optional[str] = Field(None, max_length=255)
    action: Optional[str] = Field(None, max_length=100)
    label: Optional[str] = None
    value: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = Field(None, max_length=100)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# Device Analytics
class DeviceMetrics(BaseSchema):
    """Device metrics for a time period"""
    date: Optional[str] = None
    period: Optional[str] = None
    view_count: int = 0
    unique_viewers: int = 0
    search_appearances: int = 0
    search_clicks: int = 0
    document_downloads: int = 0
    video_views: int = 0
    chat_sessions: int = 0
    incidents_reported: int = 0
    average_engagement_time: Optional[int] = None


class DeviceEngagementMetrics(BaseSchema):
    """Device engagement metrics"""
    unique_users: int
    engagement_rate: float
    download_conversion_rate: float
    return_visitor_rate: float


class DeviceIncidentMetrics(BaseSchema):
    """Device incident metrics"""
    total_incidents: int
    by_type: Dict[str, int]
    by_urgency: Dict[str, int]
    average_resolution_time_hours: float


class DeviceAnalyticsResponse(BaseSchema):
    """Complete device analytics response"""
    device_id: int
    period: Dict[str, str]
    summary: Dict[str, int]
    time_series: List[DeviceMetrics]
    event_breakdown: Dict[str, int]
    engagement: DeviceEngagementMetrics
    incidents: DeviceIncidentMetrics
    trends: Dict[str, float]


# Organization Dashboard
class OrganizationMetrics(BaseSchema):
    """Organization summary metrics"""
    total_users: int
    active_users: int
    user_engagement_rate: float
    total_events: int


class TopDevice(BaseSchema):
    """Top performing device"""
    device_id: int
    device_name: str
    views: int
    unique_viewers: int


class UserActivityPattern(BaseSchema):
    """User activity patterns"""
    hourly_distribution: Dict[int, int]
    daily_distribution: Dict[int, int]


class SearchInsights(BaseSchema):
    """Search behavior insights"""
    top_queries: List[Dict[str, Any]]
    total_searches: int
    success_rate: float
    avg_search_time_ms: int


class OrganizationDashboardResponse(BaseSchema):
    """Organization dashboard data"""
    organization_id: int
    period: Dict[str, str]
    summary: OrganizationMetrics
    top_devices: List[TopDevice]
    user_activity: UserActivityPattern
    search_insights: SearchInsights
    support_metrics: Dict[str, Any]
    generated_at: str


# Search Analytics
class SearchQuery(BaseSchema):
    """Search query analytics"""
    query: str
    count: int
    avg_results: int
    avg_duration_ms: int


class SearchVolume(BaseSchema):
    """Search volume by date"""
    date: str
    searches: int
    unique_users: int


class SearchAnalyticsResponse(BaseSchema):
    """Search analytics response"""
    period: Dict[str, str]
    top_searches: List[SearchQuery]
    no_results_searches: List[Dict[str, Any]]
    search_volume: List[SearchVolume]


# User Activity
class UserActivityResponse(BaseSchema):
    """User activity analytics"""
    period: Dict[str, str]
    hourly_activity: Dict[int, Dict[str, int]]
    top_devices: List[Dict[str, Any]]


# Incident Analytics
class IncidentAnalyticsResponse(BaseSchema):
    """Incident analytics response"""
    total_incidents: int
    status_distribution: Dict[str, int]
    urgency_distribution: Dict[str, int]
    type_distribution: Dict[str, int]
    fda_reportable_count: int
    average_response_time_hours: float
    average_resolution_time_hours: float
    sla_compliance_rate: float
    sla_compliant_count: int
    sla_breached_count: int


# Real-time Metrics
class RealtimeMetrics(BaseSchema):
    """Real-time activity metrics"""
    timestamp: str
    active_users: int
    events_per_minute: List[Dict[str, Any]]
    current_pages: List[Dict[str, Any]]


# Engagement Metrics
class EngagementMetrics(BaseSchema):
    """Device engagement metrics"""
    device_id: int
    device_name: str
    total_views: int
    unique_viewers: int
    engagement_rate: float
    conversion_rate: float


# Trend Analysis
class TrendAnalysis(BaseSchema):
    """Trend analysis for metrics"""
    metric: str
    period_days: int
    data_points: List[Dict[str, Any]]
    trend_direction: Literal["up", "down", "stable"]
    change_percent: float
    average_daily_value: float


# Export Request
class ExportRequest(BaseSchema):
    """Analytics export request"""
    export_type: Literal["events", "devices", "users", "searches", "incidents"]
    start_date: datetime
    end_date: datetime
    format: Literal["csv", "json", "excel"] = "csv"
    filters: Optional[Dict[str, Any]] = None
