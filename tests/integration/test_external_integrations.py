"""
Integration Testing
Based on NYELUX Test Coverage Document Section 16
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import aiohttp
import redis.asyncio as redis

from src.services.external_services import ExternalServicesManager
from src.db.models.user import User
from src.db.models.notification_delivery import NotificationDelivery


class TestCriticalIntegrations:
    """Test critical external service integrations"""
    
    @pytest.mark.asyncio
    async def test_openai_api_integration(self, client: AsyncClient):
        """Test OpenAI API integration and failure handling"""
        # Test successful API call
        chat_response = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Test Chat"},
            headers={"Authorization": "Bearer test_token"}
        )
        
        conversation_id = chat_response.json()["id"]
        
        # Send message requiring AI response
        message_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "What is an infusion pump?"},
            headers={"Authorization": "Bearer test_token"}
        )
        
        if message_response.status_code == 200:
            # Verify AI response received
            data = message_response.json()
            assert len(data["content"]) > 0
            assert data["model_used"] is not None
            assert data["tokens_used"] > 0
        
        # Test OpenAI API failure handling
        with patch('openai.ChatCompletion.acreate') as mock_openai:
            # Simulate API error
            mock_openai.side_effect = Exception("OpenAI API error")
            
            error_response = await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json={"content": "Another question"},
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert error_response.status_code == 503
            assert "AI service temporarily unavailable" in error_response.json()["detail"]
            
            # Verify fallback behavior
            assert error_response.json().get("fallback_available") is True
            assert error_response.json().get("retry_after") is not None
        
        # Test rate limiting
        rapid_requests = []
        for i in range(60):  # Exceed typical rate limit
            req = client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json={"content": f"Question {i}"},
                headers={"Authorization": "Bearer test_token"}
            )
            rapid_requests.append(req)
        
        responses = await asyncio.gather(*rapid_requests, return_exceptions=True)
        
        # Should hit rate limit
        rate_limited = any(
            isinstance(r, dict) and r.get("status_code") == 429
            for r in responses
        )
        assert rate_limited, "OpenAI rate limiting not enforced"
    
    @pytest.mark.asyncio
    async def test_sendgrid_email_integration(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test SendGrid email service integration"""
        # Create test user
        user = User(
            email="test@example.com",
            first_name="Test",
            last_name="User",
            role="nurse"
        )
        db_session.add(user)
        await db_session.commit()
        
        # Test email sending
        with patch('sendgrid.SendGridAPIClient.send') as mock_send:
            # Mock successful send
            mock_response = MagicMock()
            mock_response.status_code = 202
            mock_response.headers = {"X-Message-Id": "test-message-id"}
            mock_send.return_value = mock_response
            
            # Trigger email
            email_response = await client.post(
                "/api/v1/notifications/send",
                json={
                    "user_id": user.id,
                    "type": "device_recall",
                    "priority": "critical",
                    "channel": "email"
                },
                headers={"Authorization": "Bearer admin_token"}
            )
            
            assert email_response.status_code == 200
            
            # Verify delivery record
            delivery = await db_session.execute(
                """
                SELECT * FROM notification_deliveries
                WHERE channel = 'email'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            
            delivery_record = delivery.fetchone()
            assert delivery_record is not None
            assert delivery_record.status == "sent"
        
        # Test SendGrid failure handling
        with patch('sendgrid.SendGridAPIClient.send') as mock_send:
            # Simulate rate limit error
            mock_send.side_effect = Exception("Rate limit exceeded")
            
            # Try to send email
            error_response = await client.post(
                "/api/v1/notifications/send",
                json={
                    "user_id": user.id,
                    "type": "meeting_reminder",
                    "channel": "email"
                },
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Should handle gracefully
            assert error_response.status_code in [200, 202]
            
            # Check retry queued
            retry_job = await db_session.execute(
                """
                SELECT * FROM background_jobs
                WHERE job_type = 'email_retry'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            
            job = retry_job.fetchone()
            assert job is not None
            assert job.attempts == 1
            assert job.run_at > datetime.utcnow()  # Scheduled for future
    
    @pytest.mark.asyncio
    async def test_twilio_sms_integration(self, client: AsyncClient):
        """Test Twilio SMS integration"""
        with patch('twilio.rest.Client') as mock_twilio:
            # Mock Twilio client
            mock_messages = MagicMock()
            mock_twilio.return_value.messages = mock_messages
            
            # Mock successful SMS send
            mock_message = MagicMock()
            mock_message.sid = "SM123456789"
            mock_message.status = "queued"
            mock_messages.create.return_value = mock_message
            
            # Send SMS notification
            sms_response = await client.post(
                "/api/v1/notifications/send",
                json={
                    "user_id": 1,
                    "type": "device_recall",
                    "channel": "sms",
                    "phone": "+15551234567"
                },
                headers={"Authorization": "Bearer admin_token"}
            )
            
            assert sms_response.status_code == 200
            assert mock_messages.create.called
            
            # Verify call parameters
            call_args = mock_messages.create.call_args
            assert call_args.kwargs["to"] == "+15551234567"
            assert "URGENT" in call_args.kwargs["body"]
        
        # Test international SMS
        intl_response = await client.post(
            "/api/v1/notifications/send",
            json={
                "user_id": 1,
                "type": "support_update",
                "channel": "sms",
                "phone": "+447700900123"  # UK number
            },
            headers={"Authorization": "Bearer admin_token"}
        )
        
        # Should handle international numbers
        assert intl_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_aws_s3_integration(self, client: AsyncClient):
        """Test AWS S3 file storage integration"""
        import boto3
        from moto import mock_s3
        
        with mock_s3():
            # Create mock S3 bucket
            s3_client = boto3.client("s3", region_name="us-east-1")
            s3_client.create_bucket(Bucket="nyelux-documents")
            
            # Test file upload
            test_file = b"Test document content"
            
            upload_response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.pdf", test_file, "application/pdf")},
                data={"document_type": "manual"},
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert upload_response.status_code == 201
            document_data = upload_response.json()
            
            assert document_data["file_url"].startswith("s3://")
            assert document_data["file_size_bytes"] == len(test_file)
            
            # Verify file in S3
            objects = s3_client.list_objects_v2(Bucket="nyelux-documents")
            assert objects["KeyCount"] > 0
            
            # Test S3 failure handling
            s3_client.put_bucket_policy(
                Bucket="nyelux-documents",
                Policy='{"Version":"2012-10-17","Statement":[{"Effect":"Deny","Principal":"*","Action":"*","Resource":"*"}]}'
            )
            
            # Try upload with restricted bucket
            fail_response = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("fail.pdf", b"content", "application/pdf")},
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Should handle S3 error gracefully
            assert fail_response.status_code in [500, 503]
            assert "storage" in fail_response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_elasticsearch_integration(self, client: AsyncClient):
        """Test Elasticsearch search integration"""
        # Test search functionality
        search_response = await client.get(
            "/api/v1/devices/search?q=infusion pump",
            headers={"Authorization": "Bearer test_token"}
        )
        
        if search_response.status_code == 200:
            results = search_response.json()
            
            # Verify Elasticsearch features
            assert "total_count" in results
            assert "facets" in results  # Aggregations
            assert "suggestions" in results  # Did you mean
            assert "execution_time_ms" in results
        
        # Test Elasticsearch failure
        with patch('elasticsearch.AsyncElasticsearch.search') as mock_search:
            mock_search.side_effect = Exception("Elasticsearch cluster unavailable")
            
            # Should fallback to PostgreSQL search
            fallback_response = await client.get(
                "/api/v1/devices/search?q=catheter",
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Should still return results from fallback
            assert fallback_response.status_code == 200
            assert fallback_response.json().get("search_method") == "postgresql_fallback"
    
    @pytest.mark.asyncio
    async def test_redis_cache_integration(self, client: AsyncClient):
        """Test Redis cache integration"""
        # Connect to Redis
        cache = redis.from_url("redis://localhost:6379/0")
        
        try:
            # Clear test keys
            await cache.flushdb()
            
            # Make request that should be cached
            response1 = await client.get(
                "/api/v1/devices/popular",
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response1.status_code == 200
            
            # Check if cached
            cache_key = "devices:popular:org_1"
            cached_value = await cache.get(cache_key)
            assert cached_value is not None
            
            # Make same request - should hit cache
            response2 = await client.get(
                "/api/v1/devices/popular",
                headers={"Authorization": "Bearer test_token"}
            )
            
            # Response should be identical and faster
            assert response2.json() == response1.json()
            
            # Test cache failure handling
            await cache.close()
            
            # Should still work without cache
            response3 = await client.get(
                "/api/v1/devices/popular",
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response3.status_code == 200
            
        finally:
            # Reconnect and cleanup
            cache = redis.from_url("redis://localhost:6379/0")
            await cache.flushdb()
            await cache.close()


class TestIntegrationPoints:
    """Test various system integration points"""
    
    @pytest.mark.asyncio
    async def test_emr_integration(self, client: AsyncClient):
        """Test EMR system integration"""
        # Test HL7 FHIR device resource creation
        fhir_device = {
            "resourceType": "Device",
            "identifier": [{
                "system": "http://example.com/devices",
                "value": "PUMP12345"
            }],
            "status": "active",
            "type": {
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "336602003",
                    "display": "Infusion pump"
                }]
            },
            "patient": {
                "reference": "Patient/123"
            }
        }
        
        # Create device from FHIR
        fhir_response = await client.post(
            "/api/v1/integrations/fhir/Device",
            json=fhir_device,
            headers={"Authorization": "Bearer integration_token"}
        )
        
        if fhir_response.status_code == 201:
            created = fhir_response.json()
            assert created["resourceType"] == "Device"
            assert created["id"] is not None
    
    @pytest.mark.asyncio
    async def test_hr_system_sync(self, client: AsyncClient):
        """Test HR system integration for user provisioning"""
        # Simulate HR system webhook
        hr_payload = {
            "event": "employee.created",
            "data": {
                "employee_id": "EMP12345",
                "email": "newuser@hospital.com",
                "first_name": "New",
                "last_name": "Employee",
                "department": "Emergency",
                "role": "Nurse",
                "start_date": "2024-02-01"
            }
        }
        
        webhook_response = await client.post(
            "/api/v1/webhooks/hr/employee",
            json=hr_payload,
            headers={
                "X-HR-System-Token": "test_hr_token",
                "X-HR-Signature": "test_signature"
            }
        )
        
        assert webhook_response.status_code in [200, 201]
        
        # Verify user created
        user_check = await client.get(
            "/api/v1/users?email=newuser@hospital.com",
            headers={"Authorization": "Bearer admin_token"}
        )
        
        if user_check.status_code == 200:
            users = user_check.json()["results"]
            assert len(users) > 0
            assert users[0]["employee_id"] == "EMP12345"
    
    @pytest.mark.asyncio
    async def test_inventory_system_integration(self, client: AsyncClient):
        """Test inventory management system integration"""
        # Update device inventory
        inventory_update = {
            "device_di": "INV001",
            "location": "Storage Room A",
            "quantity": 25,
            "lot_number": "LOT2024A",
            "expiration_date": "2025-12-31",
            "last_updated": datetime.utcnow().isoformat()
        }
        
        inventory_response = await client.post(
            "/api/v1/integrations/inventory/update",
            json=inventory_update,
            headers={"Authorization": "Bearer inventory_token"}
        )
        
        assert inventory_response.status_code == 200
        
        # Test low stock alert
        low_stock = {
            "device_di": "INV002",
            "current_quantity": 2,
            "minimum_quantity": 5,
            "location": "ICU Supply"
        }
        
        alert_response = await client.post(
            "/api/v1/integrations/inventory/low-stock",
            json=low_stock,
            headers={"Authorization": "Bearer inventory_token"}
        )
        
        assert alert_response.status_code == 200
        
        # Verify notification created
        notif_check = await client.get(
            "/api/v1/notifications?type=low_stock_alert",
            headers={"Authorization": "Bearer admin_token"}
        )
        
        if notif_check.status_code == 200:
            notifications = notif_check.json()["results"]
            assert any(n["metadata"]["device_di"] == "INV002" for n in notifications)
    
    @pytest.mark.asyncio
    async def test_training_platform_integration(self, client: AsyncClient):
        """Test external training platform integration"""
        # Sync training completion
        training_data = {
            "user_email": "nurse@hospital.com",
            "course_id": "DEV101",
            "course_name": "Infusion Pump Operation",
            "completion_date": "2024-01-15T14:30:00Z",
            "score": 95,
            "certificate_url": "https://training.example.com/certs/12345"
        }
        
        training_response = await client.post(
            "/api/v1/integrations/training/completion",
            json=training_data,
            headers={"Authorization": "Bearer training_token"}
        )
        
        assert training_response.status_code == 200
        
        # Verify training record created
        record_check = await client.get(
            "/api/v1/users/training?email=nurse@hospital.com",
            headers={"Authorization": "Bearer admin_token"}
        )
        
        if record_check.status_code == 200:
            records = record_check.json()["training_records"]
            assert any(r["course_id"] == "DEV101" for r in records)


class TestWebhookReliability:
    """Test webhook delivery and reliability"""
    
    @pytest.mark.asyncio
    async def test_webhook_delivery_retry(self, client: AsyncClient):
        """Test webhook delivery with retry logic"""
        # Register webhook endpoint
        webhook_config = {
            "url": "https://example.com/webhooks/nyelux",
            "events": ["device.recall", "incident.created"],
            "secret": "webhook_secret_123"
        }
        
        register_response = await client.post(
            "/api/v1/webhooks/register",
            json=webhook_config,
            headers={"Authorization": "Bearer admin_token"}
        )
        
        webhook_id = register_response.json()["id"]
        
        # Simulate webhook delivery failure
        with patch('aiohttp.ClientSession.post') as mock_post:
            # First attempt fails
            mock_post.side_effect = [
                aiohttp.ClientError("Connection failed"),
                aiohttp.ClientError("Connection failed"),
                AsyncMock(status=200)  # Third attempt succeeds
            ]
            
            # Trigger webhook event
            event_response = await client.post(
                "/api/v1/admin/devices/recall",
                json={
                    "device_di": "WEBHOOK001",
                    "reason": "Test recall"
                },
                headers={"Authorization": "Bearer admin_token"}
            )
            
            # Wait for retries
            await asyncio.sleep(5)
            
            # Verify retry attempts
            assert mock_post.call_count == 3
            
            # Check webhook delivery log
            log_response = await client.get(
                f"/api/v1/webhooks/{webhook_id}/deliveries",
                headers={"Authorization": "Bearer admin_token"}
            )
            
            deliveries = log_response.json()["deliveries"]
            latest = deliveries[0]
            
            assert latest["attempts"] == 3
            assert latest["status"] == "delivered"
    
    @pytest.mark.asyncio
    async def test_webhook_signature_verification(self, client: AsyncClient):
        """Test webhook signature security"""
        import hmac
        import hashlib
        
        secret = "test_webhook_secret"
        payload = {"event": "test", "data": {"id": 123}}
        
        # Calculate correct signature
        signature = hmac.new(
            secret.encode(),
            json.dumps(payload).encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Test with valid signature
        valid_response = await client.post(
            "/api/v1/webhooks/incoming/test",
            json=payload,
            headers={
                "X-Nyelux-Signature": f"sha256={signature}",
                "X-Nyelux-Event": "test.event"
            }
        )
        
        assert valid_response.status_code == 200
        
        # Test with invalid signature
        invalid_response = await client.post(
            "/api/v1/webhooks/incoming/test",
            json=payload,
            headers={
                "X-Nyelux-Signature": "sha256=invalid_signature",
                "X-Nyelux-Event": "test.event"
            }
        )
        
        assert invalid_response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
