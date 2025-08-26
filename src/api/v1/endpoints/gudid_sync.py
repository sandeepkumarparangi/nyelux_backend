"""
GUDID sync endpoints.

Provides endpoints for triggering and monitoring FDA GUDID data synchronization.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from src.core.config import settings
from src.db.models.background_job import BackgroundJob, JobType, JobStatus
from src.db.models.user import User
from src.db.session import get_db
from src.schemas.base import SuccessResponse
from src.schemas.background_job import BackgroundJobResponse, BackgroundJobList
from src.services.auth_service import get_current_active_user
from src.services.gudid_sync_service import GUDIDSyncService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/trigger", response_model=BackgroundJobResponse)
async def trigger_gudid_sync(
    *,
    db: AsyncSession = Depends(get_db),
    force: bool = Query(False, description="Force sync even if data hasn't changed"),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Trigger FDA GUDID data synchronization.
    
    This endpoint initiates a background job to download and process the latest
    medical device data from the FDA GUDID database (4.8M+ records).
    
    The sync runs asynchronously and typically takes 20-30 minutes to complete.
    
    Args:
        force: Force sync even if FDA data hasn't changed
        
    Returns:
        BackgroundJobResponse with job details and tracking ID
        
    Raises:
        HTTPException 403: If user doesn't have admin role
        HTTPException 409: If sync is already running
        
    Security:
        - Requires admin role
        - Only one sync can run at a time
    """
    # Check permissions - only admins can trigger sync
    if current_user.role not in ["super_admin", "org_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger GUDID sync"
        )
    
    # Check if sync is already running
    running_job = await db.execute(
        select(BackgroundJob).where(
            BackgroundJob.job_type == JobType.GUDID_SYNC,
            BackgroundJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
        )
    )
    if running_job.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GUDID sync is already running or scheduled"
        )
    
    # Create background job
    job = BackgroundJob.create_job(
        job_type=JobType.GUDID_SYNC,
        payload={
            "force": force,
            "triggered_by": current_user.id,
            "triggered_by_email": current_user.email
        },
        priority=3  # High priority
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    logger.info(f"GUDID sync triggered by {current_user.email} (job_id: {job.id})")
    
    # TODO: Queue job for processing
    # In production, this would be picked up by a background worker
    # For now, we'll run it directly (not recommended for production)
    if settings.ENVIRONMENT == "development":
        # Run sync in background (don't await)
        import asyncio
        gudid_service = GUDIDSyncService()
        asyncio.create_task(gudid_service.sync_gudid_data(db, force=force))
    
    return BackgroundJobResponse.from_orm(job)


@router.get("/status", response_model=BackgroundJobList)
async def get_sync_status(
    *,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get GUDID sync job history and status.
    
    Returns a list of recent GUDID sync jobs with their status, timing,
    and results. Useful for monitoring sync health and troubleshooting.
    
    Args:
        limit: Maximum number of jobs to return
        skip: Number of jobs to skip (for pagination)
        
    Returns:
        List of sync jobs with status and metrics
        
    Security:
        - Requires authentication
        - Non-admins only see basic status info
    """
    # Build query
    query = select(BackgroundJob).where(
        BackgroundJob.job_type == JobType.GUDID_SYNC
    ).order_by(
        BackgroundJob.created_at.desc()
    ).limit(limit).offset(skip)
    
    # Execute query
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    # Count total
    count_query = select(BackgroundJob).where(
        BackgroundJob.job_type == JobType.GUDID_SYNC
    )
    total = await db.execute(count_query)
    total_count = len(total.scalars().all())
    
    # Filter sensitive data for non-admins
    if current_user.role not in ["super_admin", "org_admin"]:
        for job in jobs:
            if job.payload:
                job.payload = {"status": "hidden"}
            if job.result:
                job.result = {
                    "success": job.result.get("success", False),
                    "total_processed": job.result.get("total_processed", 0)
                }
    
    return BackgroundJobList(
        items=[BackgroundJobResponse.from_orm(job) for job in jobs],
        total=total_count,
        skip=skip,
        limit=limit
    )


@router.get("/stats", response_model=dict)
async def get_sync_statistics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get GUDID database statistics.
    
    Returns statistics about the synchronized GUDID data including:
    - Total device count
    - Devices by FDA class
    - Last sync timestamp
    - Data freshness
    
    Returns:
        Dictionary with database statistics
        
    Security:
        - Requires authentication
    """
    from src.db.models.gudid_device import GUDIDDevice
    
    # Get total device count
    total_query = select(func.count(GUDIDDevice.id))
    total_result = await db.execute(total_query)
    total_count = total_result.scalar()
    
    # Get devices by class
    class_query = select(
        GUDIDDevice.device_class,
        func.count(GUDIDDevice.id).label("count")
    ).group_by(GUDIDDevice.device_class)
    
    class_result = await db.execute(class_query)
    by_class = {row.device_class or "Unknown": row.count for row in class_result}
    
    # Get last sync info
    last_sync_query = select(BackgroundJob).where(
        BackgroundJob.job_type == JobType.GUDID_SYNC,
        BackgroundJob.status == JobStatus.COMPLETED
    ).order_by(BackgroundJob.completed_at.desc()).limit(1)
    
    last_sync_result = await db.execute(last_sync_query)
    last_sync = last_sync_result.scalar_one_or_none()
    
    # Build response
    stats = {
        "total_devices": total_count,
        "devices_by_class": by_class,
        "last_sync": {
            "timestamp": last_sync.completed_at.isoformat() if last_sync else None,
            "records_processed": last_sync.result.get("total_processed", 0) if last_sync and last_sync.result else 0,
            "duration_seconds": last_sync.result.get("duration_seconds", 0) if last_sync and last_sync.result else 0
        },
        "data_freshness": {
            "hours_since_sync": (
                (datetime.utcnow() - last_sync.completed_at).total_seconds() / 3600
                if last_sync and last_sync.completed_at else None
            ),
            "is_current": (
                last_sync.completed_at > datetime.utcnow() - timedelta(hours=25)
                if last_sync and last_sync.completed_at else False
            )
        }
    }
    
    return stats


@router.post("/cancel/{job_id}", response_model=SuccessResponse)
async def cancel_sync_job(
    *,
    db: AsyncSession = Depends(get_db),
    job_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Cancel a pending or running GUDID sync job.
    
    Args:
        job_id: ID of the sync job to cancel
        
    Returns:
        Success response
        
    Raises:
        HTTPException 403: If user doesn't have admin role
        HTTPException 404: If job not found
        HTTPException 400: If job already completed
        
    Security:
        - Requires admin role
    """
    # Check permissions
    if current_user.role not in ["super_admin", "org_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can cancel sync jobs"
        )
    
    # Get job
    job = await db.get(BackgroundJob, job_id)
    if not job or job.job_type != JobType.GUDID_SYNC:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync job not found"
        )
    
    # Check if cancellable
    if job.is_finished:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in {job.status} status"
        )
    
    # Cancel job
    job.cancel()
    await db.commit()
    
    logger.info(f"GUDID sync job {job_id} cancelled by {current_user.email}")
    
    return SuccessResponse(
        message=f"Sync job {job_id} cancelled successfully"
    )


# Import after models to avoid circular imports
from sqlalchemy import func
from datetime import datetime, timedelta
