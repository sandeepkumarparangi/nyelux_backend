"""
Background jobs for vendor portal maintenance and analytics.
Run these as scheduled tasks (cron jobs or Celery tasks).
"""

import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import select, func, and_, update
from sqlalchemy.orm import sessionmaker
import logging

from src.core.config import settings
from src.db.models.vendor_profile import VendorProfile, VendorPageAnalytics
from src.db.models.vendor_lead import VendorLead
from src.db.models.vendor_service import VendorServiceRequest
from src.db.models.vendor_profile import VendorAccessRequest
from src.db.models.analytics_event import AnalyticsEvent
from src.db.models.vendor_device import VendorDevice

logger = logging.getLogger(__name__)

# Create async engine for background jobs
engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def aggregate_vendor_analytics():
    """
    Aggregate vendor analytics daily.
    Run this job once per day at midnight.
    """
    async with AsyncSessionLocal() as db:
        try:
            # Get yesterday's date range
            end_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = end_date - timedelta(days=1)
            
            logger.info(f"Aggregating vendor analytics for {start_date.date()}")
            
            # Get all active vendor profiles
            result = await db.execute(
                select(VendorProfile).where(
                    VendorProfile.is_active == True
                )
            )
            profiles = result.scalars().all()
            
            for profile in profiles:
                # Check if analytics already exist for this date
                existing = await db.execute(
                    select(VendorPageAnalytics).where(
                        and_(
                            VendorPageAnalytics.vendor_profile_id == profile.id,
                            VendorPageAnalytics.date == start_date
                        )
                    )
                )
                
                if existing.scalar_one_or_none():
                    logger.info(f"Analytics already exist for vendor {profile.id} on {start_date.date()}")
                    continue
                
                # Aggregate page views
                page_views_result = await db.execute(
                    select(
                        func.count(AnalyticsEvent.id).label('page_views'),
                        func.count(func.distinct(AnalyticsEvent.session_id)).label('unique_visitors'),
                        func.avg(AnalyticsEvent.value).label('avg_time')  # Assuming value stores time on page
                    ).where(
                        and_(
                            AnalyticsEvent.resource_type == 'vendor_profile',
                            AnalyticsEvent.resource_id == str(profile.id),
                            AnalyticsEvent.created_at >= start_date,
                            AnalyticsEvent.created_at < end_date
                        )
                    )
                )
                page_stats = page_views_result.one()
                
                # Count device clicks
                device_clicks_result = await db.execute(
                    select(func.count(AnalyticsEvent.id)).where(
                        and_(
                            AnalyticsEvent.event_type == 'device_view',
                            AnalyticsEvent.resource_type == 'vendor_device',
                            AnalyticsEvent.organization_id == profile.organization_id,
                            AnalyticsEvent.created_at >= start_date,
                            AnalyticsEvent.created_at < end_date
                        )
                    )
                )
                device_clicks = device_clicks_result.scalar() or 0
                
                # Count leads captured
                leads_result = await db.execute(
                    select(func.count(VendorLead.id)).where(
                        and_(
                            VendorLead.vendor_profile_id == profile.id,
                            VendorLead.created_at >= start_date,
                            VendorLead.created_at < end_date
                        )
                    )
                )
                leads_captured = leads_result.scalar() or 0
                
                # Count access requests
                access_requests_result = await db.execute(
                    select(func.count(VendorAccessRequest.id)).where(
                        and_(
                            VendorAccessRequest.vendor_profile_id == profile.id,
                            VendorAccessRequest.created_at >= start_date,
                            VendorAccessRequest.created_at < end_date
                        )
                    )
                )
                access_requests = access_requests_result.scalar() or 0
                
                # Create analytics record
                analytics = VendorPageAnalytics(
                    vendor_profile_id=profile.id,
                    date=start_date,
                    page_views=page_stats.page_views or 0,
                    unique_visitors=page_stats.unique_visitors or 0,
                    avg_time_on_page=int(page_stats.avg_time or 0),
                    bounce_rate=0.0,  # Calculate based on your bounce logic
                    device_clicks=device_clicks,
                    document_downloads=0,  # Track these in AnalyticsEvent
                    video_plays=0,  # Track these in AnalyticsEvent
                    chat_initiations=0,  # Track these in AnalyticsEvent
                    leads_captured=leads_captured,
                    access_requests=access_requests,
                    demo_requests=0,  # Count from service requests
                    contact_form_submissions=0  # Track separately
                )
                
                db.add(analytics)
                
                # Update vendor profile totals
                profile.total_devices = await db.execute(
                    select(func.count(VendorDevice.id)).where(
                        and_(
                            VendorDevice.organization_id == profile.organization_id,
                            VendorDevice.is_active == True
                        )
                    )
                ).scalar() or 0
                
                logger.info(f"Aggregated analytics for vendor {profile.id}: "
                           f"{page_stats.page_views} views, {leads_captured} leads")
            
            await db.commit()
            logger.info("Vendor analytics aggregation completed")
            
        except Exception as e:
            logger.error(f"Error aggregating vendor analytics: {e}")
            await db.rollback()


