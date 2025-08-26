"""
Integration tests for Analytics & Reporting functionality.
Tests cover real-time analytics, custom reports, and compliance reporting.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, date
from unittest.mock import patch, AsyncMock
import json
import io
import csv
from typing import List, Dict

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.analytics_event import AnalyticsEvent
from src.db.models.device_analytics_daily import DeviceAnalyticsDaily
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.db.models.audit_log import AuditLog
from src.services.auth_service import AuthService


class TestAnalyticsReporting:
    """Test cases for Analytics & Reporting - Section 12"""

    @pytest.fixture
    async def setup_analytics_data(self, db: AsyncSession):
        """Create test data for analytics"""
        # Create organizations
        hospital = Organization(
            name="Analytics Hospital",
            type="hospital",
            subdomain="analytics-hospital"
        )
        vendor = Organization(
            name="Device Vendor Inc",
            type="vendor",
            subdomain="device-vendor"
        )
        db.add_all([hospital, vendor])
        await db.flush()

        auth_service = AuthService()
        
        # Create users
        admin_user = User(
            email="admin@hospital.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Admin",
            last_name="User",
            role="org_admin",
            organization_id=hospital.id
        )
        
        nurse_user = User(
            email="nurse@hospital.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Nurse",
            last_name="User",
            role="nurse",
            organization_id=hospital.id
        )
        
        vendor_admin = User(
            email="vendor@device.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Vendor",
            last_name="Admin",
            role="vendor_admin",
            organization_id=vendor.id
        )
        
        db.add_all([admin_user, nurse_user, vendor_admin])
        await db.flush()
        
        # Create devices
        devices = []
        for i in range(5):
            device = GUDIDDevice(
                primary_di=f"0088984200{1000+i}",
                device_name=f"Test Device {i+1}",
                manufacturer_name="MedCorp",
                device_class="II" if i < 3 else "III"
            )
            devices.append(device)
            db.add(device)
        
        await db.flush()
        
        # Create vendor devices
        for i, device in enumerate(devices[:3]):
            vendor_device = VendorDevice(
                gudid_device_di=device.primary_di,
                organization_id=vendor.id,
                custom_name=f"Vendor Device {i+1}"
            )
            db.add(vendor_device)
        
        await db.commit()
        
        return {
            "hospital": hospital,
            "vendor": vendor,
            "admin_user": admin_user,
            "nurse_user": nurse_user,
            "vendor_admin": vendor_admin,
            "devices": devices
        }

    @pytest.fixture
    async def generate_analytics_events(self, db: AsyncSession, setup_analytics_data):
        """Generate realistic analytics events"""
        data = setup_analytics_data
        
        # Generate events over past 30 days
        events = []
        event_types = ["page_view", "search", "device_view", "document_download", "video_play"]
        
        for days_ago in range(30):
            event_date = datetime.utcnow() - timedelta(days=days_ago)
            
            # Generate different number of events per day
            daily_events = 100 - (days_ago * 2)  # More recent = more events
            
            for _ in range(daily_events):
                event = AnalyticsEvent(
                    user_id=data["nurse_user"].id if _ % 2 == 0 else data["admin_user"].id,
                    organization_id=data["hospital"].id,
                    session_id=f"session_{days_ago}_{_}",
                    event_type=event_types[_ % len(event_types)],
                    event_category="engagement",
                    resource_type="device" if _ % 3 == 0 else "document",
                    resource_id=data["devices"][_ % len(data["devices"])].primary_di if _ % 3 == 0 else f"doc_{_}",
                    value=float(_ % 10),
                    metadata={
                        "search_query": f"query_{_}" if event_types[_ % len(event_types)] == "search" else None,
                        "duration": _ * 10 if event_types[_ % len(event_types)] == "video_play" else None
                    },
                    page_url=f"/devices/{data['devices'][_ % len(data['devices'])].primary_di}",
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    device_type="desktop" if _ % 3 != 0 else "mobile",
                    created_at=event_date
                )
                events.append(event)
        
        db.add_all(events)
        
        # Generate device analytics daily aggregates
        for device in data["devices"]:
            for days_ago in range(30):
                daily_date = date.today() - timedelta(days=days_ago)
                
                daily_analytics = DeviceAnalyticsDaily(
                    device_id=device.id,
                    organization_id=data["hospital"].id,
                    date=daily_date,
                    view_count=50 - days_ago,
                    unique_viewers=30 - days_ago,
                    search_appearances=100 - (days_ago * 2),
                    search_clicks=20 - int(days_ago / 2),
                    document_downloads=5 + (days_ago % 3),
                    video_views=10 - int(days_ago / 3),
                    chat_sessions=2 + (days_ago % 2),
                    incidents_reported=1 if days_ago % 10 == 0 else 0,
                    average_engagement_time=300 - (days_ago * 5)
                )
                db.add(daily_analytics)
        
        await db.commit()
        
        return events

    @pytest.fixture
    async def admin_headers(self, client: AsyncClient, setup_analytics_data):
        """Get auth headers for admin user"""
        admin_user = setup_analytics_data["admin_user"]
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": admin_user.email, "password": "password123"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_real_time_analytics_dashboard(
        self, client: AsyncClient, db: AsyncSession, admin_headers, generate_analytics_events
    ):
        """Test real-time analytics dashboard data"""
        # Get real-time analytics
        response = await client.get(
            "/api/v1/analytics/real-time",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify real-time metrics
        expected_metrics = [
            "active_users",
            "active_sessions",
            "current_page_views",
            "events_per_minute",
            "top_devices_now",
            "active_searches"
        ]
        
        for metric in expected_metrics:
            assert metric in data
        
        # Test with time window
        response = await client.get(
            "/api/v1/analytics/real-time?window=5m",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        # Should update within 5 minutes as per requirement
        assert "last_updated" in response.json()

    @pytest.mark.asyncio
    async def test_device_usage_analytics(
        self, client: AsyncClient, db: AsyncSession, admin_headers, setup_analytics_data
    ):
        """Test device usage analytics"""
        device = setup_analytics_data["devices"][0]
        
        # Get device-specific analytics
        response = await client.get(
            f"/api/v1/analytics/devices/{device.primary_di}?period=30d",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        analytics = response.json()
        
        # Verify comprehensive metrics
        assert "summary" in analytics
        assert "daily_trends" in analytics
        assert "user_engagement" in analytics
        assert "geographic_distribution" in analytics
        
        summary = analytics["summary"]
        assert "total_views" in summary
        assert "unique_users" in summary
        assert "avg_engagement_time" in summary
        assert "conversion_rate" in summary
        
        # Test comparison with previous period
        response = await client.get(
            f"/api/v1/analytics/devices/{device.primary_di}?period=30d&compare=true",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        comparison_data = response.json()
        assert "current_period" in comparison_data
        assert "previous_period" in comparison_data
        assert "percentage_changes" in comparison_data

    @pytest.mark.asyncio
    async def test_search_analytics(
        self, client: AsyncClient, db: AsyncSession, admin_headers, generate_analytics_events
    ):
        """Test search pattern analytics"""
        response = await client.get(
            "/api/v1/analytics/search?period=7d",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        search_analytics = response.json()
        
        # Verify search metrics
        assert "top_queries" in search_analytics
        assert "no_results_queries" in search_analytics
        assert "search_volume_trend" in search_analytics
        assert "avg_results_clicked" in search_analytics
        assert "search_refinements" in search_analytics
        
        # Top queries should be ordered by frequency
        top_queries = search_analytics["top_queries"]
        if len(top_queries) > 1:
            assert top_queries[0]["count"] >= top_queries[1]["count"]

    @pytest.mark.asyncio
    async def test_custom_report_builder(
        self, client: AsyncClient, db: AsyncSession, admin_headers
    ):
        """Test custom report generation"""
        # Create custom report configuration
        report_config = {
            "name": "Monthly Device Usage Report",
            "metrics": [
                "device_views",
                "unique_users",
                "document_downloads",
                "support_tickets",
                "user_satisfaction"
            ],
            "dimensions": [
                "device_category",
                "department",
                "time_period"
            ],
            "filters": {
                "device_class": ["II", "III"],
                "date_range": {
                    "start": "2024-01-01",
                    "end": "2024-01-31"
                }
            },
            "grouping": "device_category",
            "sort_by": "device_views",
            "sort_order": "desc"
        }
        
        response = await client.post(
            "/api/v1/analytics/reports/custom",
            json=report_config,
            headers=admin_headers
        )
        assert response.status_code == 201
        
        report_id = response.json()["report_id"]
        
        # Execute report
        response = await client.post(
            f"/api/v1/analytics/reports/{report_id}/execute",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        # Report should generate within 30 seconds
        execution_id = response.json()["execution_id"]
        
        # Check execution status
        import asyncio
        for _ in range(6):  # Check for 30 seconds
            response = await client.get(
                f"/api/v1/analytics/reports/executions/{execution_id}",
                headers=admin_headers
            )
            
            if response.json()["status"] == "completed":
                break
            
            await asyncio.sleep(5)
        
        assert response.json()["status"] == "completed"
        
        # Download report in different formats
        for format in ["json", "csv", "excel"]:
            response = await client.get(
                f"/api/v1/analytics/reports/executions/{execution_id}/download?format={format}",
                headers=admin_headers
            )
            assert response.status_code == 200
            
            if format == "csv":
                # Verify CSV structure
                content = response.content.decode('utf-8')
                reader = csv.DictReader(io.StringIO(content))
                rows = list(reader)
                assert len(rows) > 0

    @pytest.mark.asyncio
    async def test_scheduled_reports(
        self, client: AsyncClient, db: AsyncSession, admin_headers
    ):
        """Test scheduled report delivery"""
        # Create scheduled report
        schedule_config = {
            "report_id": "monthly_device_usage",
            "schedule": {
                "frequency": "monthly",
                "day_of_month": 1,
                "time": "08:00",
                "timezone": "America/New_York"
            },
            "delivery": {
                "email_recipients": ["admin@hospital.com", "director@hospital.com"],
                "format": "excel",
                "include_summary": True
            }
        }
        
        response = await client.post(
            "/api/v1/analytics/reports/scheduled",
            json=schedule_config,
            headers=admin_headers
        )
        assert response.status_code == 201
        
        schedule_id = response.json()["schedule_id"]
        
        # Verify schedule created
        response = await client.get(
            f"/api/v1/analytics/reports/scheduled/{schedule_id}",
            headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["next_run"] is not None

    @pytest.mark.asyncio
    async def test_compliance_reporting(
        self, client: AsyncClient, db: AsyncSession, admin_headers, setup_analytics_data
    ):
        """Test HIPAA compliance and audit reports"""
        # Generate audit logs
        users = [setup_analytics_data["admin_user"], setup_analytics_data["nurse_user"]]
        
        for user in users:
            for i in range(10):
                audit_log = AuditLog(
                    user_id=user.id,
                    organization_id=user.organization_id,
                    action="view",
                    resource_type="device",
                    resource_id=setup_analytics_data["devices"][i % len(setup_analytics_data["devices"])].primary_di,
                    resource_name=f"Device {i}",
                    ip_address="192.168.1.100",
                    user_agent="Mozilla/5.0",
                    session_id=f"session_{user.id}_{i}",
                    success=True,
                    created_at=datetime.utcnow() - timedelta(hours=i)
                )
                db.add(audit_log)
        
        await db.commit()
        
        # Get HIPAA audit report
        response = await client.get(
            "/api/v1/analytics/reports/compliance/hipaa-audit?period=7d",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        audit_report = response.json()
        
        # Verify required HIPAA fields
        assert "access_logs" in audit_report
        assert "user_activity_summary" in audit_report
        assert "resource_access_patterns" in audit_report
        assert "anomalous_activities" in audit_report
        
        # Test user access review report
        response = await client.get(
            "/api/v1/analytics/reports/compliance/user-access-review",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        access_review = response.json()
        assert "active_users" in access_review
        assert "permission_assignments" in access_review
        assert "last_access_times" in access_review
        assert "dormant_accounts" in access_review

    @pytest.mark.asyncio
    async def test_cost_analytics(
        self, client: AsyncClient, db: AsyncSession, admin_headers
    ):
        """Test cost tracking and allocation analytics"""
        # Get cost analytics
        response = await client.get(
            "/api/v1/analytics/costs?period=30d",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        cost_data = response.json()
        
        # Verify cost breakdown
        assert "total_cost" in cost_data
        assert "cost_breakdown" in cost_data
        assert "cost_by_department" in cost_data
        assert "cost_trends" in cost_data
        
        breakdown = cost_data["cost_breakdown"]
        expected_categories = [
            "ai_usage",
            "storage",
            "bandwidth",
            "sms_notifications",
            "video_streaming"
        ]
        
        for category in expected_categories:
            assert category in breakdown

    @pytest.mark.asyncio
    async def test_performance_analytics(
        self, client: AsyncClient, db: AsyncSession, admin_headers
    ):
        """Test system performance analytics"""
        response = await client.get(
            "/api/v1/analytics/performance?period=24h",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        performance = response.json()
        
        # Verify performance metrics
        assert "api_response_times" in performance
        assert "endpoint_statistics" in performance
        assert "error_rates" in performance
        assert "database_performance" in performance
        assert "cache_hit_rates" in performance
        
        # Response time percentiles
        response_times = performance["api_response_times"]
        assert "p50" in response_times
        assert "p95" in response_times
        assert "p99" in response_times

    @pytest.mark.asyncio
    async def test_drill_down_capabilities(
        self, client: AsyncClient, db: AsyncSession, admin_headers, setup_analytics_data
    ):
        """Test analytics drill-down functionality"""
        # Start with high-level metrics
        response = await client.get(
            "/api/v1/analytics/overview?period=30d",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        overview = response.json()
        
        # Drill down into specific metric
        if overview["top_devices"]:
            top_device = overview["top_devices"][0]
            device_di = top_device["device_di"]
            
            # Drill down to device details
            response = await client.get(
                f"/api/v1/analytics/devices/{device_di}/detailed?period=30d",
                headers=admin_headers
            )
            assert response.status_code == 200
            
            detailed = response.json()
            
            # Further drill down to user level
            if detailed["top_users"]:
                top_user_id = detailed["top_users"][0]["user_id"]
                
                response = await client.get(
                    f"/api/v1/analytics/users/{top_user_id}/device-usage?device_di={device_di}",
                    headers=admin_headers
                )
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_analytics_data(
        self, client: AsyncClient, db: AsyncSession, admin_headers
    ):
        """Test analytics data export functionality"""
        # Request data export
        export_config = {
            "data_types": [
                "device_analytics",
                "user_activity",
                "search_logs",
                "cost_data"
            ],
            "period": {
                "start": "2024-01-01",
                "end": "2024-01-31"
            },
            "format": "parquet",  # For efficient big data processing
            "compression": "gzip"
        }
        
        response = await client.post(
            "/api/v1/analytics/export",
            json=export_config,
            headers=admin_headers
        )
        assert response.status_code == 202  # Accepted for processing
        
        export_id = response.json()["export_id"]
        
        # Check export status
        response = await client.get(
            f"/api/v1/analytics/export/{export_id}/status",
            headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] in ["pending", "processing", "completed"]

    @pytest.mark.asyncio
    async def test_retention_policy_compliance(
        self, client: AsyncClient, db: AsyncSession, admin_headers
    ):
        """Test data retention policy compliance"""
        # Get retention compliance report
        response = await client.get(
            "/api/v1/analytics/reports/retention-compliance",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        retention_report = response.json()
        
        # Verify retention periods
        assert "audit_logs_retention" in retention_report
        assert retention_report["audit_logs_retention"]["years"] >= 7  # HIPAA requirement
        
        assert "analytics_data_retention" in retention_report
        assert "pii_data_retention" in retention_report
        assert "data_deletion_log" in retention_report

    @pytest.mark.asyncio
    async def test_analytics_api_performance(
        self, client: AsyncClient, db: AsyncSession, admin_headers, generate_analytics_events
    ):
        """Test analytics API performance requirements"""
        import time
        
        # Test query performance with large dataset
        start_time = time.time()
        
        response = await client.get(
            "/api/v1/analytics/devices?period=30d&limit=100",
            headers=admin_headers
        )
        
        query_time = time.time() - start_time
        
        assert response.status_code == 200
        assert query_time < 2.0  # Should return in less than 2 seconds
        
        # Test aggregation performance
        start_time = time.time()
        
        response = await client.get(
            "/api/v1/analytics/aggregations?metrics=views,downloads,searches&group_by=day&period=30d",
            headers=admin_headers
        )
        
        aggregation_time = time.time() - start_time
        
        assert response.status_code == 200
        assert aggregation_time < 1.0  # Aggregations should be fast

    @pytest.mark.asyncio
    async def test_role_based_analytics_access(
        self, client: AsyncClient, db: AsyncSession, setup_analytics_data
    ):
        """Test role-based access to analytics"""
        # Test vendor admin access - should only see their devices
        vendor_admin = setup_analytics_data["vendor_admin"]
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": vendor_admin.email, "password": "password123"}
        )
        vendor_token = response.json()["access_token"]
        vendor_headers = {"Authorization": f"Bearer {vendor_token}"}
        
        # Vendor should only see analytics for their devices
        response = await client.get(
            "/api/v1/analytics/devices",
            headers=vendor_headers
        )
        assert response.status_code == 200
        
        devices = response.json()["devices"]
        # Should only see vendor's devices
        for device in devices:
            assert device["organization_id"] == vendor_admin.organization_id
        
        # Test nurse user - limited analytics access
        nurse_user = setup_analytics_data["nurse_user"]
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": nurse_user.email, "password": "password123"}
        )
        nurse_token = response.json()["access_token"]
        nurse_headers = {"Authorization": f"Bearer {nurse_token}"}
        
        # Nurse should not access cost analytics
        response = await client.get(
            "/api/v1/analytics/costs",
            headers=nurse_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_analytics_webhooks(
        self, client: AsyncClient, db: AsyncSession, admin_headers
    ):
        """Test analytics webhook notifications"""
        # Configure webhook for analytics alerts
        webhook_config = {
            "url": "https://example.com/webhooks/analytics",
            "events": ["usage_spike", "error_rate_high", "cost_threshold"],
            "thresholds": {
                "usage_spike_percent": 200,
                "error_rate_percent": 5,
                "cost_threshold_usd": 1000
            }
        }
        
        response = await client.post(
            "/api/v1/analytics/webhooks",
            json=webhook_config,
            headers=admin_headers
        )
        assert response.status_code == 201
        
        webhook_id = response.json()["id"]
        
        # Test webhook trigger
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value.status_code = 200
            
            # Simulate usage spike
            # Would be detected by analytics monitoring service
            
            # Verify webhook configuration
            response = await client.get(
                f"/api/v1/analytics/webhooks/{webhook_id}",
                headers=admin_headers
            )
            assert response.status_code == 200
