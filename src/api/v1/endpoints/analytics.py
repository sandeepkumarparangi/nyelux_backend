"""
Analytics API endpoints.
REAL implementation for device and organization analytics.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import Any, List, Optional, Literal
from datetime import datetime, timedelta, date
import logging

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.organization import Organization
from src.services.auth_service import get_current_active_user, require_role
from src.services.analytics_service import AnalyticsService
from src.schemas.base import SuccessResponse
from src.schemas.analytics import (
    DeviceAnalyticsResponse,
    OrganizationDashboardResponse,
    SearchAnalyticsResponse,
    UserActivityResponse,
    IncidentAnalyticsResponse,
    ExportRequest,
    AnalyticsEventCreate,
    RealtimeMetrics,
    EngagementMetrics,
    TrendAnalysis
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Create service instance for this router
analytics_service = AnalyticsService()


@router.post("/events", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
async def track_analytics_event(
    *,
    db: AsyncSession = Depends(get_db),
    event_in: AnalyticsEventCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Track analytics event.
    
    Used by frontend to track user interactions in real-time.
    """
    try:
        event = await analytics_service.track_event(
            db=db,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type=event_in.event_type,
            event_category=event_in.event_category,
            resource_type=event_in.resource_type,
            resource_id=event_in.resource_id,
            action=event_in.action,
            label=event_in.label,
            value=event_in.value,
            metadata=event_in.metadata,
            session_id=event_in.session_id,
            ip_address=event_in.ip_address,
            user_agent=event_in.user_agent
        )
        
        await db.commit()
        
        return SuccessResponse(
            message="Event tracked successfully"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/devices/{device_id}", response_model=DeviceAnalyticsResponse)
async def get_device_analytics(
    *,
    db: AsyncSession = Depends(get_db),
    device_id: int,
    current_user: User = Depends(get_current_active_user),
    start_date: datetime = Query(..., description="Start date for analytics period"),
    end_date: datetime = Query(..., description="End date for analytics period"),
    interval: Literal["daily", "weekly", "monthly", "quarterly", "yearly"] = Query("daily")
) -> Any:
    """
    Get comprehensive analytics for a specific device.
    
    Requires vendor access to the device.
    """
    # Verify access - vendors can see their own devices
    if current_user.role in ["vendor_admin", "vendor_rep"]:
        from src.db.models.vendor_device import VendorDevice
        device = await db.get(VendorDevice, device_id)
        
        if not device or device.organization_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view analytics for this device"
            )
    
    try:
        analytics = await analytics_service.get_device_analytics(
            db=db,
            device_id=device_id,
            start_date=start_date,
            end_date=end_date,
            interval=interval
        )
        
        return DeviceAnalyticsResponse(**analytics)
        
    except Exception as e:
        logger.error(f"Device analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate analytics"
        )


@router.get("/organization/dashboard", response_model=OrganizationDashboardResponse)
async def get_organization_dashboard(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    period: Literal["last_7_days", "last_30_days", "last_90_days"] = Query("last_30_days"),
    organization_id: Optional[int] = Query(None, description="Organization ID (admin only)")
) -> Any:
    """
    Get comprehensive dashboard for organization.
    
    Shows different metrics based on organization type (vendor vs healthcare).
    """
    # Determine organization
    if organization_id and current_user.role == "super_admin":
        org_id = organization_id
    else:
        org_id = current_user.organization_id
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization ID required"
        )
    
    # Verify access
    if org_id != current_user.organization_id and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this organization's dashboard"
        )
    
    try:
        dashboard = await analytics_service.get_organization_dashboard(
            db=db,
            organization_id=org_id,
            period=period
        )
        
        return OrganizationDashboardResponse(**dashboard)
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate dashboard"
        )


