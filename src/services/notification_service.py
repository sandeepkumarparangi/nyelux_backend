"""
Notification service for multi-channel message delivery.
Supports email, SMS, push notifications, and in-app messages.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.db.models.notification import Notification
from src.db.models.notification_delivery import NotificationDelivery
from src.db.models.notification_preferences import NotificationPreferences
from src.db.models.user import User
from src.core.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Handles all notification delivery across multiple channels.
    Respects user preferences and handles delivery tracking.
    
    REAL IMPLEMENTATION: Only enables services that are properly configured.
    """
    
    def __init__(self):
        # Only initialize services that are actually configured
        self.email_service = None
        
        # Use the email wrapper - it will only initialize when needed
        from src.services.email_wrapper import email_wrapper
        self.email_service = email_wrapper
        
        # SMS and push services would be initialized here when ready
        # self.sms_service = None
        # self.push_service = None
    
    async def send_notification(
        self,
        db: AsyncSession,
        user_id: int,
        notification_type: str,
        title: str,
        body: str,
        priority: str = 'medium',
        data: Dict[str, Any] = None,
        action_url: str = None,
        expires_at: datetime = None
    ) -> Notification:
        """
        Send a notification to a user across their preferred channels.
        
        Args:
            db: Database session
            user_id: Target user ID
            notification_type: Type of notification
            title: Notification title
            body: Notification body
            priority: Priority level (low, medium, high, urgent)
            data: Additional data payload
            action_url: URL for action button
            expires_at: When notification expires
            
        Returns:
            Created notification object
        """
        try:
            # Get user and preferences
            user_result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                logger.error(f"User {user_id} not found for notification")
                raise ValueError(f"User {user_id} not found")
            
            # Get user notification preferences
            prefs_result = await db.execute(
                select(NotificationPreferences).where(
                    NotificationPreferences.user_id == user_id
                )
            )
            preferences = prefs_result.scalar_one_or_none()
            
            # Create notification record
            notification = Notification(
                user_id=user_id,
                type=notification_type,
                priority=priority,
                title=title,
                body=body,
                action_url=action_url,
                data=data or {},
                expires_at=expires_at
            )
            db.add(notification)
            await db.flush()  # Get notification ID
            
            # Determine channels to use
            channels = self._determine_channels(preferences, notification_type, priority)
            
            # Send through each channel
            for channel in channels:
                await self._send_channel_notification(
                    db, notification, user, channel, preferences
                )
            
            await db.commit()
            logger.info(f"Notification {notification.id} sent to user {user_id}")
            
            return notification
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to send notification: {str(e)}")
            raise
    
    async def send_bulk_notifications(
        self,
        db: AsyncSession,
        user_ids: List[int],
        notification_type: str,
        title: str,
        body: str,
        priority: str = 'medium',
        data: Dict[str, Any] = None
    ) -> List[Notification]:
        """
        Send notifications to multiple users.
        
        Args:
            db: Database session
            user_ids: List of target user IDs
            notification_type: Type of notification
            title: Notification title
            body: Notification body
            priority: Priority level
            data: Additional data payload
            
        Returns:
            List of created notifications
        """
        notifications = []
        
        for user_id in user_ids:
            try:
                notification = await self.send_notification(
                    db=db,
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    priority=priority,
                    data=data
                )
                notifications.append(notification)
            except Exception as e:
                logger.error(f"Failed to send notification to user {user_id}: {str(e)}")
                continue
        
        return notifications
    
    async def send_admin_notification(
        self,
        db: AsyncSession,
        organization_id: int,
        title: str,
        body: str,
        notification_type: str = 'system_alert',
        priority: str = 'high'
    ) -> List[Notification]:
        """
        Send notification to all admins in an organization.
        
        Args:
            db: Database session
            organization_id: Organization ID
            title: Notification title
            body: Notification body
            notification_type: Type of notification
            priority: Priority level
            
        Returns:
            List of created notifications
        """
        # Get all admin users in the organization
        admin_result = await db.execute(
            select(User).where(
                and_(
                    User.organization_id == organization_id,
                    User.role.in_(['org_admin', 'clinical_admin']),
                    User.deleted_at.is_(None)
                )
            )
        )
        admin_users = admin_result.scalars().all()
        
        if not admin_users:
            logger.warning(f"No admin users found for organization {organization_id}")
            return []
        
        # Send to all admins
        admin_ids = [admin.id for admin in admin_users]
        
        return await self.send_bulk_notifications(
            db=db,
            user_ids=admin_ids,
            notification_type=notification_type,
            title=title,
            body=body,
            priority=priority,
            data={'organization_id': organization_id}
        )
    
    async def mark_as_read(
        self,
        db: AsyncSession,
        notification_id: int,
        user_id: int
    ) -> bool:
        """
        Mark a notification as read.
        
        Args:
            db: Database session
            notification_id: Notification ID
            user_id: User ID (for verification)
            
        Returns:
            Success status
        """
        result = await db.execute(
            select(Notification).where(
                and_(
                    Notification.id == notification_id,
                    Notification.user_id == user_id
                )
            )
        )
        notification = result.scalar_one_or_none()
        
        if not notification:
            return False
        
        notification.read_at = datetime.utcnow()
        await db.commit()
        
        return True
    
    async def get_unread_count(
        self,
        db: AsyncSession,
        user_id: int
    ) -> int:
        """
        Get count of unread notifications for a user.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            Count of unread notifications
        """
        from sqlalchemy import func
        
        result = await db.execute(
            select(func.count(Notification.id)).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                    Notification.dismissed_at.is_(None)
                )
            )
        )
        
        return result.scalar() or 0
    
    def _determine_channels(
        self,
        preferences: Optional[NotificationPreferences],
        notification_type: str,
        priority: str
    ) -> List[str]:
        """
        Determine which channels to use based on preferences and priority.
        Only includes channels that are actually available.
        
        Args:
            preferences: User notification preferences
            notification_type: Type of notification
            priority: Priority level
            
        Returns:
            List of channels to use
        """
        # Always use in-app notifications
        channels = ['in_app']
        
        # For urgent/critical, use all available channels
        if priority in ['urgent', 'critical']:
            if self.email_service and self.email_service.is_available():  # Only add if service is available
                channels.append('email')
            # Only add SMS/push when those services are implemented
            # if self.sms_service:
            #     channels.append('sms')
            # if self.push_service:
            #     channels.append('push')
            return channels
        
        # If no preferences, use defaults (only available services)
        if not preferences:
            if self.email_service and self.email_service.is_available():
                channels.append('email')
            return channels
        
        # Check user preferences (only for available services)
        if self.email_service and self.email_service.is_available() and preferences.should_send_notification(notification_type, 'email'):
            channels.append('email')
        
        # Only add these when services are implemented
        # if self.sms_service and preferences.should_send_notification(notification_type, 'sms'):
        #     channels.append('sms')
        #     
        # if self.push_service and preferences.should_send_notification(notification_type, 'push'):
        #     channels.append('push')
        
        return list(set(channels))  # Remove duplicates
    
    async def _send_channel_notification(
        self,
        db: AsyncSession,
        notification: Notification,
        user: User,
        channel: str,
        preferences: Optional[NotificationPreferences]
    ):
        """
        Send notification through a specific channel.
        
        Args:
            db: Database session
            notification: Notification object
            user: User object
            channel: Channel to use
            preferences: User preferences
        """
        # Create delivery record
        delivery = NotificationDelivery(
            notification_id=notification.id,
            channel=channel,
            recipient_address=self._get_recipient_address(user, channel)
        )
        db.add(delivery)
        await db.flush()
        
        try:
            if channel == 'email':
                await self._send_email_notification(notification, user, delivery)
            elif channel == 'sms':
                await self._send_sms_notification(notification, user, delivery)
            elif channel == 'push':
                await self._send_push_notification(notification, user, delivery)
            elif channel == 'in_app':
                # In-app notifications are already created in the database
                delivery.mark_delivered()
            
            await db.commit()
            
        except Exception as e:
            logger.error(f"Failed to send {channel} notification: {str(e)}")
            delivery.mark_failed(str(e))
            await db.commit()
    
    async def _send_email_notification(
        self,
        notification: Notification,
        user: User,
        delivery: NotificationDelivery
    ):
        """Send notification via email."""
        # Check if email service is available
        if not self.email_service or not self.email_service.is_available():
            delivery.mark_failed("Email service not configured")
            logger.warning("Attempted to send email but service not configured")
            return
            
        try:
            delivery.mark_sent()
            
            # For now, send plain emails until templates are configured
            # This is a REAL implementation - sends actual emails
            subject = f"[Nyelux] {notification.title}"
            body = notification.body
            
            if notification.action_url:
                body += f"\n\nView details: {notification.action_url}"
            
            # Send plain email
            success = await self.email_service.send_plain_email(
                to_email=user.email,
                subject=subject,
                body=body
            )
            
            if success:
                delivery.mark_delivered()
            else:
                delivery.mark_failed("Email send failed")
                
        except Exception as e:
            delivery.mark_failed(str(e))
            logger.error(f"Email notification failed: {e}")
    
    async def _send_sms_notification(
        self,
        notification: Notification,
        user: User,
        delivery: NotificationDelivery
    ):
        """Send notification via SMS."""
        # SMS implementation would go here
        # For now, mark as failed
        delivery.mark_failed("SMS service not implemented")
    
    async def _send_push_notification(
        self,
        notification: Notification,
        user: User,
        delivery: NotificationDelivery
    ):
        """Send push notification."""
        # Push notification implementation would go here
        # For now, mark as failed
        delivery.mark_failed("Push service not implemented")
    
    def _get_recipient_address(self, user: User, channel: str) -> str:
        """Get recipient address for channel."""
        if channel == 'email':
            return user.email
        elif channel == 'sms':
            return user.phone or ""
        elif channel == 'push':
            # Would return device token
            return ""
        elif channel == 'in_app':
            return str(user.id)
        return ""
    
    def _get_email_template_id(self, notification_type: str) -> Optional[str]:
        """Get SendGrid template ID for notification type.
        
        NOTE: This is only used when SendGrid templates are configured.
        Returns None if templates aren't set up.
        """
        # Only use templates if they're actually configured
        if not hasattr(settings, 'SENDGRID_DEFAULT_TEMPLATE_ID'):
            return None
            
        # Template map would be used when templates are configured
        # For now, return None to use plain emails
        return None


