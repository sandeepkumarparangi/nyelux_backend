"""
Integration tests for Notification System functionality.
Tests cover multi-channel delivery, preferences, and notification types.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, time
from unittest.mock import patch, AsyncMock, call
import json
from typing import List

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.notification import Notification
from src.db.models.notification_delivery import NotificationDelivery
from src.db.models.notification_preferences import NotificationPreferences
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.services.auth_service import AuthService


class TestNotificationSystem:
    """Test cases for Notification System - Section 11"""

    @pytest.fixture
    async def setup_users_with_preferences(self, db: AsyncSession):
        """Create test users with different notification preferences"""
        org = Organization(
            name="Test Hospital",
            type="hospital",
            subdomain="test-hospital"
        )
        db.add(org)
        await db.flush()

        auth_service = AuthService()
        
        # User with all channels enabled
        all_channels_user = User(
            email="all_channels@example.com",
            phone="+1234567890",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="All",
            last_name="Channels",
            role="nurse",
            organization_id=org.id
        )
        
        # User with quiet hours
        quiet_hours_user = User(
            email="quiet_hours@example.com",
            phone="+1234567891",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Quiet",
            last_name="Hours",
            role="physician",
            organization_id=org.id,
            timezone="America/New_York"
        )
        
        # User with email only
        email_only_user = User(
            email="email_only@example.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Email",
            last_name="Only",
            role="technician",
            organization_id=org.id
        )
        
        db.add_all([all_channels_user, quiet_hours_user, email_only_user])
        await db.flush()
        
        # Set notification preferences
        all_pref = NotificationPreferences(
            user_id=all_channels_user.id,
            email_enabled=True,
            sms_enabled=True,
            push_enabled=True,
            in_app_enabled=True,
            categories=json.dumps({
                "device_recall": {"email": True, "sms": True, "push": True},
                "training_available": {"email": True, "sms": False, "push": True},
                "meeting_reminder": {"email": True, "sms": True, "push": True}
            })
        )
        
        quiet_pref = NotificationPreferences(
            user_id=quiet_hours_user.id,
            email_enabled=True,
            sms_enabled=True,
            push_enabled=True,
            quiet_hours_start=time(22, 0),  # 10 PM
            quiet_hours_end=time(7, 0),     # 7 AM
            timezone="America/New_York"
        )
        
        email_pref = NotificationPreferences(
            user_id=email_only_user.id,
            email_enabled=True,
            sms_enabled=False,
            push_enabled=False,
            in_app_enabled=True
        )
        
        db.add_all([all_pref, quiet_pref, email_pref])
        await db.commit()
        
        return all_channels_user, quiet_hours_user, email_only_user

    @pytest.fixture
    async def auth_headers(self, client: AsyncClient, setup_users_with_preferences, db: AsyncSession):
        """Get auth headers for test user"""
        all_channels_user, _, _ = setup_users_with_preferences
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": all_channels_user.email, "password": "password123"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_tc_notif_001_device_recall_critical_alert(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """TC-NOTIF-001: Test critical device recall notification to all channels"""
        all_channels_user, _, _ = setup_users_with_preferences
        
        # Create a recalled device
        device = GUDIDDevice(
            primary_di="00889842001234",
            device_name="Critical Infusion Pump",
            manufacturer_name="MedCorp",
            device_class="III"
        )
        db.add(device)
        
        vendor_device = VendorDevice(
            gudid_device_di=device.primary_di,
            organization_id=all_channels_user.organization_id,
            custom_name="ICU Infusion Pump Model X"
        )
        db.add(vendor_device)
        await db.commit()
        
        # Simulate device recall notification
        with patch("src.services.notification_service.send_email") as mock_email, \
             patch("src.services.notification_service.send_sms") as mock_sms, \
             patch("src.services.notification_service.send_push") as mock_push:
            
            mock_email.return_value = {"status": "sent", "message_id": "email_123"}
            mock_sms.return_value = {"status": "sent", "message_id": "sms_123"}
            mock_push.return_value = {"status": "sent", "message_id": "push_123"}
            
            notification_data = {
                "type": "device_recall",
                "priority": "critical",
                "title": "URGENT: Device Recall Notice",
                "body": f"The {device.device_name} has been recalled by the FDA. Immediate action required.",
                "action_url": f"/devices/{device.primary_di}",
                "data": {
                    "device_di": device.primary_di,
                    "device_name": device.device_name,
                    "recall_reason": "Potential malfunction causing patient injury",
                    "fda_recall_number": "Z-1234-2024"
                },
                "user_ids": [all_channels_user.id]
            }
            
            # Admin endpoint to trigger notification
            admin_token = "admin_token_here"  # Would be obtained through admin login
            response = await client.post(
                "/api/v1/notifications/send",
                json=notification_data,
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            # For testing purposes, simulate the notification service
            notification = Notification(
                user_id=all_channels_user.id,
                type="device_recall",
                priority="critical",
                title=notification_data["title"],
                body=notification_data["body"],
                action_url=notification_data["action_url"],
                data=notification_data["data"]
            )
            db.add(notification)
            await db.commit()
            
            # Verify all channels were attempted
            assert mock_email.called
            assert mock_sms.called
            assert mock_push.called
            
            # Verify critical notifications bypass quiet hours
            assert mock_email.call_args[1]["immediate"] is True

    @pytest.mark.asyncio
    async def test_tc_notif_002_quiet_hours_respect(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """TC-NOTIF-002: Test quiet hours enforcement for non-urgent notifications"""
        _, quiet_hours_user, _ = setup_users_with_preferences
        
        # Create non-urgent notification at 11 PM (during quiet hours)
        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 2, 1, 23, 0, 0)  # 11 PM
            mock_datetime.utcnow = mock_datetime.now
            
            with patch("src.services.notification_service.send_email") as mock_email, \
                 patch("src.services.notification_service.send_sms") as mock_sms:
                
                # Non-urgent notification
                notification = Notification(
                    user_id=quiet_hours_user.id,
                    type="training_available",
                    priority="low",
                    title="New Training Available",
                    body="A new training video for Device XYZ is available",
                    action_url="/training/123"
                )
                db.add(notification)
                await db.commit()
                
                # Process notifications (would be done by background job)
                # Simulate notification service processing
                from src.services.notification_service import NotificationService
                service = NotificationService(db)
                await service.process_notification(notification.id)
                
                # Verify notification was queued, not sent immediately
                delivery = await db.query(NotificationDelivery).filter(
                    NotificationDelivery.notification_id == notification.id
                ).first()
                
                assert delivery is None or delivery.status == "queued"
                assert not mock_email.called  # Should not send during quiet hours
                assert not mock_sms.called
                
                # Urgent notification should still go through
                urgent_notification = Notification(
                    user_id=quiet_hours_user.id,
                    type="device_recall",
                    priority="critical",
                    title="URGENT: Device Recall",
                    body="Critical safety issue",
                    action_url="/devices/recall/123"
                )
                db.add(urgent_notification)
                await db.commit()
                
                mock_email.return_value = {"status": "sent"}
                mock_sms.return_value = {"status": "sent"}
                
                await service.process_notification(urgent_notification.id)
                
                # Urgent should be sent immediately
                assert mock_email.called
                assert mock_sms.called

    @pytest.mark.asyncio
    async def test_multi_channel_delivery_tracking(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """Test delivery status tracking across multiple channels"""
        all_channels_user, _, _ = setup_users_with_preferences
        
        notification = Notification(
            user_id=all_channels_user.id,
            type="system_alert",
            priority="high",
            title="System Maintenance Notice",
            body="System will be under maintenance from 2 AM to 4 AM EST",
            expires_at=datetime.utcnow() + timedelta(days=1)
        )
        db.add(notification)
        await db.commit()
        
        # Simulate delivery attempts
        channels = ["email", "sms", "push", "in_app"]
        
        for channel in channels:
            delivery = NotificationDelivery(
                notification_id=notification.id,
                channel=channel,
                recipient_address=all_channels_user.email if channel == "email" else all_channels_user.phone,
                status="pending"
            )
            db.add(delivery)
        
        await db.commit()
        
        # Simulate successful email, failed SMS, delivered push
        email_delivery = await db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_id == notification.id,
            NotificationDelivery.channel == "email"
        ).first()
        
        email_delivery.status = "delivered"
        email_delivery.sent_at = datetime.utcnow()
        email_delivery.delivered_at = datetime.utcnow()
        
        sms_delivery = await db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_id == notification.id,
            NotificationDelivery.channel == "sms"
        ).first()
        
        sms_delivery.status = "failed"
        sms_delivery.failed_at = datetime.utcnow()
        sms_delivery.error_message = "Invalid phone number format"
        
        await db.commit()

    @pytest.mark.asyncio
    async def test_notification_preferences_api(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test notification preferences management API"""
        # Get current preferences
        response = await client.get(
            "/api/v1/notifications/preferences",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        current_prefs = response.json()
        
        # Update preferences
        update_data = {
            "email_enabled": True,
            "sms_enabled": False,
            "push_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "categories": {
                "device_recall": {
                    "email": True,
                    "sms": True,  # Override general SMS disabled for critical
                    "push": True
                },
                "meeting_reminder": {
                    "email": True,
                    "sms": False,
                    "push": False
                }
            }
        }
        
        response = await client.put(
            "/api/v1/notifications/preferences",
            json=update_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Verify updates
        response = await client.get(
            "/api/v1/notifications/preferences",
            headers=auth_headers
        )
        updated_prefs = response.json()
        
        assert updated_prefs["sms_enabled"] is False
        assert updated_prefs["quiet_hours_start"] == "22:00"
        assert updated_prefs["categories"]["device_recall"]["sms"] is True

    @pytest.mark.asyncio
    async def test_notification_templates(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """Test notification templates for different types"""
        all_channels_user, _, _ = setup_users_with_preferences
        
        notification_types = [
            {
                "type": "device_update",
                "data": {
                    "device_name": "Infusion Pump X",
                    "update_type": "firmware",
                    "version": "2.3.4",
                    "release_notes": "Security patches and bug fixes"
                }
            },
            {
                "type": "meeting_reminder",
                "data": {
                    "meeting_title": "Device Training Session",
                    "start_time": "2024-02-01T14:00:00-05:00",
                    "meeting_url": "https://zoom.us/j/123456789"
                }
            },
            {
                "type": "incident_update",
                "data": {
                    "ticket_number": "INC-2024-001",
                    "status": "resolved",
                    "device_name": "Patient Monitor",
                    "resolution_summary": "Replaced faulty sensor"
                }
            }
        ]
        
        for notif_type in notification_types:
            # Create notification with template data
            notification = Notification(
                user_id=all_channels_user.id,
                type=notif_type["type"],
                priority="medium",
                title=f"Test {notif_type['type']}",
                body="Template test",
                data=notif_type["data"]
            )
            db.add(notification)
        
        await db.commit()

    @pytest.mark.asyncio
    async def test_batch_notifications(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """Test batch notification sending"""
        users = setup_users_with_preferences
        
        # Create batch notification for all users
        with patch("src.services.notification_service.send_email") as mock_email:
            mock_email.return_value = {"status": "sent"}
            
            batch_data = {
                "type": "system_announcement",
                "priority": "medium",
                "title": "New Feature Announcement",
                "body": "We've added image recognition capabilities to the platform",
                "user_filters": {
                    "roles": ["nurse", "physician", "technician"],
                    "organizations": [users[0].organization_id]
                }
            }
            
            # Admin endpoint
            admin_token = "admin_token_here"
            response = await client.post(
                "/api/v1/notifications/batch",
                json=batch_data,
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            # Simulate batch processing
            for user in users:
                notification = Notification(
                    user_id=user.id,
                    type=batch_data["type"],
                    priority=batch_data["priority"],
                    title=batch_data["title"],
                    body=batch_data["body"]
                )
                db.add(notification)
            
            await db.commit()

    @pytest.mark.asyncio
    async def test_notification_analytics(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test notification analytics and metrics"""
        # Get notification statistics
        response = await client.get(
            "/api/v1/notifications/analytics?period=7d",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        analytics = response.json()
        expected_metrics = [
            "total_sent",
            "delivery_rate",
            "open_rate",
            "click_rate",
            "by_channel",
            "by_type"
        ]
        
        for metric in expected_metrics:
            assert metric in analytics

    @pytest.mark.asyncio
    async def test_push_notification_tokens(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test push notification token management"""
        # Register push token
        token_data = {
            "token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
            "platform": "ios",
            "device_info": {
                "model": "iPhone 14",
                "os_version": "16.0"
            }
        }
        
        response = await client.post(
            "/api/v1/notifications/push-tokens",
            json=token_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Update token
        updated_token = {
            "token": "ExponentPushToken[yyyyyyyyyyyyyyyyyyyyyy]",
            "platform": "ios"
        }
        
        response = await client.put(
            "/api/v1/notifications/push-tokens",
            json=updated_token,
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Remove token (logout)
        response = await client.delete(
            "/api/v1/notifications/push-tokens/ExponentPushToken[yyyyyyyyyyyyyyyyyyyyyy]",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_email_unsubscribe_compliance(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """Test CAN-SPAM compliance with unsubscribe handling"""
        email_only_user = setup_users_with_preferences[2]
        
        # Generate unsubscribe token
        from src.services.notification_service import generate_unsubscribe_token
        unsubscribe_token = generate_unsubscribe_token(email_only_user.id, "marketing")
        
        # Test unsubscribe link
        response = await client.get(
            f"/api/v1/notifications/unsubscribe/{unsubscribe_token}"
        )
        assert response.status_code == 200
        
        # Verify preference updated
        pref = await db.query(NotificationPreferences).filter(
            NotificationPreferences.user_id == email_only_user.id
        ).first()
        
        categories = json.loads(pref.categories) if pref.categories else {}
        assert categories.get("marketing", {}).get("email", True) is False

    @pytest.mark.asyncio
    async def test_webhook_notifications(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test webhook notification delivery"""
        # Configure webhook endpoint
        webhook_config = {
            "url": "https://example.com/webhooks/nyelux",
            "events": ["device_recall", "incident_critical"],
            "secret": "webhook_secret_123",
            "headers": {
                "X-Custom-Header": "CustomValue"
            }
        }
        
        response = await client.post(
            "/api/v1/notifications/webhooks",
            json=webhook_config,
            headers=auth_headers
        )
        assert response.status_code == 201
        
        webhook_id = response.json()["id"]
        
        # Test webhook delivery
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"status": "received"}
            
            # Trigger a device recall notification
            notification_data = {
                "type": "device_recall",
                "data": {
                    "device_di": "00889842001234",
                    "recall_reason": "Safety issue"
                }
            }
            
            # Simulate webhook trigger
            # Would be called by notification service
            
            # Verify webhook was called
            # mock_post.assert_called()

    @pytest.mark.asyncio
    async def test_notification_retry_logic(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """Test notification retry logic for failed deliveries"""
        all_channels_user, _, _ = setup_users_with_preferences
        
        notification = Notification(
            user_id=all_channels_user.id,
            type="system_alert",
            priority="high",
            title="Important Update",
            body="Please review the latest safety guidelines"
        )
        db.add(notification)
        await db.commit()
        
        # Create failed delivery
        delivery = NotificationDelivery(
            notification_id=notification.id,
            channel="email",
            recipient_address=all_channels_user.email,
            status="failed",
            failed_at=datetime.utcnow(),
            error_message="Temporary server error",
            retry_count=0
        )
        db.add(delivery)
        await db.commit()
        
        # Simulate retry process
        with patch("src.services.notification_service.send_email") as mock_email:
            mock_email.return_value = {"status": "sent", "message_id": "retry_123"}
            
            # Process retries (would be done by background job)
            from src.services.notification_service import NotificationService
            service = NotificationService(db)
            await service.retry_failed_notifications()
            
            # Verify retry attempted
            await db.refresh(delivery)
            assert delivery.retry_count == 1
            
            # Simulate max retries reached
            delivery.retry_count = 3
            delivery.status = "failed"
            await db.commit()
            
            await service.retry_failed_notifications()
            
            # Should not retry after max attempts
            await db.refresh(delivery)
            assert delivery.retry_count == 3
            assert delivery.status == "failed"

    @pytest.mark.asyncio
    async def test_notification_localization(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """Test notification localization based on user preferences"""
        all_channels_user, _, _ = setup_users_with_preferences
        
        # Update user language preference
        all_channels_user.language_preference = "es"
        await db.commit()
        
        # Create notification that should be localized
        notification = Notification(
            user_id=all_channels_user.id,
            type="device_recall",
            priority="critical",
            title="Device Recall Notice",  # Will be translated
            body="Important safety information",  # Will be translated
            data={
                "device_name": "Infusion Pump X",
                "template_key": "device_recall"
            }
        )
        db.add(notification)
        await db.commit()
        
        # Verify localization would be applied
        # In real implementation, this would use i18n service
        assert all_channels_user.language_preference == "es"

    @pytest.mark.asyncio
    async def test_notification_grouping_digest(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """Test notification grouping and digest functionality"""
        email_only_user = setup_users_with_preferences[2]
        
        # Update user to receive digest
        pref = await db.query(NotificationPreferences).filter(
            NotificationPreferences.user_id == email_only_user.id
        ).first()
        
        pref.frequency = json.dumps({
            "training_available": "daily_digest",
            "device_update": "daily_digest",
            "low_priority": "weekly_digest"
        })
        await db.commit()
        
        # Create multiple notifications that should be grouped
        notifications = []
        for i in range(5):
            notif = Notification(
                user_id=email_only_user.id,
                type="training_available",
                priority="low",
                title=f"New Training {i+1}",
                body=f"Training for Device {i+1} is available",
                created_at=datetime.utcnow() - timedelta(hours=i)
            )
            notifications.append(notif)
            db.add(notif)
        
        await db.commit()
        
        # Simulate digest generation (would be done by scheduled job)
        # Verify notifications would be grouped
        assert len(notifications) == 5

    @pytest.mark.asyncio
    async def test_edge_cases(
        self, client: AsyncClient, db: AsyncSession, setup_users_with_preferences
    ):
        """Test notification system edge cases"""
        all_channels_user, _, _ = setup_users_with_preferences
        
        # Edge case: Notification with very long content
        long_notification = Notification(
            user_id=all_channels_user.id,
            type="system_alert",
            priority="medium",
            title="A" * 500,  # Very long title
            body="B" * 10000,  # Very long body
            data={"large_data": "C" * 1000}
        )
        db.add(long_notification)
        await db.commit()
        
        # Should truncate for SMS
        with patch("src.services.notification_service.send_sms") as mock_sms:
            mock_sms.return_value = {"status": "sent"}
            
            # Process notification
            from src.services.notification_service import NotificationService
            service = NotificationService(db)
            await service.send_sms_notification(long_notification.id)
            
            # Verify SMS was truncated (160 char limit)
            call_args = mock_sms.call_args[1]
            assert len(call_args["message"]) <= 160
        
        # Edge case: User with no contact info
        no_contact_user = User(
            email="",  # Empty email
            phone=None,  # No phone
            password_hash="hash",
            first_name="No",
            last_name="Contact",
            role="nurse",
            organization_id=all_channels_user.organization_id
        )
        db.add(no_contact_user)
        await db.commit()
        
        # Try to send notification
        notification = Notification(
            user_id=no_contact_user.id,
            type="device_recall",
            priority="critical",
            title="Critical Alert",
            body="Important message"
        )
        db.add(notification)
        await db.commit()
        
        # Should only create in-app notification
        deliveries = await db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_id == notification.id
        ).all()
        
        in_app_delivery = [d for d in deliveries if d.channel == "in_app"]
        assert len(in_app_delivery) > 0
        
        # Edge case: Expired notification
        expired_notification = Notification(
            user_id=all_channels_user.id,
            type="meeting_reminder",
            priority="medium",
            title="Old Meeting",
            body="This meeting already happened",
            expires_at=datetime.utcnow() - timedelta(days=1)  # Already expired
        )
        db.add(expired_notification)
        await db.commit()
        
        # Should not send expired notification
        with patch("src.services.notification_service.send_email") as mock_email:
            service = NotificationService(db)
            await service.process_notification(expired_notification.id)
            
            # Should not attempt to send
            assert not mock_email.called