@router.get("/search", response_model=SearchAnalyticsResponse)
async def get_search_analytics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["org_admin", "super_admin"])),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    organization_id: Optional[int] = Query(None)
) -> Any:
    """
    Get search behavior analytics.
    
    Shows popular searches, success rates, and trends.
    """
    # Determine organization
    if organization_id and current_user.role == "super_admin":
        org_id = organization_id
    else:
        org_id = current_user.organization_id
    
    # Get search insights
    from src.db.models.search_history import SearchHistory
    
    # Top searches
    top_searches = await db.execute(
        select(
            SearchHistory.search_query,
            func.count(SearchHistory.id).label('count'),
            func.avg(SearchHistory.results_count).label('avg_results'),
            func.avg(SearchHistory.search_duration_ms).label('avg_duration')
        ).where(
            and_(
                SearchHistory.organization_id == org_id if org_id else True,
                SearchHistory.created_at >= start_date,
                SearchHistory.created_at <= end_date
            )
        ).group_by(SearchHistory.search_query)
        .order_by(func.count(SearchHistory.id).desc())
        .limit(50)
    )
    
    # No results searches
    no_results = await db.execute(
        select(
            SearchHistory.search_query,
            func.count(SearchHistory.id).label('count')
        ).where(
            and_(
                SearchHistory.organization_id == org_id if org_id else True,
                SearchHistory.results_count == 0,
                SearchHistory.created_at >= start_date,
                SearchHistory.created_at <= end_date
            )
        ).group_by(SearchHistory.search_query)
        .order_by(func.count(SearchHistory.id).desc())
        .limit(20)
    )
    
    # Search volume over time
    volume_by_day = await db.execute(
        select(
            func.date(SearchHistory.created_at).label('date'),
            func.count(SearchHistory.id).label('searches'),
            func.count(func.distinct(SearchHistory.user_id)).label('unique_users')
        ).where(
            and_(
                SearchHistory.organization_id == org_id if org_id else True,
                SearchHistory.created_at >= start_date,
                SearchHistory.created_at <= end_date
            )
        ).group_by(func.date(SearchHistory.created_at))
        .order_by(func.date(SearchHistory.created_at))
    )
    
    return SearchAnalyticsResponse(
        period={
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        top_searches=[
            {
                "query": row.search_query,
                "count": row.count,
                "avg_results": int(row.avg_results),
                "avg_duration_ms": int(row.avg_duration)
            }
            for row in top_searches
        ],
        no_results_searches=[
            {
                "query": row.search_query,
                "count": row.count
            }
            for row in no_results
        ],
        search_volume=[
            {
                "date": row.date.isoformat(),
                "searches": row.searches,
                "unique_users": row.unique_users
            }
            for row in volume_by_day
        ]
    )


@router.get("/users/activity", response_model=UserActivityResponse)
async def get_user_activity_analytics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["org_admin", "super_admin"])),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    user_id: Optional[int] = Query(None, description="Specific user (admin only)")
) -> Any:
    """
    Get user activity patterns and engagement metrics.
    """
    # Verify access to user data
    if user_id:
        if current_user.role != "super_admin":
            target_user = await db.get(User, user_id)
            if not target_user or target_user.organization_id != current_user.organization_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this user's activity"
                )
    
    # Get activity patterns
    from src.db.models.analytics_event import AnalyticsEvent
    
    # Activity by hour
    hourly_activity = await db.execute(
        select(
            func.extract('hour', AnalyticsEvent.created_at).label('hour'),
            func.count(AnalyticsEvent.id).label('events'),
            func.count(func.distinct(AnalyticsEvent.user_id)).label('active_users')
        ).where(
            and_(
                AnalyticsEvent.user_id == user_id if user_id else True,
                AnalyticsEvent.organization_id == current_user.organization_id,
                AnalyticsEvent.created_at >= start_date,
                AnalyticsEvent.created_at <= end_date
            )
        ).group_by(func.extract('hour', AnalyticsEvent.created_at))
        .order_by(func.extract('hour', AnalyticsEvent.created_at))
    )
    
    # Most viewed devices
    device_views = await db.execute(
        select(
            AnalyticsEvent.resource_id,
            func.count(AnalyticsEvent.id).label('views')
        ).where(
            and_(
                AnalyticsEvent.user_id == user_id if user_id else True,
                AnalyticsEvent.organization_id == current_user.organization_id,
                AnalyticsEvent.event_type == 'device_view',
                AnalyticsEvent.created_at >= start_date,
                AnalyticsEvent.created_at <= end_date
            )
        ).group_by(AnalyticsEvent.resource_id)
        .order_by(func.count(AnalyticsEvent.id).desc())
        .limit(20)
    )
    
    return UserActivityResponse(
        period={
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        hourly_activity={
            int(row.hour): {
                "events": row.events,
                "active_users": row.active_users
            }
            for row in hourly_activity
        },
        top_devices=[
            {
                "device_id": int(row.resource_id) if row.resource_id else None,
                "views": row.views
            }
            for row in device_views if row.resource_id
        ]
    )


@router.get("/incidents", response_model=IncidentAnalyticsResponse)
async def get_incident_analytics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["vendor_admin", "vendor_rep", "org_admin", "super_admin"])),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    device_id: Optional[int] = Query(None)
) -> Any:
    """
    Get incident and support metrics.
    
    Vendors see their device incidents, admins see all.
    """
    from src.services.support_service import SupportService
    
    # Create instance
    support_service = SupportService()
    
    # Determine filter
    organization_id = None
    if current_user.role in ["vendor_admin", "vendor_rep"]:
        organization_id = current_user.organization_id
    
    try:
        metrics = await support_service.get_incident_metrics(
            db=db,
            organization_id=organization_id,
            device_id=device_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return IncidentAnalyticsResponse(**metrics)
        
    except Exception as e:
        logger.error(f"Incident analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate incident analytics"
        )


@router.get("/realtime", response_model=RealtimeMetrics)
async def get_realtime_metrics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["org_admin", "super_admin"]))
) -> Any:
    """
    Get real-time metrics for monitoring.
    
    Updates every minute with current activity.
    """
    # Get metrics from last 5 minutes
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    
    from src.db.models.analytics_event import AnalyticsEvent
    
    # Active users
    active_users = await db.execute(
        select(func.count(func.distinct(AnalyticsEvent.user_id))).where(
            and_(
                AnalyticsEvent.organization_id == current_user.organization_id,
                AnalyticsEvent.created_at >= cutoff
            )
        )
    )
    
    # Events per minute
    events = await db.execute(
        select(
            func.date_trunc('minute', AnalyticsEvent.created_at).label('minute'),
            func.count(AnalyticsEvent.id).label('count')
        ).where(
            and_(
                AnalyticsEvent.organization_id == current_user.organization_id,
                AnalyticsEvent.created_at >= cutoff
            )
        ).group_by(func.date_trunc('minute', AnalyticsEvent.created_at))
        .order_by(func.date_trunc('minute', AnalyticsEvent.created_at))
    )
    
    # Current page views
    page_views = await db.execute(
        select(
            AnalyticsEvent.page_url,
            func.count(func.distinct(AnalyticsEvent.user_id)).label('users')
        ).where(
            and_(
                AnalyticsEvent.organization_id == current_user.organization_id,
                AnalyticsEvent.event_type == 'page_view',
                AnalyticsEvent.created_at >= cutoff
            )
        ).group_by(AnalyticsEvent.page_url)
        .order_by(func.count(func.distinct(AnalyticsEvent.user_id)).desc())
        .limit(10)
    )
    
    return RealtimeMetrics(
        timestamp=datetime.utcnow().isoformat(),
        active_users=active_users.scalar() or 0,
        events_per_minute=[
            {
                "minute": row.minute.isoformat(),
                "count": row.count
            }
            for row in events
        ],
        current_pages=[
            {
                "url": row.page_url,
                "users": row.users
            }
            for row in page_views if row.page_url
        ]
    )


