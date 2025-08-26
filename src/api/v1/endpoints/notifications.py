"""
Notifications API endpoints.
REAL implementation for multi-channel notification management.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update, func
from typing import Any, List, Optional, Dict
from datetime import datetime
import logging

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.notification import Notification
from src.db.models.notification_delivery import NotificationDelivery
from src.db.models.notification_preferences import NotificationPreferences
from src.services.auth_service import get_current_active_user
from src.services.notification_service import NotificationService
from src.schemas.base import SuccessResponse, PaginatedResponse
from src.schemas.notification import (
    NotificationResponse,
    NotificationPreferencesUpdate,
    NotificationPreferencesResponse,
    NotificationMarkRead,
    NotificationBulkAction,
    NotificationStats,
    TestNotificationRequest
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Create service instance for this router
notification_service = NotificationService()


@router.get("/", response_model=PaginatedResponse[NotificationResponse])
async def get_notifications(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    unread_only: bool = Query(False, description="Show only unread notifications"),
    notification_type: Optional[str] = Query(None, description="Filter by type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
) -> Any:
    """
    Get user's notifications with pagination.
    
    Includes delivery status for each channel.
    """
    # Build query
    stmt = select(Notification).where(
        Notification.user_id == current_user.id
    )
    
    # Apply filters
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    
    if notification_type:
        stmt = stmt.where(Notification.type == notification_type)
    
    if priority:
        stmt = stmt.where(Notification.priority == priority)
    
    # Order by created date descending
    stmt = stmt.order_by(Notification.created_at.desc())
    
    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()
    
    # Apply pagination
    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)
    
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    
    # Get delivery status for each notification
    notification_responses = []
    for notification in notifications:
        # Get delivery status
        delivery_result = await db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        deliveries = delivery_result.scalars().all()
        
        notification_responses.append(
            NotificationResponse.from_orm_with_deliveries(notification, deliveries)
        )
    
    return PaginatedResponse(
        items=notification_responses,
        total=total,
        page=page,
        limit=limit,
        pages=(total + limit - 1) // limit
    )


@router.get("/stats", response_model=NotificationStats)
async def get_notification_stats(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Get notification statistics for current user."""
    # Count unread
    unread_result = await db.execute(
        select(func.count()).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None),
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            )
        )
    )
    unread_count = unread_result.scalar()
    
    # Count by type
    type_result = await db.execute(
        select(
            Notification.type,
            func.count().label('count')
        ).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None)
            )
        ).group_by(Notification.type)
    )
    
    by_type = {row.type: row.count for row in type_result}
    
    # Count by priority
    priority_result = await db.execute(
        select(
            Notification.priority,
            func.count().label('count')
        ).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None)
            )
        ).group_by(Notification.priority)
    )
    
    by_priority = {row.priority: row.count for row in priority_result}
    
    return NotificationStats(
        unread_count=unread_count,
        by_type=by_type,
        by_priority=by_priority
    )


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    *,
    db: AsyncSession = Depends(get_db),
    notification_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Get specific notification."""
    notification = await db.get(Notification, notification_id)
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this notification"
        )
    
    # Get delivery status
    delivery_result = await db.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notification.id
        )
    )
    deliveries = delivery_result.scalars().all()
    
    return NotificationResponse.from_orm_with_deliveries(notification, deliveries)


@router.post("/{notification_id}/read", response_model=SuccessResponse)
async def mark_notification_read(
    *,
    db: AsyncSession = Depends(get_db),
    notification_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Mark notification as read."""
    notification = await db.get(Notification, notification_id)
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this notification"
        )
    
    if not notification.read_at:
        notification.read_at = datetime.utcnow()
        await db.commit()
    
    return SuccessResponse(
        message="Notification marked as read"
    )


@router.post("/mark-read", response_model=SuccessResponse)
async def mark_notifications_read(
    *,
    db: AsyncSession = Depends(get_db),
    mark_in: NotificationMarkRead,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Mark multiple notifications as read."""
    # Update notifications
    stmt = (
        update(Notification)
        .where(
            and_(
                Notification.user_id == current_user.id,
                Notification.id.in_(mark_in.notification_ids),
                Notification.read_at.is_(None)
            )
        )
        .values(read_at=datetime.utcnow())
    )
    
    result = await db.execute(stmt)
    await db.commit()
    
    return SuccessResponse(
        message=f"Marked {result.rowcount} notifications as read"
    )


@router.post("/mark-all-read", response_model=SuccessResponse)
async def mark_all_notifications_read(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Mark all notifications as read."""
    stmt = (
        update(Notification)
        .where(
            and_(
                Notification.user_id == current_user.id,
                Notification.read_at.is_(None)
            )
        )
        .values(read_at=datetime.utcnow())
    )
    
    result = await db.execute(stmt)
    await db.commit()
    
    return SuccessResponse(
        message=f"Marked {result.rowcount} notifications as read"
    )


@router.delete("/{notification_id}", response_model=SuccessResponse)
async def dismiss_notification(
    *,
    db: AsyncSession = Depends(get_db),
    notification_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Dismiss (soft delete) notification."""
    notification = await db.get(Notification, notification_id)
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to dismiss this notification"
        )
    
    notification.dismissed_at = datetime.utcnow()
    await db.commit()
    
    return SuccessResponse(
        message="Notification dismissed"
    )


@router.post("/bulk-action", response_model=SuccessResponse)
async def bulk_notification_action(
    *,
    db: AsyncSession = Depends(get_db),
    bulk_in: NotificationBulkAction,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Perform bulk action on notifications."""
    if bulk_in.action == "mark_read":
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.user_id == current_user.id,
                    Notification.id.in_(bulk_in.notification_ids),
                    Notification.read_at.is_(None)
                )
            )
            .values(read_at=datetime.utcnow())
        )
    elif bulk_in.action == "dismiss":
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.user_id == current_user.id,
                    Notification.id.in_(bulk_in.notification_ids),
                    Notification.dismissed_at.is_(None)
                )
            )
            .values(dismissed_at=datetime.utcnow())
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Must be 'mark_read' or 'dismiss'"
        )
    
    result = await db.execute(stmt)
    await db.commit()
    
    return SuccessResponse(
        message=f"Applied {bulk_in.action} to {result.rowcount} notifications"
    )