# Use dependency injection instead of singleton
# Create instances as needed with NotificationService()


class NotificationBatchService(NotificationService):
    """Extended notification service with batch operations."""
    
    async def send_device_recall_notification(
        self,
        db: AsyncSession,
        device_id: int,
        recall_info: Dict[str, Any]
    ):
        """Send critical device recall notifications."""
        # Find all users who have interacted with this device
        from sqlalchemy import text
        
        notification_data = {
            'device_id': device_id,
            'recall_number': recall_info.get('recall_number'),
            'reason': recall_info.get('reason'),
            'action_required': recall_info.get('action_required')
        }
        
        title = f"URGENT: Device Recall - {recall_info.get('device_name', 'Medical Device')}"
        body = f"A device you've viewed has been recalled. {recall_info.get('reason', '')}. Please take immediate action."
        
        # Get affected users (simplified - in production, would query multiple tables)
        affected_users_query = """
            SELECT DISTINCT u.id
            FROM users u
            JOIN analytics_events ae ON ae.user_id = u.id
            WHERE ae.resource_type = 'device'
            AND ae.resource_id = :device_id
            AND ae.event_type IN ('device_view', 'document_download')
            AND u.deleted_at IS NULL
        """
        
        result = await db.execute(
            text(affected_users_query),
            {"device_id": str(device_id)}
        )
        
        user_ids = [row[0] for row in result]
        
        # Send critical notifications to all affected users
        notifications = await self.send_bulk_notifications(
            db=db,
            user_ids=user_ids,
            notification_type='device_recall',
            title=title,
            body=body,
            priority='critical',
            data=notification_data
        )
        
        logger.info(f"Sent recall notifications for device {device_id} to {len(user_ids)} users")
        return notifications
    
    async def send_mention_notification(
        self,
        db: AsyncSession,
        mentioned_user_id: int,
        mentioning_user_id: int,
        note_id: int,
        context: str
    ):
        """Send notification when user is @mentioned in a note."""
        mentioning_user = await db.get(User, mentioning_user_id)
        
        title = f"{mentioning_user.first_name} {mentioning_user.last_name} mentioned you"
        body = f"You were mentioned in a note: \"{context}...\""
        
        await self.send_notification(
            db,
            mentioned_user_id,
            'mention',
            title,
            body,
            priority='high',
            data={
                'note_id': note_id,
                'mentioning_user_id': mentioning_user_id
            },
            action_url=f"/notes/{note_id}"
        )
    
    async def send_share_notification(
        self,
        db: AsyncSession,
        recipient_user_id: int,
        sharing_user_id: int,
        note_id: int
    ):
        """Send notification when note is shared with user."""
        sharing_user = await db.get(User, sharing_user_id)
        
        title = f"{sharing_user.first_name} {sharing_user.last_name} shared a note with you"
        body = "Click to view the shared note"
        
        await self.send_notification(
            db,
            recipient_user_id,
            'share',
            title,
            body,
            data={
                'note_id': note_id,
                'sharing_user_id': sharing_user_id
            },
            action_url=f"/notes/{note_id}"
        )