@router.post("/export", response_model=dict)
async def export_analytics_data(
    *,
    db: AsyncSession = Depends(get_db),
    export_request: ExportRequest,
    current_user: User = Depends(require_role(["org_admin", "super_admin"])),
    response: Response
) -> Any:
    """
    Export analytics data in various formats.
    
    Returns downloadable file with requested data.
    """
    try:
        # Generate export
        export_data = await analytics_service.export_analytics_data(
            db=db,
            organization_id=current_user.organization_id,
            export_type=export_request.export_type,
            start_date=export_request.start_date,
            end_date=export_request.end_date,
            format=export_request.format
        )
        
        # Set response headers
        filename = f"analytics_{export_request.export_type}_{datetime.utcnow().strftime('%Y%m%d')}.{export_request.format}"
        
        if export_request.format == 'csv':
            content_type = 'text/csv'
        elif export_request.format == 'json':
            content_type = 'application/json'
        elif export_request.format == 'excel':
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-Type"] = content_type
        
        return Response(
            content=export_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export analytics data"
        )


@router.get("/engagement/devices", response_model=List[EngagementMetrics])
async def get_device_engagement_metrics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["vendor_admin", "vendor_rep"])),
    limit: int = Query(10, ge=1, le=50)
) -> Any:
    """
    Get engagement metrics for vendor's devices.
    
    Shows which devices have highest engagement.
    """
    from src.db.models.vendor_device import VendorDevice
    from src.db.models.device_analytics_daily import DeviceAnalyticsDaily
    
    # Get vendor's devices with metrics
    devices = await db.execute(
        select(
            VendorDevice.id,
            VendorDevice.custom_name,
            func.sum(DeviceAnalyticsDaily.view_count).label('total_views'),
            func.sum(DeviceAnalyticsDaily.unique_viewers).label('total_unique_viewers'),
            func.sum(DeviceAnalyticsDaily.document_downloads).label('total_downloads'),
            func.sum(DeviceAnalyticsDaily.chat_sessions).label('total_chats')
        ).join(
            DeviceAnalyticsDaily,
            DeviceAnalyticsDaily.device_id == VendorDevice.id
        ).where(
            and_(
                VendorDevice.organization_id == current_user.organization_id,
                DeviceAnalyticsDaily.date >= date.today() - timedelta(days=30)
            )
        ).group_by(VendorDevice.id, VendorDevice.custom_name)
        .order_by(func.sum(DeviceAnalyticsDaily.view_count).desc())
        .limit(limit)
    )
    
    return [
        EngagementMetrics(
            device_id=row.id,
            device_name=row.custom_name or f"Device {row.id}",
            total_views=row.total_views or 0,
            unique_viewers=row.total_unique_viewers or 0,
            engagement_rate=((row.total_downloads or 0) + (row.total_chats or 0)) / (row.total_views or 1) * 100,
            conversion_rate=(row.total_downloads or 0) / (row.total_views or 1) * 100
        )
        for row in devices
    ]