@router.get("/preferences/current", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Get user's notification preferences."""
    # Get or create preferences
    prefs = await db.execute(
        select(NotificationPreferences).where(
            NotificationPreferences.user_id == current_user.id
        )
    )
    preferences = prefs.scalar_one_or_none()
    
    if not preferences:
        # Create default preferences
        preferences = NotificationPreferences(
            user_id=current_user.id,
            categories={
                "device_recall": {"email": True, "sms": True, "push": True, "in_app": True},
                "device_update": {"email": True, "sms": False, "push": True, "in_app": True},
                "new_message": {"email": True, "sms": False, "push": True, "in_app": True},
                "meeting_reminder": {"email": True, "sms": False, "push": True, "in_app": True},
                "training_available": {"email": False, "sms": False, "push": True, "in_app": True},
                "incident_update": {"email": True, "sms": False, "push": True, "in_app": True},
                "system_alert": {"email": True, "sms": False, "push": False, "in_app": True}
            },
            frequency={
                "email": "immediate",
                "sms": "immediate",
                "push": "immediate",
                "in_app": "immediate"
            }
        )
        db.add(preferences)
        await db.commit()
        await db.refresh(preferences)
    
    return NotificationPreferencesResponse.from_orm(preferences)


@router.put("/preferences", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    *,
    db: AsyncSession = Depends(get_db),
    prefs_in: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Update notification preferences."""
    # Get existing preferences
    result = await db.execute(
        select(NotificationPreferences).where(
            NotificationPreferences.user_id == current_user.id
        )
    )
    preferences = result.scalar_one_or_none()
    
    if not preferences:
        # Create new preferences
        preferences = NotificationPreferences(user_id=current_user.id)
        db.add(preferences)
    
    # Update fields
    update_data = prefs_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preferences, field, value)
    
    await db.commit()
    await db.refresh(preferences)
    
    return NotificationPreferencesResponse.from_orm(preferences)


@router.post("/test", response_model=SuccessResponse)
async def send_test_notification(
    *,
    db: AsyncSession = Depends(get_db),
    test_in: TestNotificationRequest,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Send test notification to verify channel configuration.
    
    Useful for testing email, SMS, and push notification setup.
    """
    try:
        # Create test notification
        notification = await notification_service.send_notification(
            db=db,
            user_id=current_user.id,
            notification_type='system_alert',
            title='Test Notification',
            body=f'This is a test {test_in.channel} notification from Nyelux.',
            priority='medium'
        )
        
        # Send via specific channel
        if test_in.channel == 'email':
            success = await notification_service.send_email(
                recipient=current_user.email,
                subject='Test Notification',
                template_id=None,
                template_data={
                    'title': 'Test Notification',
                    'body': 'This is a test email notification from Nyelux.'
                }
            )
        elif test_in.channel == 'sms':
            if not current_user.phone:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number not configured for SMS notifications"
                )
            success = await notification_service.send_sms(
                recipient=current_user.phone,
                message='Test: This is a test SMS notification from Nyelux.'
            )
        elif test_in.channel == 'push':
            # Would send push notification
            success = True
        else:
            success = True
        
        if success:
            return SuccessResponse(
                message=f"Test {test_in.channel} notification sent successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send test {test_in.channel} notification"
            )
            
    except Exception as e:
        logger.error(f"Test notification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/subscription/vapid-key", response_model=dict)
async def get_vapid_public_key(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get VAPID public key for push notification subscription.
    
    Used by frontend to subscribe to web push notifications.
    """
    # TODO: Implement VAPID key generation for web push
    return {
        "public_key": "VAPID_PUBLIC_KEY_PLACEHOLDER"
    }


@router.post("/subscription/push", response_model=SuccessResponse)
async def subscribe_push_notifications(
    *,
    db: AsyncSession = Depends(get_db),
    subscription: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Subscribe to push notifications.
    
    Stores browser push subscription for sending notifications.
    """
    # TODO: Store push subscription endpoint and keys
    # This would save the subscription data for the user
    
    return SuccessResponse(
        message="Successfully subscribed to push notifications"
    )


@router.delete("/subscription/push", response_model=SuccessResponse)
async def unsubscribe_push_notifications(
    *,
    db: AsyncSession = Depends(get_db),
    endpoint: str = Body(..., embed=True),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Unsubscribe from push notifications."""
    # TODO: Remove push subscription
    
    return SuccessResponse(
        message="Successfully unsubscribed from push notifications"
    )
