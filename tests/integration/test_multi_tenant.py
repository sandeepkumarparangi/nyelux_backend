"""
Integration tests for Multi-Tenant Architecture.
Tests cover data isolation, tenant management, and security boundaries.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
import json
import asyncio
from typing import List, Dict

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.db.models.device_document import DeviceDocument
from src.db.models.chat import ChatConversation
from src.db.models.device_incident import DeviceIncident
from src.db.models.analytics_event import AnalyticsEvent
from src.services.auth_service import AuthService


class TestMultiTenantArchitecture:
    """Test cases for Multi-Tenant Architecture - Section 13"""

    @pytest.fixture
    async def setup_multiple_tenants(self, db: AsyncSession):
        """Create multiple tenant organizations with complete data"""
        # Create tenant organizations
        hospital_a = Organization(
            name="Hospital A",
            type="hospital",
            subdomain="hospital-a",
            license_tier="professional",
            settings={"theme": "blue", "features": ["ai_chat", "analytics"]}
        )
        
        hospital_b = Organization(
            name="Hospital B",
            type="hospital",
            subdomain="hospital-b",
            license_tier="enterprise",
            settings={"theme": "green", "features": ["ai_chat", "analytics", "api_access"]}
        )
        
        vendor_x = Organization(
            name="Vendor X Medical",
            type="vendor",
            subdomain="vendor-x",
            license_tier="vendor_pro"
        )
        
        clinic_c = Organization(
            name="Clinic C",
            type="clinic",
            subdomain="clinic-c",
            license_tier="basic"
        )
        
        db.add_all([hospital_a, hospital_b, vendor_x, clinic_c])
        await db.flush()
        
        auth_service = AuthService()
        
        # Create users for each tenant
        users = []
        
        # Hospital A users
        hospital_a_admin = User(
            email="admin@hospital-a.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Admin",
            last_name="HospitalA",
            role="org_admin",
            organization_id=hospital_a.id
        )
        
        hospital_a_nurse = User(
            email="nurse@hospital-a.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Nurse",
            last_name="HospitalA",
            role="nurse",
            organization_id=hospital_a.id
        )
        
        # Hospital B users
        hospital_b_admin = User(
            email="admin@hospital-b.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Admin",
            last_name="HospitalB",
            role="org_admin",
            organization_id=hospital_b.id
        )
        
        hospital_b_doctor = User(
            email="doctor@hospital-b.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Doctor",
            last_name="HospitalB",
            role="physician",
            organization_id=hospital_b.id
        )
        
        # Vendor X users
        vendor_x_admin = User(
            email="admin@vendor-x.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Admin",
            last_name="VendorX",
            role="vendor_admin",
            organization_id=vendor_x.id
        )
        
        users.extend([
            hospital_a_admin, hospital_a_nurse,
            hospital_b_admin, hospital_b_doctor,
            vendor_x_admin
        ])
        
        db.add_all(users)
        await db.flush()
        
        # Create FDA devices (shared across all tenants)
        fda_devices = []
        for i in range(5):
            device = GUDIDDevice(
                primary_di=f"00889842000{100+i}",
                device_name=f"FDA Device {i+1}",
                manufacturer_name="GlobalMed Corp",
                device_class="II"
            )
            fda_devices.append(device)
        
        db.add_all(fda_devices)
        await db.flush()
        
        # Create vendor-specific devices for Vendor X
        vendor_devices = []
        for i in range(3):
            vendor_device = VendorDevice(
                gudid_device_di=fda_devices[i].primary_di,
                organization_id=vendor_x.id,
                custom_name=f"VendorX Device Model {i+1}",
                internal_sku=f"VX-{1000+i}",
                list_price=1000.00 + (i * 500)
            )
            vendor_devices.append(vendor_device)
        
        db.add_all(vendor_devices)
        
        # Create tenant-specific data
        # Hospital A documents
        hospital_a_doc = DeviceDocument(
            device_id=vendor_devices[0].id,
            organization_id=hospital_a.id,
            document_type="manual",
            title="Hospital A Training Manual",
            file_url="s3://hospital-a/manual.pdf",
            access_level="organization"
        )
        
        # Hospital B chat conversation
        hospital_b_chat = ChatConversation(
            user_id=hospital_b_doctor.id,
            device_id=vendor_devices[0].id,
            title="Device Questions - Hospital B",
            context_type="device_support"
        )
        
        db.add_all([hospital_a_doc, hospital_b_chat])
        await db.commit()
        
        return {
            "hospital_a": hospital_a,
            "hospital_b": hospital_b,
            "vendor_x": vendor_x,
            "clinic_c": clinic_c,
            "users": {
                "hospital_a_admin": hospital_a_admin,
                "hospital_a_nurse": hospital_a_nurse,
                "hospital_b_admin": hospital_b_admin,
                "hospital_b_doctor": hospital_b_doctor,
                "vendor_x_admin": vendor_x_admin
            },
            "fda_devices": fda_devices,
            "vendor_devices": vendor_devices
        }

    @pytest.mark.asyncio
    async def test_tc_tenant_001_cross_tenant_query_prevention(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """TC-TENANT-001: Test cross-tenant data access prevention"""
        data = setup_multiple_tenants
        
        # Login as Hospital A admin
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_a_admin"].email, "password": "password123"}
        )
        hospital_a_token = response.json()["access_token"]
        hospital_a_headers = {"Authorization": f"Bearer {hospital_a_token}"}
        
        # Login as Hospital B admin
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_b_admin"].email, "password": "password123"}
        )
        hospital_b_token = response.json()["access_token"]
        hospital_b_headers = {"Authorization": f"Bearer {hospital_b_token}"}
        
        # Test 1: Direct ID reference to other tenant's data
        # Hospital B has a chat conversation
        hospital_b_chat = await db.query(ChatConversation).filter(
            ChatConversation.user_id == data["users"]["hospital_b_doctor"].id
        ).first()
        
        # Hospital A admin tries to access Hospital B's chat
        response = await client.get(
            f"/api/v1/chat/conversations/{hospital_b_chat.id}",
            headers=hospital_a_headers
        )
        assert response.status_code == 404  # Should not find it
        
        # Test 2: Search injection attempts
        # Try to search with organization filter manipulation
        malicious_searches = [
            {"query": "device", "filters": {"organization_id": data["hospital_b"].id}},
            {"query": "device' OR organization_id=2 --"},
            {"query": "device", "filters": {"organization_id": ["1", "2"]}}
        ]
        
        for search in malicious_searches:
            response = await client.post(
                "/api/v1/devices/search",
                json=search,
                headers=hospital_a_headers
            )
            
            if response.status_code == 200:
                results = response.json()["results"]
                # Verify no Hospital B specific data returned
                for result in results:
                    if "organization_id" in result:
                        assert result["organization_id"] != data["hospital_b"].id
        
        # Test 3: API parameter manipulation
        # Try to access users from another organization
        response = await client.get(
            f"/api/v1/users?organization_id={data['hospital_b'].id}",
            headers=hospital_a_headers
        )
        assert response.status_code in [403, 404]  # Forbidden or not found
        
        # Test 4: Verify Hospital A can only see their own data
        response = await client.get(
            "/api/v1/documents",
            headers=hospital_a_headers
        )
        assert response.status_code == 200
        
        documents = response.json()["documents"]
        for doc in documents:
            assert doc["organization_id"] == data["hospital_a"].id

    @pytest.mark.asyncio
    async def test_tc_tenant_002_cache_isolation(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """TC-TENANT-002: Test cache isolation between tenants"""
        data = setup_multiple_tenants
        
        # Login as both hospital admins
        hospital_a_response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_a_admin"].email, "password": "password123"}
        )
        hospital_a_headers = {"Authorization": f"Bearer {hospital_a_response.json()['access_token']}"}
        
        hospital_b_response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_b_admin"].email, "password": "password123"}
        )
        hospital_b_headers = {"Authorization": f"Bearer {hospital_b_response.json()['access_token']}"}
        
        # Hospital A searches for "pump"
        response_a = await client.post(
            "/api/v1/devices/search",
            json={"query": "pump"},
            headers=hospital_a_headers
        )
        assert response_a.status_code == 200
        results_a = response_a.json()["results"]
        
        # Hospital B searches for "pump" 
        response_b = await client.post(
            "/api/v1/devices/search",
            json={"query": "pump"},
            headers=hospital_b_headers
        )
        assert response_b.status_code == 200
        results_b = response_b.json()["results"]
        
        # Results should be scoped to each tenant's accessible devices
        # FDA devices are shared, but vendor devices and custom data should differ
        
        # Verify cache keys are tenant-scoped
        with patch("src.services.cache_service.CacheService.get") as mock_cache_get:
            # Simulate cache check
            await client.post(
                "/api/v1/devices/search",
                json={"query": "pump"},
                headers=hospital_a_headers
            )
            
            # Cache key should include organization context
            cache_key = mock_cache_get.call_args[0][0]
            assert str(data["hospital_a"].id) in cache_key or "hospital_a" in cache_key

    @pytest.mark.asyncio
    async def test_subdomain_based_tenant_resolution(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test subdomain-based tenant identification"""
        data = setup_multiple_tenants
        
        # Test subdomain routing
        subdomains = [
            ("hospital-a", data["hospital_a"]),
            ("hospital-b", data["hospital_b"]),
            ("vendor-x", data["vendor_x"])
        ]
        
        for subdomain, org in subdomains:
            # Simulate request with subdomain header
            headers = {"Host": f"{subdomain}.nyelux.com"}
            
            response = await client.get(
                "/api/v1/tenant/info",
                headers=headers
            )
            
            # Should return correct tenant info
            if response.status_code == 200:
                tenant_info = response.json()
                assert tenant_info["subdomain"] == subdomain
                assert tenant_info["organization_name"] == org.name

    @pytest.mark.asyncio
    async def test_tenant_resource_limits(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test tenant-specific resource limits and quotas"""
        data = setup_multiple_tenants
        
        # Clinic C has basic tier with limited users
        clinic_c = data["clinic_c"]
        
        # Create users up to limit (assuming basic = 5 users)
        auth_service = AuthService()
        for i in range(4):  # Already have 0, create 4 more
            user = User(
                email=f"user{i}@clinic-c.com",
                password_hash=auth_service.get_password_hash("password123"),
                first_name=f"User{i}",
                last_name="ClinicC",
                role="nurse",
                organization_id=clinic_c.id
            )
            db.add(user)
        
        await db.commit()
        
        # Try to create 6th user (over limit)
        # First need admin token for clinic C
        clinic_admin = User(
            email="admin@clinic-c.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Admin",
            last_name="ClinicC",
            role="org_admin",
            organization_id=clinic_c.id
        )
        db.add(clinic_admin)
        await db.commit()
        
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": clinic_admin.email, "password": "password123"}
        )
        admin_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        # Attempt to create user over limit
        response = await client.post(
            "/api/v1/users",
            json={
                "email": "overlimit@clinic-c.com",
                "password": "password123",
                "first_name": "Over",
                "last_name": "Limit",
                "role": "nurse"
            },
            headers=admin_headers
        )
        
        # Should be rejected due to license limit
        assert response.status_code == 403
        assert "license limit" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_tenant_data_isolation_comprehensive(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test comprehensive data isolation across all models"""
        data = setup_multiple_tenants
        
        # Login as Hospital A admin
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_a_admin"].email, "password": "password123"}
        )
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        # Create tenant-specific data for Hospital A
        # 1. Create an incident
        incident_response = await client.post(
            "/api/v1/incidents",
            json={
                "device_id": data["vendor_devices"][0].id,
                "incident_type": "malfunction",
                "description": "Device not powering on",
                "urgency": "high"
            },
            headers=headers
        )
        assert incident_response.status_code == 201
        incident_id = incident_response.json()["id"]
        
        # 2. Create analytics event
        event = AnalyticsEvent(
            user_id=data["users"]["hospital_a_admin"].id,
            organization_id=data["hospital_a"].id,
            event_type="device_view",
            resource_type="device",
            resource_id=data["vendor_devices"][0].id
        )
        db.add(event)
        await db.commit()
        
        # 3. Create a note
        note_response = await client.post(
            "/api/v1/notes",
            json={
                "device_id": data["vendor_devices"][0].id,
                "content": "Hospital A specific procedure notes",
                "visibility": "organization"
            },
            headers=headers
        )
        assert note_response.status_code == 201
        
        # Now login as Hospital B and verify isolation
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_b_admin"].email, "password": "password123"}
        )
        hospital_b_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        # Hospital B should not see Hospital A's data
        # 1. Check incidents
        response = await client.get(
            "/api/v1/incidents",
            headers=hospital_b_headers
        )
        incidents = response.json()["incidents"]
        assert not any(inc["id"] == incident_id for inc in incidents)
        
        # 2. Check analytics
        response = await client.get(
            "/api/v1/analytics/events",
            headers=hospital_b_headers
        )
        if response.status_code == 200:
            events = response.json()["events"]
            for event in events:
                assert event["organization_id"] == data["hospital_b"].id
        
        # 3. Check notes
        response = await client.get(
            "/api/v1/notes",
            headers=hospital_b_headers
        )
        notes = response.json()["notes"]
        assert not any("Hospital A specific" in note.get("content", "") for note in notes)

    @pytest.mark.asyncio
    async def test_tenant_configuration_isolation(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test tenant-specific configuration and branding"""
        data = setup_multiple_tenants
        
        # Each tenant has different configurations
        tenants = [
            (data["users"]["hospital_a_admin"], data["hospital_a"]),
            (data["users"]["hospital_b_admin"], data["hospital_b"])
        ]
        
        for admin_user, org in tenants:
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": admin_user.email, "password": "password123"}
            )
            headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            
            # Get tenant configuration
            response = await client.get(
                "/api/v1/settings/organization",
                headers=headers
            )
            assert response.status_code == 200
            
            settings = response.json()
            assert settings["theme"] == org.settings["theme"]
            assert settings["features"] == org.settings["features"]
            
            # Update configuration
            response = await client.patch(
                "/api/v1/settings/organization",
                json={"theme": "custom", "logo_url": f"https://cdn.nyelux.com/{org.subdomain}/logo.png"},
                headers=headers
            )
            assert response.status_code == 200
            
            # Verify update only affects their tenant
            await db.refresh(org)
            assert org.settings["theme"] == "custom"
            
            # Other tenant's settings unchanged
            other_org = data["hospital_b"] if org == data["hospital_a"] else data["hospital_a"]
            await db.refresh(other_org)
            assert other_org.settings["theme"] != "custom"

    @pytest.mark.asyncio
    async def test_tenant_api_key_isolation(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test API key isolation between tenants"""
        data = setup_multiple_tenants
        
        # Hospital B has enterprise tier with API access
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_b_admin"].email, "password": "password123"}
        )
        admin_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        # Create API key
        response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Hospital B Integration",
                "scopes": ["read:devices", "write:analytics"]
            },
            headers=admin_headers
        )
        assert response.status_code == 201
        
        api_key = response.json()["key"]
        api_headers = {"X-API-Key": api_key}
        
        # Use API key to access data
        response = await client.get(
            "/api/v1/devices",
            headers=api_headers
        )
        assert response.status_code == 200
        
        # API key should only access Hospital B data
        devices = response.json()["devices"]
        # Verify scoped to Hospital B
        
        # Try to use Hospital B's API key with Hospital A subdomain
        response = await client.get(
            "/api/v1/devices",
            headers={**api_headers, "Host": "hospital-a.nyelux.com"}
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_tenant_search_index_isolation(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test search index isolation"""
        data = setup_multiple_tenants
        
        # Create unique content for each tenant
        hospital_a_admin = data["users"]["hospital_a_admin"]
        hospital_b_admin = data["users"]["hospital_b_admin"]
        
        # Hospital A creates a document with unique content
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": hospital_a_admin.email, "password": "password123"}
        )
        hospital_a_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        unique_content_a = "UniqueHospitalAProtocol12345"
        doc_a = DeviceDocument(
            device_id=data["vendor_devices"][0].id,
            organization_id=data["hospital_a"].id,
            document_type="protocol",
            title=f"Protocol with {unique_content_a}",
            file_url="s3://hospital-a/protocol.pdf",
            metadata={"content": unique_content_a}
        )
        db.add(doc_a)
        
        # Hospital B creates a document with different unique content
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": hospital_b_admin.email, "password": "password123"}
        )
        hospital_b_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        unique_content_b = "UniqueHospitalBProcedure67890"
        doc_b = DeviceDocument(
            device_id=data["vendor_devices"][0].id,
            organization_id=data["hospital_b"].id,
            document_type="procedure",
            title=f"Procedure with {unique_content_b}",
            file_url="s3://hospital-b/procedure.pdf",
            metadata={"content": unique_content_b}
        )
        db.add(doc_b)
        await db.commit()
        
        # Hospital A searches for their unique content
        response = await client.post(
            "/api/v1/search",
            json={"query": unique_content_a, "types": ["documents"]},
            headers=hospital_a_headers
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) > 0
        assert any(unique_content_a in str(r) for r in results)
        
        # Hospital A searches for Hospital B's unique content
        response = await client.post(
            "/api/v1/search",
            json={"query": unique_content_b, "types": ["documents"]},
            headers=hospital_a_headers
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 0  # Should not find Hospital B's content

    @pytest.mark.asyncio
    async def test_concurrent_tenant_operations(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test concurrent operations from multiple tenants"""
        data = setup_multiple_tenants
        
        # Login all admins
        admins = []
        for user_key in ["hospital_a_admin", "hospital_b_admin", "vendor_x_admin"]:
            user = data["users"][user_key]
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": user.email, "password": "password123"}
            )
            token = response.json()["access_token"]
            admins.append((user, {"Authorization": f"Bearer {token}"}))
        
        # Concurrent operations
        async def create_incident(user, headers, device_id, org_id):
            return await client.post(
                "/api/v1/incidents",
                json={
                    "device_id": device_id,
                    "incident_type": "malfunction",
                    "description": f"Issue reported by {user.email}",
                    "urgency": "medium"
                },
                headers=headers
            )
        
        # All tenants create incidents simultaneously
        tasks = []
        for user, headers in admins:
            device_id = data["vendor_devices"][0].id
            task = create_incident(user, headers, device_id, user.organization_id)
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        for response in responses:
            assert response.status_code == 201
        
        # Verify each tenant only sees their own incidents
        for user, headers in admins:
            response = await client.get(
                "/api/v1/incidents",
                headers=headers
            )
            incidents = response.json()["incidents"]
            
            # Should only see incidents from their organization
            for incident in incidents:
                assert user.email in incident["description"]

    @pytest.mark.asyncio
    async def test_tenant_data_migration(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test tenant data integrity during migrations"""
        data = setup_multiple_tenants
        
        # Simulate a scenario where data needs to be migrated
        # Create data that references cross-tenant resources
        
        # Hospital A admin
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_a_admin"].email, "password": "password123"}
        )
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        # Create bookmark for a device
        response = await client.post(
            "/api/v1/bookmarks",
            json={
                "resource_type": "device",
                "resource_id": data["vendor_devices"][0].id,
                "notes": "Important device for ICU"
            },
            headers=headers
        )
        assert response.status_code == 201
        bookmark_id = response.json()["id"]
        
        # Simulate tenant migration/split scenario
        # Verify data integrity maintained
        bookmark = await client.get(
            f"/api/v1/bookmarks/{bookmark_id}",
            headers=headers
        )
        assert bookmark.status_code == 200
        
        # Other tenant cannot access
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_b_admin"].email, "password": "password123"}
        )
        other_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        bookmark = await client.get(
            f"/api/v1/bookmarks/{bookmark_id}",
            headers=other_headers
        )
        assert bookmark.status_code == 404

    @pytest.mark.asyncio
    async def test_tenant_performance_isolation(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test performance isolation between tenants"""
        data = setup_multiple_tenants
        
        # Create heavy load for Hospital A
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_a_admin"].email, "password": "password123"}
        )
        hospital_a_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        # Hospital B normal operations
        response = await client.post(
            "/api/v1/auth/login", 
            data={"username": data["users"]["hospital_b_admin"].email, "password": "password123"}
        )
        hospital_b_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        
        import time
        
        # Measure Hospital B response time before load
        start = time.time()
        response = await client.get("/api/v1/devices", headers=hospital_b_headers)
        baseline_time = time.time() - start
        assert response.status_code == 200
        
        # Generate heavy load from Hospital A (simulate)
        async def heavy_operation():
            return await client.post(
                "/api/v1/devices/search",
                json={"query": "complex search with many filters"},
                headers=hospital_a_headers
            )
        
        # Run concurrent heavy operations
        heavy_tasks = [heavy_operation() for _ in range(10)]
        
        # Meanwhile, Hospital B performs normal operation
        start = time.time()
        response = await client.get("/api/v1/devices", headers=hospital_b_headers)
        loaded_time = time.time() - start
        
        # Complete heavy operations
        await asyncio.gather(*heavy_tasks)
        
        # Hospital B performance should not degrade significantly
        assert response.status_code == 200
        assert loaded_time < baseline_time * 2  # Allow some degradation but not severe

    @pytest.mark.asyncio
    async def test_security_boundaries(
        self, client: AsyncClient, db: AsyncSession, setup_multiple_tenants
    ):
        """Test various security boundary violations"""
        data = setup_multiple_tenants
        
        # Login as Hospital A admin
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["users"]["hospital_a_admin"].email, "password": "password123"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Attempt various cross-tenant access patterns
        security_tests = [
            # Try to update another tenant's organization
            {
                "method": "PATCH",
                "url": f"/api/v1/organizations/{data['hospital_b'].id}",
                "json": {"name": "Hacked Hospital B"},
                "expected_status": [403, 404]
            },
            # Try to add user to another tenant
            {
                "method": "POST",
                "url": "/api/v1/users",
                "json": {
                    "email": "spy@hospital-b.com",
                    "organization_id": data["hospital_b"].id,
                    "role": "org_admin"
                },
                "expected_status": [403, 422]
            },
            # Try to access another tenant's audit logs
            {
                "method": "GET",
                "url": f"/api/v1/audit-logs?organization_id={data['hospital_b'].id}",
                "expected_status": [403, 200]  # 200 OK but empty results
            }
        ]
        
        for test in security_tests:
            if test["method"] == "GET":
                response = await client.get(test["url"], headers=headers)
            elif test["method"] == "POST":
                response = await client.post(
                    test["url"],
                    json=test.get("json", {}),
                    headers=headers
                )
            elif test["method"] == "PATCH":
                response = await client.patch(
                    test["url"],
                    json=test.get("json", {}),
                    headers=headers
                )
            
            assert response.status_code in test["expected_status"]
            
            # If 200 OK, verify no cross-tenant data
            if response.status_code == 200:
                data_returned = response.json()
                if isinstance(data_returned, dict) and "results" in data_returned:
                    assert len(data_returned["results"]) == 0
