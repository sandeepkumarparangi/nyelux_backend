"""
Public Access & Lead Generation Tests
Based on NYELUX Test Coverage Document Section 2
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import asyncio

from src.db.models.lead import Lead
from src.db.models.search_history import SearchHistory
from src.db.models.gudid_device import GUDIDDevice


class TestPublicSearch:
    """Test cases TC-PUBLIC-001 through TC-PUBLIC-004"""
    
    @pytest.mark.asyncio
    async def test_unauthenticated_device_search(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-PUBLIC-001: Unauthenticated Device Search"""
        # Create test devices
        for i in range(20):
            device = GUDIDDevice(
                primary_di=f"TEST{i:06d}",
                device_name=f"Infusion Pump Model {i}",
                manufacturer_name="MedTech Corp",
                device_class="II",
                device_description="Advanced infusion pump for medication delivery"
            )
            db_session.add(device)
        await db_session.commit()
        
        # Test unauthenticated search
        start_time = datetime.utcnow()
        response = await client.get("/api/v1/public/devices/search?q=infusion pump")
        end_time = datetime.utcnow()
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Check result limit
        assert len(data["results"]) <= 10  # Maximum 10 results
        
        # Check response time
        response_time = (end_time - start_time).total_seconds() * 1000
        assert response_time < 300  # Less than 300ms
        
        # Verify limited information (no pricing/vendor data)
        for device in data["results"]:
            assert "device_name" in device
            assert "manufacturer_name" in device
            assert "device_class" in device
            assert "price" not in device
            assert "vendor_specific" not in device
    
    @pytest.mark.asyncio
    async def test_seo_friendly_device_urls(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-PUBLIC-002: SEO-Friendly Device URLs"""
        # Create test device
        device = GUDIDDevice(
            primary_di="00889842001234",
            device_name="Advanced Infusion Pump X200",
            manufacturer_name="MedTech Corporation",
            device_class="II",
            device_description="State-of-the-art infusion pump with smart features",
            brand_name="MedTech Pro"
        )
        db_session.add(device)
        await db_session.commit()
        
        # Test SEO URL
        response = await client.get("/devices/00889842001234")
        assert response.status_code == 200
        
        # Check HTML meta tags
        content = response.text
        assert '<meta name="description"' in content
        assert '<meta property="og:title"' in content
        assert '<meta property="og:description"' in content
        assert '<meta property="og:type" content="product"' in content
        
        # Check JSON-LD structured data
        assert '<script type="application/ld+json">' in content
        assert '"@type": "MedicalDevice"' in content
        assert '"name": "Advanced Infusion Pump X200"' in content
        assert '"manufacturer": "MedTech Corporation"' in content
    
    @pytest.mark.asyncio
    async def test_lead_capture_after_searches(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-PUBLIC-003: Lead Capture After 3 Searches"""
        # Use same session/IP for searches
        headers = {"X-Forwarded-For": "192.168.1.100"}
        
        # Perform 3 searches
        for i in range(3):
            response = await client.get(
                f"/api/v1/public/devices/search?q=device{i}",
                headers=headers
            )
            assert response.status_code == 200
            
            # Check if lead capture triggered
            data = response.json()
            if i < 2:
                assert "show_lead_form" not in data or data["show_lead_form"] is False
            else:
                # After 3rd search
                assert data.get("show_lead_form") is True
        
        # Submit lead form
        lead_data = {
            "email": "potential.customer@hospital.com",
            "first_name": "John",
            "last_name": "Doe",
            "organization": "City Hospital",
            "title": "Procurement Manager",
            "search_history": ["device0", "device1", "device2"]
        }
        
        lead_response = await client.post(
            "/api/v1/public/lead/capture",
            json=lead_data,
            headers=headers
        )
        
        assert lead_response.status_code == 201
        
        # Verify lead in database
        lead = await db_session.execute(
            db_session.query(Lead).filter(Lead.email == lead_data["email"])
        )
        lead = lead.scalar_one()
        
        assert lead is not None
        assert lead.search_count == 3
        assert lead.lead_score > 0
        assert lead.ip_address == "192.168.1.100"
    
    @pytest.mark.asyncio
    async def test_search_rate_limiting(self, client: AsyncClient):
        """TC-PUBLIC-004: Search Rate Limiting"""
        headers = {"X-Forwarded-For": "192.168.1.101"}
        
        # Perform 11 searches within short time
        responses = []
        for i in range(11):
            response = await client.get(
                f"/api/v1/public/devices/search?q=test{i}",
                headers=headers
            )
            responses.append(response)
            
            # Small delay to simulate realistic usage
            await asyncio.sleep(0.1)
        
        # First 10 should succeed
        for i in range(10):
            assert responses[i].status_code == 200
        
        # 11th should be rate limited
        assert responses[10].status_code == 429
        assert "Rate limit exceeded" in responses[10].json()["detail"]
        assert "Retry-After" in responses[10].headers


class TestLeadGeneration:
    """Test cases TC-PUBLIC-005 through TC-PUBLIC-006"""
    
    @pytest.mark.asyncio
    async def test_progressive_form_fields(self, client: AsyncClient):
        """TC-PUBLIC-005: Progressive Form Fields"""
        headers = {"X-Forwarded-For": "192.168.1.102"}
        
        # Initial form submission - email only
        initial_data = {
            "email": "progressive@example.com",
            "form_step": 1
        }
        
        response = await client.post(
            "/api/v1/public/lead/capture",
            json=initial_data,
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["next_step"] == 2
        assert "required_fields" in data
        assert set(data["required_fields"]) == {"first_name", "last_name"}
        
        # Second submission - add name
        step2_data = {
            "email": "progressive@example.com",
            "first_name": "Jane",
            "last_name": "Smith",
            "form_step": 2
        }
        
        response2 = await client.post(
            "/api/v1/public/lead/capture",
            json=step2_data,
            headers=headers
        )
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["next_step"] == 3
        assert "organization" in data2["required_fields"]
        
        # Final submission - complete profile
        final_data = {
            "email": "progressive@example.com",
            "first_name": "Jane",
            "last_name": "Smith",
            "organization": "Regional Medical Center",
            "title": "Director of Purchasing",
            "phone": "555-0123",
            "form_step": 3
        }
        
        response3 = await client.post(
            "/api/v1/public/lead/capture",
            json=final_data,
            headers=headers
        )
        
        assert response3.status_code == 201
        assert response3.json()["status"] == "complete"
    
    @pytest.mark.asyncio
    async def test_lead_quality_scoring(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-PUBLIC-006: Lead Quality Scoring"""
        headers = {"X-Forwarded-For": "192.168.1.103"}
        
        # Test Case 1: Low engagement (1 search, immediate email)
        await client.get("/api/v1/public/devices/search?q=pump", headers=headers)
        
        low_engagement_lead = {
            "email": "low@example.com",
            "search_count": 1,
            "time_on_site": 30,  # 30 seconds
            "pages_viewed": 2
        }
        
        response1 = await client.post(
            "/api/v1/public/lead/capture",
            json=low_engagement_lead,
            headers=headers
        )
        
        lead1_id = response1.json()["id"]
        lead1 = await db_session.get(Lead, lead1_id)
        assert lead1.lead_score < 30  # Low score
        
        # Test Case 2: High engagement (10 searches, multiple devices)
        headers2 = {"X-Forwarded-For": "192.168.1.104"}
        
        # Perform multiple searches
        devices_viewed = []
        for i in range(10):
            response = await client.get(
                f"/api/v1/public/devices/search?q=advanced device {i}",
                headers=headers2
            )
            devices_viewed.extend([d["primary_di"] for d in response.json()["results"][:2]])
            await asyncio.sleep(0.5)  # Simulate time between searches
        
        # View specific device pages
        for device_di in devices_viewed[:5]:
            await client.get(f"/devices/{device_di}", headers=headers2)
        
        high_engagement_lead = {
            "email": "high@example.com",
            "search_count": 10,
            "time_on_site": 600,  # 10 minutes
            "pages_viewed": 25,
            "devices_viewed": devices_viewed[:5],
            "organization": "Large Hospital Network",
            "title": "VP of Operations"
        }
        
        response2 = await client.post(
            "/api/v1/public/lead/capture",
            json=high_engagement_lead,
            headers=headers2
        )
        
        lead2_id = response2.json()["id"]
        lead2 = await db_session.get(Lead, lead2_id)
        assert lead2.lead_score > 70  # High score
        
        # Test Case 3: Medium engagement
        headers3 = {"X-Forwarded-For": "192.168.1.105"}
        
        for i in range(3):
            await client.get(f"/api/v1/public/devices/search?q=specific device", headers=headers3)
        
        medium_engagement_lead = {
            "email": "medium@example.com",
            "search_count": 3,
            "time_on_site": 180,  # 3 minutes
            "pages_viewed": 8,
            "organization": "Private Practice"
        }
        
        response3 = await client.post(
            "/api/v1/public/lead/capture",
            json=medium_engagement_lead,
            headers=headers3
        )
        
        lead3_id = response3.json()["id"]
        lead3 = await db_session.get(Lead, lead3_id)
        assert 30 <= lead3.lead_score <= 70  # Medium score
        
        # Verify scoring factors
        assert lead2.lead_score > lead3.lead_score > lead1.lead_score


class TestPublicDeviceComparison:
    """Additional public feature tests"""
    
    @pytest.mark.asyncio
    async def test_public_device_comparison(self, client: AsyncClient, db_session: AsyncSession):
        """Test public device comparison (max 3 devices)"""
        # Create test devices
        device_ids = []
        for i in range(5):
            device = GUDIDDevice(
                primary_di=f"COMPARE{i:06d}",
                device_name=f"Comparison Device {i}",
                manufacturer_name="TestCorp",
                device_class="II"
            )
            db_session.add(device)
        await db_session.commit()
        
        # Test comparison with 3 devices (allowed)
        response = await client.post("/api/v1/public/devices/compare", json={
            "device_ids": ["COMPARE000000", "COMPARE000001", "COMPARE000002"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["devices"]) == 3
        assert "comparison_id" in data
        
        # Test comparison with 4 devices (should fail)
        response2 = await client.post("/api/v1/public/devices/compare", json={
            "device_ids": ["COMPARE000000", "COMPARE000001", "COMPARE000002", "COMPARE000003"]
        })
        
        assert response2.status_code == 400
        assert "Maximum 3 devices" in response2.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