async def expire_access_requests():
    """
    Expire old pending access requests.
    Run this job daily.
    """
    async with AsyncSessionLocal() as db:
        try:
            expired_time = datetime.utcnow()
            
            # Find and expire requests
            result = await db.execute(
                update(VendorAccessRequest)
                .where(
                    and_(
                        VendorAccessRequest.status == 'pending',
                        VendorAccessRequest.expires_at <= expired_time
                    )
                )
                .values(status='expired')
                .returning(VendorAccessRequest.id)
            )
            
            expired_ids = result.scalars().all()
            
            if expired_ids:
                await db.commit()
                logger.info(f"Expired {len(expired_ids)} access requests")
            
        except Exception as e:
            logger.error(f"Error expiring access requests: {e}")
            await db.rollback()


async def calculate_lead_scores():
    """
    Recalculate lead scores based on activity.
    Run this job every 6 hours.
    """
    async with AsyncSessionLocal() as db:
        try:
            # Get leads that need scoring update (active in last 7 days)
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            
            result = await db.execute(
                select(VendorLead).where(
                    and_(
                        VendorLead.status.in_(['new', 'contacted', 'nurturing']),
                        VendorLead.updated_at >= cutoff_date
                    )
                )
            )
            leads = result.scalars().all()
            
            updated_count = 0
            for lead in leads:
                old_score = lead.lead_score
                new_score = lead.calculate_lead_score()
                
                if old_score != new_score:
                    lead.lead_score = new_score
                    lead.scoring_factors = {
                        "profile_completeness": 20 if lead.organization_name else 10,
                        "engagement": len(lead.interested_devices or []) * 5,
                        "recency": 10 if lead.updated_at > datetime.utcnow() - timedelta(days=1) else 5,
                        "source_quality": 15 if lead.source_type in ['demo_request', 'pricing_request'] else 5
                    }
                    updated_count += 1
            
            if updated_count > 0:
                await db.commit()
                logger.info(f"Updated scores for {updated_count} leads")
            
        except Exception as e:
            logger.error(f"Error calculating lead scores: {e}")
            await db.rollback()


async def check_sla_compliance():
    """
    Check service request SLA compliance and send alerts.
    Run this job every hour.
    """
    async with AsyncSessionLocal() as db:
        try:
            current_time = datetime.utcnow()
            
            # Find requests approaching or past SLA
            result = await db.execute(
                select(VendorServiceRequest).where(
                    and_(
                        VendorServiceRequest.status.in_(['pending', 'assigned']),
                        VendorServiceRequest.sla_deadline.isnot(None),
                        VendorServiceRequest.sla_deadline <= current_time + timedelta(hours=1)
                    )
                )
            )
            urgent_requests = result.scalars().all()
            
            for request in urgent_requests:
                if request.sla_deadline <= current_time:
                    # SLA breached
                    logger.warning(f"SLA breached for service request {request.request_number}")
                    request.sla_met = False
                    
                    # TODO: Send notification to vendor and escalate
                    
                elif request.sla_deadline <= current_time + timedelta(hours=1):
                    # SLA warning (1 hour remaining)
                    logger.warning(f"SLA warning for service request {request.request_number}")
                    
                    # TODO: Send warning notification
            
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error checking SLA compliance: {e}")
            await db.rollback()


async def cleanup_old_analytics():
    """
    Clean up old analytics data (keep last 90 days).
    Run this job weekly.
    """
    async with AsyncSessionLocal() as db:
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=90)
            
            # Delete old page analytics
            result = await db.execute(
                select(VendorPageAnalytics).where(
                    VendorPageAnalytics.date < cutoff_date
                )
            )
            old_analytics = result.scalars().all()
            
            for analytics in old_analytics:
                await db.delete(analytics)
            
            if old_analytics:
                await db.commit()
                logger.info(f"Cleaned up {len(old_analytics)} old analytics records")
            
        except Exception as e:
            logger.error(f"Error cleaning up analytics: {e}")
            await db.rollback()


async def send_lead_notifications():
    """
    Send email notifications for new leads.
    Run this job every 15 minutes.
    """
    async with AsyncSessionLocal() as db:
        try:
            # Find new leads without notification sent
            result = await db.execute(
                select(VendorLead).join(
                    VendorProfile
                ).where(
                    and_(
                        VendorLead.status == 'new',
                        VendorLead.created_at >= datetime.utcnow() - timedelta(minutes=15),
                        # Add a field to track notification sent
                    )
                )
            )
            new_leads = result.scalars().all()
            
            for lead in new_leads:
                # TODO: Implement actual email sending
                logger.info(f"Would send notification for lead {lead.id} to vendor")
                
                # Mark as notified (you'd need to add this field)
                # lead.notification_sent = True
            
            if new_leads:
                await db.commit()
                logger.info(f"Processed {len(new_leads)} lead notifications")
            
        except Exception as e:
            logger.error(f"Error sending lead notifications: {e}")
            await db.rollback()


# Main job runner
async def run_all_jobs():
    """Run all background jobs."""
    await aggregate_vendor_analytics()
    await expire_access_requests()
    await calculate_lead_scores()
    await check_sla_compliance()
    await cleanup_old_analytics()
    await send_lead_notifications()


if __name__ == "__main__":
    # For testing individual jobs
    asyncio.run(run_all_jobs())
