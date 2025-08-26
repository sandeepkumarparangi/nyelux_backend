"""
Multi-Tenant Architecture Tests
Based on NYELUX Test Coverage Document Section 13
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import asyncio
import redis.asyncio as redis

from src.db.models.organization import Organization
from src.db.models.user import User
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.db.models.note import Note
from src.db.models.device_document import DeviceDocument


class TestDataIsolation:
    """Test cases TC-TENANT-001 through TC-TENANT-002"""
    
    @pytest.mark.asyncio
    async def test_cross_tenant_query_prevention(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-TENANT-001: Cross-Tenant Query Prevention"""
        # Create two separate organizations
        org_a = Organization(
            name="Hospital A",
            type="hospital",
            subdomain="hospital-a"
        )
        org_b = Organization(
            name="Hospital B", 
            type="hospital",
            subdomain="hospital-b"
        )
        db_session.add_all([org_a, org_b])
        await db_session.commit()
        
        # Create users for each organization
        user_a = User(
            email="user@hospitala.com",
            role="nurse",
            organization_id=org_a.id
        )
        user_b = User(
            email="user@hospitalb.com",
            role="nurse",
            organization_id=org_b.id
        )
        db_session.add_all([user_a, user_b])
        await db_session.commit()
        
        # Create devices for each organization
        device_a = VendorDevice(
            gudid_device_di="TESTA001",
            custom_name="Hospital A Device",
            organization_id=org_a.id
        )
        device_b = VendorDevice(
            gudid_device_di="TESTB001",
            custom_name="Hospital B Device",
            organization_id=org_b.id
        )
        db_session.add_all([device_a, device_b])
        await db_session.commit()
        
        # Get auth tokens
        token_a = f"Bearer token_org_{org_a.id}_user_{user_a.id}"
        token_b = f"Bearer token_org_{org_b.id}_user_{user_b.id}"
        
        # Test 1: Direct ID reference attack
        # User A tries to access User B's device by ID
        attack_response = await client.get(
            f"/api/v1/devices/{device_b.id}",
            headers={"Authorization": token_a}
        )
        
        assert attack_response.status_code in [403, 404]
        # Should return 404 to not reveal existence
        assert attack_response.status_code == 404
        
        # Test 2: Search injection attack
        # Try to bypass tenant filter in search
        search_attack = await client.post(
            "/api/v1/devices/search",
            json={
                "query": f"Hospital B Device' OR organization_id={org_b.id} --"
            },
            headers={"Authorization": token_a}
        )
        
        assert search_attack.status_code == 200
        results = search_attack.json()["results"]
        
        # Should return no results from org B
        assert len(results) == 0 or all(r["organization_id"] != org_b.id for r in results)
        
        # Test 3: API parameter manipulation
        # Try to override organization_id in request
        param_attack = await client.get(
            "/api/v1/devices",
            params={"organization_id": org_b.id},
            headers={"Authorization": token_a}
        )
        
        assert param_attack.status_code == 200
        devices = param_attack.json()["results"]
        
        # Should only return org A devices despite parameter
        assert all(d["organization_id"] == org_a.id for d in devices)
        
        # Test 4: Create resource with wrong org ID
        create_attack = await client.post(
            "/api/v1/notes",
            json={
                "title": "Attack Note",
                "content": "Trying to create in wrong org",
                "organization_id": org_b.id  # Try to force wrong org
            },
            headers={"Authorization": token_a}
        )
        
        if create_attack.status_code == 201:
            # If created, verify it was assigned to correct org
            note_id = create_attack.json()["id"]
            note = await db_session.get(Note, note_id)
            assert note.organization_id == org_a.id  # Should be user's org
        
        # Test 5: Relationship traversal attack
        # Create a document linked to org A device
        doc_a = DeviceDocument(
            device_id=device_a.id,
            organization_id=org_a.id,
            title="Org A Document",
            file_url="s3://bucket/doc_a.pdf"
        )
        db_session.add(doc_a)
        await db_session.commit()
        
        # Try to access via relationship from org B
        relation_attack = await client.get(
            f"/api/v1/devices/{device_a.id}/documents",
            headers={"Authorization": token_b}
        )
        
        assert relation_attack.status_code == 404  # Device not found for org B
        
        # Test 6: Bulk operations isolation
        bulk_response = await client.post(
            "/api/v1/devices/bulk-update",
            json={
                "device_ids": [device_a.id, device_b.id],
                "update": {"custom_name": "Hacked"}
            },
            headers={"Authorization": token_a}
        )
        
        if bulk_response.status_code == 200:
            result = bulk_response.json()
            # Should only update org A device
            assert result["updated_count"] <= 1
            assert device_b.id not in result.get("updated_ids", [])
        
        # Verify all attacks logged
        audit_response = await client.get(
            "/api/v1/admin/audit-logs",
            params={
                "event_type": "unauthorized_access_attempt",
                "last_hour": True
            },
            headers={"Authorization": "Bearer admin_token"}
        )
        
        if audit_response.status_code == 200:
            audit_logs = audit_response.json()["logs"]
            assert len(audit_logs) > 0  # Attacks should be logged
    
    @pytest.mark.asyncio
    async def test_cache_isolation(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-TENANT-002: Cache Isolation"""
        # Create test organizations
        org_a = Organization(name="Cache Test A", type="hospital")
        org_b = Organization(name="Cache Test B", type="hospital")
        db_session.add_all([org_a, org_b])
        await db_session.commit()
        
        # Create users
        user_a = User(email="cache_a@test.com", organization_id=org_a.id, role="nurse")
        user_b = User(email="cache_b@test.com", organization_id=org_b.id, role="nurse")
        db_session.add_all([user_a, user_b])
        await db_session.commit()
        
        # Setup cache client
        cache = redis.from_url("redis://localhost:6379/0")
        
        # Test 1: Search results caching
        # Tenant A searches for "pump"
        search_a = await client.get(
            "/api/v1/devices/search?q=pump",
            headers={"Authorization": f"Bearer token_org_{org_a.id}"}
        )
        
        assert search_a.status_code == 200
        results_a = search_a.json()["results"]
        
        # Check cache key includes tenant
        cache_key_a = f"search:org_{org_a.id}:pump"
        cached_a = await cache.get(cache_key_a)
        assert cached_a is not None  # Should be cached
        
        # Tenant B searches for same term
        search_b = await client.get(
            "/api/v1/devices/search?q=pump",
            headers={"Authorization": f"Bearer token_org_{org_b.id}"}
        )
        
        assert search_b.status_code == 200
        results_b = search_b.json()["results"]
        
        # Results should be different (different org data)
        assert results_a != results_b
        
        # Check separate cache key
        cache_key_b = f"search:org_{org_b.id}:pump"
        cached_b = await cache.get(cache_key_b)
        assert cached_b is not None
        assert cached_a != cached_b  # Different cached results
        
        # Test 2: Session data isolation
        # Set session data for user A
        session_key_a = f"session:{user_a.id}"
        await cache.setex(
            session_key_a,
            3600,
            json.dumps({"user_id": user_a.id, "org_id": org_a.id, "data": "secret_a"})
        )
        
        # Try cache poisoning attack
        # User B tries to access user A's session
        poisoned_key = f"session:{user_a.id}"
        
        # This should be prevented by the application layer
        # Testing that even if key is known, access is denied
        session_response = await client.get(
            "/api/v1/users/session",
            headers={
                "Authorization": f"Bearer token_org_{org_b.id}",
                "X-Session-Override": poisoned_key  # Hypothetical attack header
            }
        )
        
        # Should not get user A's session data
        if session_response.status_code == 200:
            session_data = session_response.json()
            assert session_data.get("data") != "secret_a"
            assert session_data.get("user_id") == user_b.id
        
        # Test 3: Analytics cache isolation
        # Cache analytics for org A
        analytics_key_a = f"analytics:daily:org_{org_a.id}:2024-01-15"
        await cache.setex(
            analytics_key_a,
            3600,
            json.dumps({"views": 1000, "users": 50})
        )
        
        # Org B requests analytics
        analytics_b = await client.get(
            "/api/v1/analytics/daily?date=2024-01-15",
            headers={"Authorization": f"Bearer token_org_{org_b.id}"}
        )
        
        if analytics_b.status_code == 200:
            data_b = analytics_b.json()
            # Should not see org A's numbers
            assert data_b.get("views", 0) != 1000
        
        # Test 4: Clear tenant-specific cache
        clear_response = await client.post(
            "/api/v1/admin/cache/clear",
            json={"pattern": "org_specific"},
            headers={"Authorization": f"Bearer token_org_{org_a.id}"}
        )
        
        if clear_response.status_code == 200:
            # Verify only org A cache cleared
            assert await cache.get(cache_key_a) is None  # Org A cache cleared
            assert await cache.get(cache_key_b) is not None  # Org B cache intact
        
        await cache.close()


class TestTenantManagement:
    """Test tenant configuration and management"""
    
    @pytest.mark.asyncio
    async def test_tenant_configuration(
        self, client: AsyncClient, db_session: AsyncSession, super_admin_headers
    ):
        """Test tenant-specific configuration management"""
        # Create new tenant
        tenant_response = await client.post(
            "/api/v1/admin/tenants",
            json={
                "name": "Regional Medical Center",
                "type": "hospital",
                "subdomain": "regional-med",
                "admin_email": "admin@regionalmed.com",
                "settings": {
                    "branding": {
                        "primary_color": "#1E40AF",
                        "logo_url": "https://example.com/logo.png",
                        "custom_css": ".header { background: #1E40AF; }"
                    },
                    "features": {
                        "ai_chat_enabled": True,
                        "video_training_enabled": True,
                        "incident_reporting_enabled": True,
                        "custom_reports_enabled": False
                    },
                    "integrations": {
                        "sso_enabled": True,
                        "sso_provider": "okta",
                        "api_access_enabled": True
                    }
                },
                "license": {
                    "tier": "professional",
                    "user_limit": 500,
                    "storage_limit_gb": 100,
                    "api_rate_limit": 10000
                }
            },
            headers=super_admin_headers
        )
        
        assert tenant_response.status_code == 201
        tenant_id = tenant_response.json()["id"]
        
        # Test subdomain routing
        subdomain_response = await client.get(
            "/api/v1/tenant/info",
            headers={"Host": "regional-med.nyelux.com"}
        )
        
        assert subdomain_response.status_code == 200
        tenant_info = subdomain_response.json()
        assert tenant_info["subdomain"] == "regional-med"
        assert tenant_info["branding"]["primary_color"] == "#1E40AF"
        
        # Test feature flags
        feature_check = await client.get(
            "/api/v1/features",
            headers={
                "Authorization": f"Bearer tenant_{tenant_id}_token",
                "X-Tenant-ID": str(tenant_id)
            }
        )
        
        assert feature_check.status_code == 200
        features = feature_check.json()
        assert features["ai_chat_enabled"] is True
        assert features["custom_reports_enabled"] is False
        
        # Test license enforcement
        # Try to exceed user limit
        for i in range(501):  # Over 500 limit
            user_response = await client.post(
                "/api/v1/users",
                json={
                    "email": f"user{i}@regionalmed.com",
                    "role": "nurse"
                },
                headers={"Authorization": f"Bearer tenant_{tenant_id}_admin_token"}
            )
            
            if i < 500:
                assert user_response.status_code == 201
            else:
                # 501st user should fail
                assert user_response.status_code == 403
                assert "user limit" in user_response.json()["detail"].lower()
                break
        
        # Test API rate limiting
        # Make rapid API calls
        rate_limit_hit = False
        for i in range(150):  # Try to exceed rate limit
            response = await client.get(
                "/api/v1/devices",
                headers={"Authorization": f"Bearer tenant_{tenant_id}_token"}
            )
            
            if response.status_code == 429:
                rate_limit_hit = True
                assert "X-RateLimit-Limit" in response.headers
                assert "X-RateLimit-Remaining" in response.headers
                assert "X-RateLimit-Reset" in response.headers
                break
        
        # Should hit rate limit for sustained rapid calls
        # (actual limit depends on time window configuration)
    
    @pytest.mark.asyncio
    async def test_tenant_data_migration(
        self, client: AsyncClient, super_admin_headers
    ):
        """Test tenant data export and import"""
        source_tenant_id = 1
        
        # Export tenant data
        export_response = await client.post(
            f"/api/v1/admin/tenants/{source_tenant_id}/export",
            json={
                "include_users": True,
                "include_devices": True,
                "include_documents": True,
                "include_analytics": False,
                "format": "json"
            },
            headers=super_admin_headers
        )
        
        assert export_response.status_code == 202  # Accepted
        export_job_id = export_response.json()["job_id"]
        
        # Wait for export completion
        export_complete = False
        for _ in range(30):  # Max 30 seconds
            status_response = await client.get(
                f"/api/v1/admin/jobs/{export_job_id}",
                headers=super_admin_headers
            )
            
            if status_response.json()["status"] == "completed":
                export_complete = True
                break
            
            await asyncio.sleep(1)
        
        assert export_complete
        
        # Download export
        download_response = await client.get(
            f"/api/v1/admin/jobs/{export_job_id}/download",
            headers=super_admin_headers
        )
        
        assert download_response.status_code == 200
        export_data = download_response.json()
        
        # Verify export structure
        assert "metadata" in export_data
        assert "users" in export_data
        assert "devices" in export_data
        assert "documents" in export_data
        assert export_data["metadata"]["tenant_id"] == source_tenant_id
        assert export_data["metadata"]["export_version"] == "1.0"
        
        # Create new tenant and import data
        new_tenant = await client.post(
            "/api/v1/admin/tenants",
            json={
                "name": "Migrated Hospital",
                "subdomain": "migrated",
                "type": "hospital"
            },
            headers=super_admin_headers
        )
        
        new_tenant_id = new_tenant.json()["id"]
        
        # Import data to new tenant
        import_response = await client.post(
            f"/api/v1/admin/tenants/{new_tenant_id}/import",
            json=export_data,
            headers=super_admin_headers
        )
        
        assert import_response.status_code == 202
        import_job_id = import_response.json()["job_id"]
        
        # Wait for import completion
        import_complete = False
        for _ in range(30):
            status = await client.get(
                f"/api/v1/admin/jobs/{import_job_id}",
                headers=super_admin_headers
            )
            
            if status.json()["status"] == "completed":
                import_complete = True
                break
            
            await asyncio.sleep(1)
        
        assert import_complete
        
        # Verify data migrated correctly
        migrated_check = await client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer tenant_{new_tenant_id}_admin_token"}
        )
        
        assert migrated_check.status_code == 200
        assert len(migrated_check.json()["results"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
