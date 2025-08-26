"""
Comprehensive Analytics Service
REAL implementation tracking every user action with real-time dashboards
"""
import json
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, date
from collections import defaultdict
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.sql import extract

from src.db.models.analytics_event import AnalyticsEvent
from src.db.models.device_analytics_daily import DeviceAnalyticsDaily
from src.db.models.search_history import SearchHistory
from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.vendor_device import VendorDevice
from src.core.redis_manager import RedisManager

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    REAL analytics service tracking all platform activity.
    Provides real-time and historical analytics with drill-down capabilities.
    """
    
    def __init__(self):
        self.redis_manager = RedisManager()
        self.event_queue = asyncio.Queue(maxsize=10000)
        self.batch_size = 100
        self.flush_interval = 5  # seconds
        
    async def track_event(
        self,
        db: AsyncSession,
        user_id: Optional[int],
        organization_id: Optional[int],
        event_type: str,
        event_category: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        request_context: Optional[Dict[str, Any]] = None
    ):
        """
        Track any user or system event.
        """
        # Create event record
        event = AnalyticsEvent(
            user_id=user_id,
            organization_id=organization_id,
            event_type=event_type,
            event_category=event_category,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=json.dumps(metadata) if metadata else None,
            session_id=request_context.get('session_id') if request_context else None,
            page_url=request_context.get('page_url') if request_context else None,
            referrer_url=request_context.get('referrer_url') if request_context else None,
            ip_address=request_context.get('ip_address') if request_context else None,
            user_agent=request_context.get('user_agent') if request_context else None,
            device_type=self._detect_device_type(request_context.get('user_agent')) if request_context else None,
            browser=self._detect_browser(request_context.get('user_agent')) if request_context else None,
            os=self._detect_os(request_context.get('user_agent')) if request_context else None,
            country_code=request_context.get('country_code') if request_context else None,
            region=request_context.get('region') if request_context else None,
            city=request_context.get('city') if request_context else None
        )
        
        # Queue for batch processing
        try:
            self.event_queue.put_nowait(event)
        except asyncio.QueueFull:
            # If queue is full, process synchronously
            db.add(event)
            await db.commit()
        
        # Update real-time counters in Redis
        await self._update_realtime_metrics(event)
        
        # Special handling for certain events
        if event_type == 'device_view' and resource_type == 'device' and resource_id:
            await self._update_device_analytics(db, int(resource_id), organization_id)
    
    async def _update_realtime_metrics(self, event: AnalyticsEvent):
        """Update real-time metrics in Redis."""
        now = datetime.utcnow()
        hour_key = now.strftime("%Y%m%d%H")
        
        # Increment counters
        keys = [
            f"analytics:events:{hour_key}:total",
            f"analytics:events:{hour_key}:{event.event_type}",
            f"analytics:events:{hour_key}:{event.event_category}"
        ]
        
        if event.organization_id:
            keys.append(f"analytics:org:{event.organization_id}:{hour_key}")
        
        for key in keys:
            await self.redis_manager.incr(key, expire=86400)  # 24 hour expiry
    
    async def _update_device_analytics(
        self,
        db: AsyncSession,
        device_id: int,
        organization_id: Optional[int]
    ):
        """Update device-specific analytics."""
        today = date.today()
        
        # Get or create daily record
        result = await db.execute(
            select(DeviceAnalyticsDaily).where(
                and_(
                    DeviceAnalyticsDaily.device_id == device_id,
                    DeviceAnalyticsDaily.organization_id == organization_id,
                    DeviceAnalyticsDaily.date == today
                )
            )
        )
        daily_stats = result.scalar_one_or_none()
        
        if not daily_stats:
            daily_stats = DeviceAnalyticsDaily(
                device_id=device_id,
                organization_id=organization_id,
                date=today
            )
            db.add(daily_stats)
        
        # Increment view count
        daily_stats.view_count += 1
        
        # TODO: Update unique viewers using HyperLogLog in Redis
        
        await db.commit()
    
    def _detect_device_type(self, user_agent: Optional[str]) -> Optional[str]:
        """Detect device type from user agent."""
        if not user_agent:
            return None
        
        user_agent_lower = user_agent.lower()
        if any(x in user_agent_lower for x in ['mobile', 'android', 'iphone', 'ipod']):
            return 'mobile'
        elif any(x in user_agent_lower for x in ['tablet', 'ipad']):
            return 'tablet'
        else:
            return 'desktop'
    
    def _detect_browser(self, user_agent: Optional[str]) -> Optional[str]:
        """Detect browser from user agent."""
        if not user_agent:
            return None
        
        user_agent_lower = user_agent.lower()
        if 'chrome' in user_agent_lower and 'edg' not in user_agent_lower:
            return 'Chrome'
        elif 'firefox' in user_agent_lower:
            return 'Firefox'
        elif 'safari' in user_agent_lower and 'chrome' not in user_agent_lower:
            return 'Safari'
        elif 'edg' in user_agent_lower:
            return 'Edge'
        else:
            return 'Other'
    
    def _detect_os(self, user_agent: Optional[str]) -> Optional[str]:
        """Detect OS from user agent."""
        if not user_agent:
            return None
        
        user_agent_lower = user_agent.lower()
        if 'windows' in user_agent_lower:
            return 'Windows'
        elif 'mac' in user_agent_lower:
            return 'macOS'
        elif 'linux' in user_agent_lower:
            return 'Linux'
        elif 'android' in user_agent_lower:
            return 'Android'
        elif 'ios' in user_agent_lower or 'iphone' in user_agent_lower:
            return 'iOS'
        else:
            return 'Other'
    
    async def process_event_batch(self, db: AsyncSession):
        """Process queued events in batches."""
        batch = []
        
        while len(batch) < self.batch_size:
            try:
                event = self.event_queue.get_nowait()
                batch.append(event)
            except asyncio.QueueEmpty:
                break
        
        if batch:
            db.add_all(batch)
            await db.commit()
            logger.info(f"Processed {len(batch)} analytics events")
    
    async def get_dashboard_metrics(
        self,
        db: AsyncSession,
        organization_id: Optional[int] = None,
        date_range: str = "7d"
    ) -> Dict[str, Any]:
        """
        Get comprehensive dashboard metrics.
        """
        # Parse date range
        end_date = datetime.utcnow()
        if date_range == "24h":
            start_date = end_date - timedelta(hours=24)
        elif date_range == "7d":
            start_date = end_date - timedelta(days=7)
        elif date_range == "30d":
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=7)
        
        metrics = {
            'overview': await self._get_overview_metrics(db, organization_id, start_date, end_date),
            'activity_timeline': await self._get_activity_timeline(db, organization_id, start_date, end_date),
            'top_devices': await self._get_top_devices(db, organization_id, start_date, end_date),
            'search_analytics': await self._get_search_analytics(db, organization_id, start_date, end_date),
            'user_analytics': await self._get_user_analytics(db, organization_id, start_date, end_date),
            'real_time': await self._get_realtime_metrics(organization_id)
        }
        
        return metrics
    
    async def _get_overview_metrics(
        self,
        db: AsyncSession,
        organization_id: Optional[int],
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get overview metrics."""
        base_query = select(AnalyticsEvent).where(
            and_(
                AnalyticsEvent.created_at >= start_date,
                AnalyticsEvent.created_at <= end_date
            )
        )
        
        if organization_id:
            base_query = base_query.where(AnalyticsEvent.organization_id == organization_id)
        
        # Total events
        total_events = await db.execute(
            select(func.count(AnalyticsEvent.id)).select_from(base_query.subquery())
        )
        
        # Unique users
        unique_users = await db.execute(
            select(func.count(func.distinct(AnalyticsEvent.user_id))).select_from(base_query.subquery())
        )
        
        # Page views
        page_views = await db.execute(
            select(func.count(AnalyticsEvent.id)).select_from(
                base_query.where(AnalyticsEvent.event_type == 'page_view').subquery()
            )
        )
        
        # Device searches
        searches = await db.execute(
            select(func.count(AnalyticsEvent.id)).select_from(
                base_query.where(AnalyticsEvent.event_type == 'search').subquery()
            )
        )
        
        return {
            'total_events': total_events.scalar() or 0,
            'unique_users': unique_users.scalar() or 0,
            'page_views': page_views.scalar() or 0,
            'searches': searches.scalar() or 0,
            'avg_events_per_user': (total_events.scalar() or 0) / max(1, unique_users.scalar() or 1)
        }
    
    async def _get_activity_timeline(
        self,
        db: AsyncSession,
        organization_id: Optional[int],
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get activity timeline data."""
        # Determine appropriate time bucket
        date_diff = (end_date - start_date).days
        if date_diff <= 1:
            # Hourly buckets
            time_bucket = "hour"
            interval = "1 hour"
        elif date_diff <= 7:
            # Daily buckets
            time_bucket = "day"
            interval = "1 day"
        else:
            # Weekly buckets
            time_bucket = "week"
            interval = "1 week"
        
        query = f"""
            SELECT 
                date_trunc('{time_bucket}', created_at) as time_bucket,
                COUNT(*) as event_count,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT session_id) as sessions
            FROM analytics_events
            WHERE created_at >= :start_date 
            AND created_at <= :end_date
            {f"AND organization_id = :org_id" if organization_id else ""}
            GROUP BY time_bucket
            ORDER BY time_bucket
        """
        
        params = {"start_date": start_date, "end_date": end_date}
        if organization_id:
            params["org_id"] = organization_id
        
        result = await db.execute(text(query), params)
        
        timeline = []
        for row in result:
            timeline.append({
                'timestamp': row.time_bucket.isoformat(),
                'events': row.event_count,
                'unique_users': row.unique_users,
                'sessions': row.sessions
            })
        
        return timeline
    
    async def _get_top_devices(
        self,
        db: AsyncSession,
        organization_id: Optional[int],
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top viewed devices."""
        query = """
            SELECT 
                ae.resource_id::integer as device_id,
                COUNT(*) as view_count,
                COUNT(DISTINCT ae.user_id) as unique_viewers,
                vd.device_name,
                vd.manufacturer_name
            FROM analytics_events ae
            LEFT JOIN vendor_devices vd ON vd.id = ae.resource_id::integer
            WHERE ae.event_type = 'device_view'
            AND ae.resource_type = 'device'
            AND ae.created_at >= :start_date
            AND ae.created_at <= :end_date
            {org_filter}
            GROUP BY ae.resource_id, vd.device_name, vd.manufacturer_name
            ORDER BY view_count DESC
            LIMIT :limit
        """
        
        org_filter = "AND ae.organization_id = :org_id" if organization_id else ""
        query = query.format(org_filter=org_filter)
        
        params = {"start_date": start_date, "end_date": end_date, "limit": limit}
        if organization_id:
            params["org_id"] = organization_id
        
        result = await db.execute(text(query), params)
        
        devices = []
        for row in result:
            devices.append({
                'device_id': row.device_id,
                'device_name': row.device_name or f"Device {row.device_id}",
                'manufacturer': row.manufacturer_name,
                'view_count': row.view_count,
                'unique_viewers': row.unique_viewers
            })
        
        return devices
    
    async def _get_search_analytics(
        self,
        db: AsyncSession,
        organization_id: Optional[int],
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get search analytics."""
        base_query = select(SearchHistory).where(
            and_(
                SearchHistory.created_at >= start_date,
                SearchHistory.created_at <= end_date
            )
        )
        
        if organization_id:
            base_query = base_query.where(SearchHistory.organization_id == organization_id)
        
        # Total searches
        total_searches = await db.execute(
            select(func.count(SearchHistory.id)).select_from(base_query.subquery())
        )
        
        # Average results per search
        avg_results = await db.execute(
            select(func.avg(SearchHistory.results_count)).select_from(base_query.subquery())
        )
        
        # Top search queries
        top_queries_result = await db.execute(
            select(
                SearchHistory.search_query,
                func.count(SearchHistory.id).label('count')
            )
            .select_from(base_query.subquery())
            .group_by(SearchHistory.search_query)
            .order_by(func.count(SearchHistory.id).desc())
            .limit(10)
        )
        
        top_queries = [
            {'query': row.search_query, 'count': row.count}
            for row in top_queries_result
        ]
        
        # Search performance
        avg_duration = await db.execute(
            select(func.avg(SearchHistory.search_duration_ms)).select_from(base_query.subquery())
        )
        
        return {
            'total_searches': total_searches.scalar() or 0,
            'avg_results_per_search': float(avg_results.scalar() or 0),
            'avg_search_duration_ms': float(avg_duration.scalar() or 0),
            'top_queries': top_queries
        }
    
    async def _get_user_analytics(
        self,
        db: AsyncSession,
        organization_id: Optional[int],
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get user behavior analytics."""
        base_query = select(AnalyticsEvent).where(
            and_(
                AnalyticsEvent.created_at >= start_date,
                AnalyticsEvent.created_at <= end_date,
                AnalyticsEvent.user_id.isnot(None)
            )
        )
        
        if organization_id:
            base_query = base_query.where(AnalyticsEvent.organization_id == organization_id)
        
        # Active users
        active_users = await db.execute(
            select(func.count(func.distinct(AnalyticsEvent.user_id))).select_from(base_query.subquery())
        )
        
        # New vs returning users
        first_time_users_query = """
            SELECT COUNT(DISTINCT user_id) as count
            FROM (
                SELECT user_id, MIN(created_at) as first_seen
                FROM analytics_events
                WHERE user_id IS NOT NULL
                GROUP BY user_id
                HAVING MIN(created_at) >= :start_date AND MIN(created_at) <= :end_date
            ) as new_users
        """
        
        new_users_result = await db.execute(
            text(first_time_users_query),
            {"start_date": start_date, "end_date": end_date}
        )
        new_users = new_users_result.scalar() or 0
        
        # Device distribution
        device_dist_result = await db.execute(
            select(
                AnalyticsEvent.device_type,
                func.count(func.distinct(AnalyticsEvent.user_id)).label('count')
            )
            .select_from(base_query.subquery())
            .group_by(AnalyticsEvent.device_type)
        )
        
        device_distribution = {
            row.device_type or 'Unknown': row.count
            for row in device_dist_result
        }
        
        # Browser distribution
        browser_dist_result = await db.execute(
            select(
                AnalyticsEvent.browser,
                func.count(func.distinct(AnalyticsEvent.user_id)).label('count')
            )
            .select_from(base_query.subquery())
            .group_by(AnalyticsEvent.browser)
        )
        
        browser_distribution = {
            row.browser or 'Unknown': row.count
            for row in browser_dist_result
        }
        
        return {
            'active_users': active_users.scalar() or 0,
            'new_users': new_users,
            'returning_users': (active_users.scalar() or 0) - new_users,
            'device_distribution': device_distribution,
            'browser_distribution': browser_distribution
        }
    
    async def _get_realtime_metrics(self, organization_id: Optional[int]) -> Dict[str, Any]:
        """Get real-time metrics from Redis."""
        now = datetime.utcnow()
        hour_key = now.strftime("%Y%m%d%H")
        
        # Get current hour metrics
        total_events = await self.redis_manager.get(f"analytics:events:{hour_key}:total") or 0
        
        # Get event type breakdown
        event_types = ['page_view', 'search', 'device_view', 'document_download']
        event_breakdown = {}
        
        for event_type in event_types:
            count = await self.redis_manager.get(f"analytics:events:{hour_key}:{event_type}") or 0
            event_breakdown[event_type] = int(count)
        
        # Get organization-specific metrics if applicable
        org_events = 0
        if organization_id:
            org_events = await self.redis_manager.get(
                f"analytics:org:{organization_id}:{hour_key}"
            ) or 0
        
        return {
            'current_hour_events': int(total_events),
            'event_breakdown': event_breakdown,
            'organization_events': int(org_events),
            'timestamp': now.isoformat()
        }
    
    async def export_analytics(
        self,
        db: AsyncSession,
        organization_id: Optional[int],
        start_date: datetime,
        end_date: datetime,
        format: str = "csv"
    ) -> str:
        """
        Export analytics data in various formats.
        """
        # Get all analytics data
        query = select(AnalyticsEvent).where(
            and_(
                AnalyticsEvent.created_at >= start_date,
                AnalyticsEvent.created_at <= end_date
            )
        )
        
        if organization_id:
            query = query.where(AnalyticsEvent.organization_id == organization_id)
        
        result = await db.execute(query)
        events = result.scalars().all()
        
        if format == "csv":
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=[
                'timestamp', 'user_id', 'event_type', 'event_category',
                'resource_type', 'resource_id', 'device_type', 'browser',
                'country_code', 'metadata'
            ])
            
            writer.writeheader()
            for event in events:
                writer.writerow({
                    'timestamp': event.created_at.isoformat(),
                    'user_id': event.user_id,
                    'event_type': event.event_type,
                    'event_category': event.event_category,
                    'resource_type': event.resource_type,
                    'resource_id': event.resource_id,
                    'device_type': event.device_type,
                    'browser': event.browser,
                    'country_code': event.country_code,
                    'metadata': event.metadata
                })
            
            return output.getvalue()
        
        elif format == "json":
            data = []
            for event in events:
                data.append({
                    'timestamp': event.created_at.isoformat(),
                    'user_id': event.user_id,
                    'event_type': event.event_type,
                    'event_category': event.event_category,
                    'resource_type': event.resource_type,
                    'resource_id': event.resource_id,
                    'metadata': json.loads(event.metadata) if event.metadata else None
                })
            
            return json.dumps(data, indent=2)
        
        else:
            raise ValueError(f"Unsupported export format: {format}")


# Background task for processing analytics events
async def process_analytics_queue(analytics_service: AnalyticsService, db_session_factory):
    """
    Background task to process analytics event queue.
    """
    while True:
        try:
            async with db_session_factory() as db:
                await analytics_service.process_event_batch(db)
            
            await asyncio.sleep(analytics_service.flush_interval)
            
        except Exception as e:
            logger.error(f"Error processing analytics queue: {e}")
            await asyncio.sleep(60)  # Wait longer on error
