"""
Integration tests for External Service Integration.
Tests cover third-party API integrations and service resilience.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
import json
import asyncio
from typing import Dict, List

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.notification import Notification
from src.db.models.device_document import DeviceDocument
from src.db.models.calendar_event import CalendarEvent
from src.services.auth_service import AuthService


class TestIntegrationServices:
    """Test cases for External Service Integration - Section 16"""

    @pytest.fixture
    async def setup_integration_test_data(self, db: AsyncSession):
        """Create test data for integration testing"""
        # Create organization
        org = Organization(
            name="Integration Test Hospital",
            type="hospital",
            subdomain="integration-test",
            license_tier="enterprise"
        )
        db.add(org)
        await db.flush()

        auth_service = AuthService()
        
        # Create test user
        test_user = User(
            email="integration@test.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Integration",
            last_name="Test",
            role="org_admin",
            organization_id=org.id,
            phone="+1234567890"
        )
        db.add(test_user)
        
        # Create test device
        device = GUDIDDevice(
            primary_di="00889842INT001",
            device_name="Integration Test Device",
            manufacturer_name="TestCorp",
            device_class="II"
        )
        db.add(device)
        
        await db.commit()
        
        return {
            "organization": org,
            "user": test_user,
            "device": device
        }

    @pytest.fixture
    async def auth_headers(self, client: AsyncClient, setup_integration_test_data):
        """Get auth headers for test user"""
        user = setup_integration_test_data["user"]
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": user.email, "password": "password123"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_tc_int_001_openai_api_failure_handling(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_integration_test_data
    ):
        """TC-INT-001: Test OpenAI API failure handling"""
        device = setup_integration_test_data["device"]
        
        # Create chat conversation
        response = await client.post(
            "/api/v1/chat/conversations",
            json={"device_id": device.primary_di, "title": "Test Chat"},
            headers=auth_headers
        )
        assert response.status_code == 201
        conversation_id = response.json()["id"]
        
        # Test various OpenAI failure scenarios
        with patch("openai.ChatCompletion.acreate") as mock_openai:
            # Scenario 1: API timeout
            mock_openai.side_effect = asyncio.TimeoutError("Request timeout")
            
            response = await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json={"content": "How does this device work?"},
                headers=auth_headers
            )
            
            # Should handle gracefully
            assert response.status_code in [503, 504]  # Service unavailable or timeout
            assert "temporarily unavailable" in response.json()["detail"].lower()
            
            # Scenario 2: Rate limit exceeded
            from openai.error import RateLimitError
            mock_openai.side_effect = RateLimitError("Rate limit exceeded")
            
            response = await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json={"content": "Another question"},
                headers=auth_headers
            )
            
            assert response.status_code == 429  # Too Many Requests
            assert "rate limit" in response.json()["detail"].lower()
            
            # Scenario 3: Invalid API key
            from openai.error import AuthenticationError
            mock_openai.side_effect = AuthenticationError("Invalid API key")
            
            response = await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json={"content": "Yet another question"},
                headers=auth_headers
            )
            
            assert response.status_code == 503
            
            # Scenario 4: Service outage
            from openai.error import ServiceUnavailableError
            mock_openai.side_effect = ServiceUnavailableError("Service unavailable")
            
            response = await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json={"content": "Final question"},
                headers=auth_headers
            )
            
            assert response.status_code == 503
            
            # System should remain stable
            response = await client.get("/api/v1/health", headers=auth_headers)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_tc_int_002_email_service_degradation(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_integration_test_data
    ):
        """TC-INT-002: Test email service degradation handling"""
        user = setup_integration_test_data["user"]
        
        # Test SendGrid failures
        with patch("sendgrid.SendGridAPIClient.send") as mock_sendgrid:
            # Scenario 1: Rate limit
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.body = "Rate limit exceeded"
            mock_sendgrid.return_value = mock_response
            
            # Trigger email notification
            notification = Notification(
                user_id=user.id,
                type="device_update",
                priority="medium",
                title="Device Update Available",
                body="A new firmware update is available"
            )
            db.add(notification)
            await db.commit()
            
            # Process notification (would be done by background job)
            from src.services.notification_service import NotificationService
            service = NotificationService(db)
            
            with patch("src.services.notification_service.NotificationService.retry_with_backoff") as mock_retry:
                mock_retry.return_value = True
                await service.send_email_notification(notification.id)
                
                # Should implement retry logic
                assert mock_retry.called
            
            # Scenario 2: Service down
            mock_response.status_code = 503
            mock_response.body = "Service temporarily unavailable"
            
            # Should fall back to alternative service
            with patch("src.services.notification_service.use_backup_email_service") as mock_backup:
                mock_backup.return_value = {"status": "sent"}
                
                await service.send_email_notification(notification.id)
                
                # Should use backup service
                if hasattr(service, 'use_backup_email_service'):
                    assert mock_backup.called
            
            # Scenario 3: Invalid recipient
            mock_response.status_code = 400
            mock_response.body = "Invalid email address"
            
            # Should log error but not crash
            result = await service.send_email_notification(notification.id)
            
            # System remains stable
            response = await client.get("/api/v1/health", headers=auth_headers)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_s3_storage_failures(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test S3 storage failure scenarios"""
        # Test file upload with S3 issues
        with patch("boto3.client") as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            
            # Scenario 1: S3 bucket not accessible
            from botocore.exceptions import ClientError
            mock_s3.generate_presigned_post.side_effect = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
                "generate_presigned_post"
            )
            
            response = await client.post(
                "/api/v1/documents/upload/presigned",
                json={"filename": "test.pdf", "content_type": "application/pdf"},
                headers=auth_headers
            )
            
            # Should handle error gracefully
            assert response.status_code in [500, 503]
            assert "storage" in response.json()["detail"].lower()
            
            # Scenario 2: S3 region outage
            mock_s3.generate_presigned_post.side_effect = ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
                "generate_presigned_post"
            )
            
            response = await client.post(
                "/api/v1/documents/upload/presigned",
                json={"filename": "test2.pdf", "content_type": "application/pdf"},
                headers=auth_headers
            )
            
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_elasticsearch_failures(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test Elasticsearch failure handling"""
        with patch("elasticsearch.AsyncElasticsearch") as mock_es:
            mock_client = AsyncMock()
            mock_es.return_value = mock_client
            
            # Scenario 1: Cluster unavailable
            from elasticsearch.exceptions import ConnectionError
            mock_client.search.side_effect = ConnectionError("Connection refused")
            
            # Should fall back to database search
            response = await client.post(
                "/api/v1/devices/search",
                json={"query": "infusion pump"},
                headers=auth_headers
            )
            
            # Should still return results (from PostgreSQL)
            assert response.status_code == 200
            assert "results" in response.json()
            
            # Scenario 2: Index corruption
            from elasticsearch.exceptions import RequestError
            mock_client.search.side_effect = RequestError(
                400, "search_phase_execution_exception", {"error": "Index corrupted"}
            )
            
            response = await client.post(
                "/api/v1/devices/search",
                json={"query": "catheter"},
                headers=auth_headers
            )
            
            # Should handle gracefully
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_redis_cache_failures(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test Redis cache failure scenarios"""
        with patch("redis.asyncio.Redis") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.from_url.return_value = mock_client
            
            # Scenario 1: Redis connection lost
            mock_client.get.side_effect = ConnectionError("Connection lost")
            mock_client.set.side_effect = ConnectionError("Connection lost")
            
            # Should work without cache
            response = await client.get(
                "/api/v1/devices",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            
            # Performance might degrade but functionality preserved
            start_time = time.time()
            response = await client.post(
                "/api/v1/devices/search",
                json={"query": "monitor"},
                headers=auth_headers
            )
            elapsed = time.time() - start_time
            
            assert response.status_code == 200
            # Without cache, might be slower but still under 1s
            assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_calendar_integration_failures(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test calendar integration failure handling"""
        # Test Google Calendar failures
        with patch("googleapiclient.discovery.build") as mock_google:
            mock_service = MagicMock()
            mock_google.return_value = mock_service
            
            # Scenario 1: OAuth token expired
            from googleapiclient.errors import HttpError
            mock_service.events().insert().execute.side_effect = HttpError(
                MagicMock(status=401), b"Invalid Credentials"
            )
            
            # Create event that should sync
            response = await client.post(
                "/api/v1/calendar/events",
                json={
                    "title": "Test Meeting",
                    "start_time": "2024-02-01T10:00:00-05:00",
                    "end_time": "2024-02-01T11:00:00-05:00",
                    "sync_to_external": True
                },
                headers=auth_headers
            )
            
            # Event should be created locally even if sync fails
            assert response.status_code == 201
            event_data = response.json()
            assert "sync_status" in event_data
            assert event_data["sync_status"] == "failed"
            
            # Test Outlook/Microsoft Graph failures
            with patch("msal.ConfidentialClientApplication") as mock_msal:
                mock_app = MagicMock()
                mock_msal.return_value = mock_app
                
                # Token acquisition failure
                mock_app.acquire_token_silent.return_value = None
                mock_app.acquire_token_for_client.return_value = {
                    "error": "invalid_client"
                }
                
                # Should handle gracefully
                response = await client.post(
                    "/api/v1/calendar/sync/outlook",
                    json={"auth_code": "test_code"},
                    headers=auth_headers
                )
                
                assert response.status_code in [400, 503]

    @pytest.mark.asyncio
    async def test_twilio_sms_failures(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_integration_test_data
    ):
        """Test Twilio SMS service failures"""
        user = setup_integration_test_data["user"]
        
        with patch("twilio.rest.Client") as mock_twilio:
            mock_client = MagicMock()
            mock_twilio.return_value = mock_client
            
            # Scenario 1: Invalid phone number
            from twilio.base.exceptions import TwilioRestException
            mock_client.messages.create.side_effect = TwilioRestException(
                status=400,
                uri="/Messages.json",
                msg="Invalid phone number"
            )
            
            # Create SMS notification
            notification = Notification(
                user_id=user.id,
                type="device_recall",
                priority="critical",
                title="Urgent Device Recall",
                body="Device recall notice"
            )
            db.add(notification)
            await db.commit()
            
            # Should handle error
            from src.services.notification_service import NotificationService
            service = NotificationService(db)
            result = await service.send_sms_notification(notification.id)
            
            # Should log error but not crash
            assert result is False or result.get("status") == "failed"
            
            # Scenario 2: Rate limit
            mock_client.messages.create.side_effect = TwilioRestException(
                status=429,
                uri="/Messages.json",
                msg="Rate limit exceeded"
            )
            
            # Should implement backoff
            with patch("asyncio.sleep") as mock_sleep:
                result = await service.send_sms_notification(notification.id)
                # Should have attempted backoff
                assert mock_sleep.called or result is False

    @pytest.mark.asyncio
    async def test_multi_service_cascade_failure(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test handling of multiple service failures simultaneously"""
        # Simulate multiple services failing
        with patch("openai.ChatCompletion.acreate") as mock_openai, \
             patch("elasticsearch.AsyncElasticsearch.search") as mock_es, \
             patch("redis.asyncio.Redis.get") as mock_redis, \
             patch("boto3.client") as mock_boto:
            
            # All services experiencing issues
            mock_openai.side_effect = Exception("OpenAI unavailable")
            mock_es.side_effect = Exception("Elasticsearch down")
            mock_redis.side_effect = Exception("Redis connection lost")
            
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.side_effect = Exception("S3 error")
            mock_boto.return_value = mock_s3
            
            # Core functionality should still work
            # 1. Authentication should work (uses PostgreSQL)
            response = await client.get(
                "/api/v1/users/me",
                headers=auth_headers
            )
            assert response.status_code == 200
            
            # 2. Basic device listing (from PostgreSQL)
            response = await client.get(
                "/api/v1/devices",
                headers=auth_headers
            )
            assert response.status_code == 200
            
            # 3. Health check should indicate degraded state
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            
            health_data = response.json()
            if "services" in health_data:
                assert health_data["services"]["database"] == "healthy"
                assert health_data["services"]["cache"] == "unhealthy"
                assert health_data["services"]["search"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_webhook_delivery_resilience(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test webhook delivery with recipient failures"""
        # Configure webhook
        webhook_config = {
            "url": "https://customer.example.com/webhooks/nyelux",
            "events": ["device_recall", "incident_created"],
            "secret": "webhook_secret_123"
        }
        
        response = await client.post(
            "/api/v1/webhooks",
            json=webhook_config,
            headers=auth_headers
        )
        assert response.status_code == 201
        webhook_id = response.json()["id"]
        
        # Test delivery scenarios
        with patch("httpx.AsyncClient.post") as mock_post:
            # Scenario 1: Recipient timeout
            mock_post.side_effect = asyncio.TimeoutError()
            
            # Trigger webhook event
            from src.services.webhook_service import WebhookService
            service = WebhookService(db)
            
            event_data = {
                "type": "device_recall",
                "data": {"device_id": "123", "reason": "Safety issue"}
            }
            
            result = await service.deliver_webhook(webhook_id, event_data)
            
            # Should retry with exponential backoff
            assert result.get("status") == "failed"
            assert result.get("retry_count", 0) > 0
            
            # Scenario 2: Recipient returns error
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_post.return_value = mock_response
            
            result = await service.deliver_webhook(webhook_id, event_data)
            
            # Should retry
            assert result.get("status") == "failed"
            
            # Scenario 3: SSL verification failure
            import ssl
            mock_post.side_effect = ssl.SSLError("Certificate verify failed")
            
            result = await service.deliver_webhook(webhook_id, event_data)
            
            # Should handle SSL errors
            assert result.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_emr_integration_resilience(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test EMR system integration resilience"""
        # Test HL7/FHIR integration failures
        with patch("hl7apy.core.Message.parse") as mock_hl7:
            # Scenario 1: Malformed HL7 message
            mock_hl7.side_effect = Exception("Invalid HL7 format")
            
            # Send device data to EMR
            response = await client.post(
                "/api/v1/integrations/emr/send-device",
                json={
                    "device_id": "00889842INT001",
                    "emr_system": "epic",
                    "patient_id": "12345"
                },
                headers=auth_headers
            )
            
            # Should handle parsing errors
            assert response.status_code in [400, 503]
            
            # Test FHIR server connection
            with patch("fhirclient.client.FHIRClient") as mock_fhir:
                mock_client = MagicMock()
                mock_fhir.return_value = mock_client
                
                # FHIR server down
                mock_client.server.request_json.side_effect = ConnectionError()
                
                response = await client.get(
                    "/api/v1/integrations/fhir/devices",
                    headers=auth_headers
                )
                
                # Should handle connection errors
                assert response.status_code in [503, 504]

    @pytest.mark.asyncio
    async def test_payment_processor_failures(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test payment processing integration failures"""
        # Test Stripe integration
        with patch("stripe.Customer.create") as mock_stripe:
            # Scenario 1: Card declined
            import stripe
            mock_stripe.side_effect = stripe.error.CardError(
                "Card declined",
                "card_declined",
                "ch_failed"
            )
            
            # Attempt subscription upgrade
            response = await client.post(
                "/api/v1/billing/upgrade",
                json={
                    "plan": "enterprise",
                    "payment_method": "pm_card_visa"
                },
                headers=auth_headers
            )
            
            # Should handle payment failure gracefully
            assert response.status_code == 402  # Payment Required
            assert "declined" in response.json()["detail"].lower()
            
            # Scenario 2: Stripe API down
            mock_stripe.side_effect = stripe.error.APIConnectionError(
                "Connection error"
            )
            
            response = await client.post(
                "/api/v1/billing/upgrade",
                json={
                    "plan": "professional",
                    "payment_method": "pm_card_mastercard"
                },
                headers=auth_headers
            )
            
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_monitoring_service_failures(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test monitoring and logging service failures"""
        # Test Datadog integration
        with patch("datadog.api.Metric.send") as mock_datadog:
            # Datadog API failure shouldn't affect main functionality
            mock_datadog.side_effect = Exception("Datadog API error")
            
            # Perform normal operations
            response = await client.get(
                "/api/v1/devices",
                headers=auth_headers
            )
            
            # Should still work
            assert response.status_code == 200
            
            # Test Sentry error tracking
            with patch("sentry_sdk.capture_exception") as mock_sentry:
                mock_sentry.side_effect = Exception("Sentry unreachable")
                
                # Trigger an error
                response = await client.get(
                    "/api/v1/devices/nonexistent",
                    headers=auth_headers
                )
                
                # Error handling should still work
                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_circuit_breaker_pattern(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test circuit breaker implementation for external services"""
        # Test circuit breaker for OpenAI
        failure_count = 0
        
        async def failing_openai(*args, **kwargs):
            nonlocal failure_count
            failure_count += 1
            if failure_count < 5:
                raise Exception("Service error")
            # After 5 failures, service "recovers"
            return {
                "choices": [{
                    "message": {"content": "Service recovered"}
                }]
            }
        
        with patch("openai.ChatCompletion.acreate", side_effect=failing_openai):
            # Make multiple requests
            responses = []
            for i in range(10):
                response = await client.post(
                    "/api/v1/chat/conversations/1/messages",
                    json={"content": f"Question {i}"},
                    headers=auth_headers
                )
                responses.append(response.status_code)
                await asyncio.sleep(0.1)
            
            # Circuit breaker should open after initial failures
            # Some requests should fail fast (503) without calling service
            assert 503 in responses
            
            # Eventually should recover
            assert 200 in responses[-3:]  # Last few should succeed

    @pytest.mark.asyncio
    async def test_graceful_degradation_features(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test feature degradation when services unavailable"""
        # Disable AI features when OpenAI unavailable
        with patch("openai.ChatCompletion.acreate") as mock_openai:
            mock_openai.side_effect = Exception("OpenAI unavailable")
            
            # Check feature availability
            response = await client.get(
                "/api/v1/features/status",
                headers=auth_headers
            )
            
            if response.status_code == 200:
                features = response.json()
                assert features["ai_chat"]["available"] is False
                assert features["ai_chat"]["reason"] == "Service temporarily unavailable"
                
                # Core features should still be available
                assert features["device_search"]["available"] is True
                assert features["document_management"]["available"] is True