@router.get("/trends/{metric}", response_model=TrendAnalysis)
async def get_metric_trends(
    *,
    db: AsyncSession = Depends(get_db),
    metric: Literal["users", "devices", "searches", "incidents"],
    current_user: User = Depends(require_role(["org_admin", "super_admin"])),
    days: int = Query(30, ge=7, le=365)
) -> Any:
    """
    Get trend analysis for specific metric.
    
    Shows growth rates and predictions.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # Get daily data based on metric
    if metric == "users":
        # Active users per day
        from src.db.models.user import User
        daily_data = await db.execute(
            select(
                func.date(User.last_login_at).label('date'),
                func.count(func.distinct(User.id)).label('value')
            ).where(
                and_(
                    User.organization_id == current_user.organization_id,
                    User.last_login_at >= start_date,
                    User.last_login_at <= end_date
                )
            ).group_by(func.date(User.last_login_at))
            .order_by(func.date(User.last_login_at))
        )
    
    elif metric == "devices":
        # Device views per day
        from src.db.models.device_analytics_daily import DeviceAnalyticsDaily
        daily_data = await db.execute(
            select(
                DeviceAnalyticsDaily.date,
                func.sum(DeviceAnalyticsDaily.view_count).label('value')
            ).where(
                and_(
                    DeviceAnalyticsDaily.organization_id == current_user.organization_id,
                    DeviceAnalyticsDaily.date >= start_date,
                    DeviceAnalyticsDaily.date <= end_date
                )
            ).group_by(DeviceAnalyticsDaily.date)
            .order_by(DeviceAnalyticsDaily.date)
        )
    
    elif metric == "searches":
        # Searches per day
        from src.db.models.search_history import SearchHistory
        daily_data = await db.execute(
            select(
                func.date(SearchHistory.created_at).label('date'),
                func.count(SearchHistory.id).label('value')
            ).where(
                and_(
                    SearchHistory.organization_id == current_user.organization_id,
                    SearchHistory.created_at >= start_date,
                    SearchHistory.created_at <= end_date
                )
            ).group_by(func.date(SearchHistory.created_at))
            .order_by(func.date(SearchHistory.created_at))
        )
    
    else:  # incidents
        # Incidents per day
        from src.db.models.device_incident import DeviceIncident
        daily_data = await db.execute(
            select(
                func.date(DeviceIncident.created_at).label('date'),
                func.count(DeviceIncident.id).label('value')
            ).where(
                and_(
                    DeviceIncident.organization_id == current_user.organization_id,
                    DeviceIncident.created_at >= start_date,
                    DeviceIncident.created_at <= end_date
                )
            ).group_by(func.date(DeviceIncident.created_at))
            .order_by(func.date(DeviceIncident.created_at))
        )
    
    # Convert to list
    data_points = [
        {
            "date": row.date.isoformat(),
            "value": row.value
        }
        for row in daily_data
    ]
    
    # Calculate trend
    if len(data_points) >= 2:
        first_value = data_points[0]["value"]
        last_value = data_points[-1]["value"]
        change_percent = ((last_value - first_value) / first_value * 100) if first_value > 0 else 0
        trend_direction = "up" if change_percent > 0 else "down" if change_percent < 0 else "stable"
    else:
        change_percent = 0
        trend_direction = "stable"
    
    return TrendAnalysis(
        metric=metric,
        period_days=days,
        data_points=data_points,
        trend_direction=trend_direction,
        change_percent=round(change_percent, 2),
        average_daily_value=sum(d["value"] for d in data_points) / len(data_points) if data_points else 0
    )
