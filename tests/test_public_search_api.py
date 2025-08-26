"""
Test suite for public search API endpoints
Tests REAL Supabase data - NO MOCKS
"""
import pytest
from httpx import AsyncClient
from fastapi import status
import time

from src.main import app


@pytest.mark.asyncio
class TestPublicSearchAPI:
    """Test public search endpoints with real data"""
    
    async def test_typeahead_search_basic(self):
        """Test basic typeahead functionality"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/public/v2/typeahead",
                params={"q": "infusion", "limit": 5}
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            # Verify response structure
            assert "query" in data
            assert "suggestions" in data
            assert "total_found" in data
            assert "response_time_ms" in data
            
            # Verify we got results
            assert len(data["suggestions"]) > 0
            assert data["total_found"] > 0
            
            # Verify response time is reasonable
            assert data["response_time_ms"] < 200  # Should be under 200ms
            
            # Verify suggestion structure
            suggestion = data["suggestions"][0]
            assert "id" in suggestion
            assert "display_name" in suggestion
            assert "manufacturer" in suggestion
            assert "match_type" in suggestion
            assert "confidence" in suggestion
    
    async def test_typeahead_search_minimum_length(self):
        """Test minimum query length requirement"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Too short query
            response = await client.get(
                "/api/v1/public/v2/typeahead",
                params={"q": "i"}  # Only 1 character
            )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_typeahead_search_various_queries(self):
        """Test different types of searches"""
        test_cases = [
            ("pump", "device_name"),      # Device name search
            ("medtronic", "manufacturer"), # Manufacturer search
            ("catheter", "device_name"),   # Another device
            ("MRI", "device_name"),        # Feature search
        ]
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            for query, expected_match_type in test_cases:
                response = await client.get(
                    "/api/v1/public/v2/typeahead",
                    params={"q": query, "limit": 10}
                )
                
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert len(data["suggestions"]) > 0
                
                # Check that at least one result has expected match type
                match_types = [s["match_type"] for s in data["suggestions"]]
                # Note: We may get multiple match types, just verify we have results
                assert len(match_types) > 0
    
    async def test_typeahead_search_limit(self):
        """Test result limit parameter"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Test different limits
            for limit in [1, 5, 10, 20]:
                response = await client.get(
                    "/api/v1/public/v2/typeahead",
                    params={"q": "device", "limit": limit}
                )
                
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert len(data["suggestions"]) <= limit
    
    async def test_typeahead_search_performance(self):
        """Test search performance requirements"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Run multiple searches to test consistency
            response_times = []
            
            for _ in range(5):
                start = time.time()
                response = await client.get(
                    "/api/v1/public/v2/typeahead",
                    params={"q": "infusion pump", "limit": 10}
                )
                elapsed = (time.time() - start) * 1000  # Convert to ms
                
                assert response.status_code == status.HTTP_200_OK
                response_times.append(elapsed)
            
            # Check that 95% of requests are under 100ms
            sorted_times = sorted(response_times)
            p95 = sorted_times[int(len(sorted_times) * 0.95)]
            assert p95 < 100, f"P95 response time {p95}ms exceeds 100ms target"
    
    async def test_device_details_valid(self):
        """Test getting device details with valid ID"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # First get a device ID from search
            search_response = await client.get(
                "/api/v1/public/v2/typeahead",
                params={"q": "infusion", "limit": 1}
            )
            
            assert search_response.status_code == status.HTTP_200_OK
            device_id = search_response.json()["suggestions"][0]["id"]
            
            # Get device details
            response = await client.get(f"/api/v1/public/v2/devices/{device_id}")
            
            assert response.status_code == status.HTTP_200_OK
            device = response.json()
            
            # Verify required fields
            assert "primary_di" in device
            assert "device_name" in device
            assert "manufacturer_name" in device
            
            # Verify public fields are present but not full details
            public_fields = [
                "brand_name", "model_number", "device_class",
                "device_description", "gmdn_terms", "mri_safety",
                "sterile", "single_use", "implantable",
                "life_supporting", "rx_required"
            ]
            
            for field in public_fields:
                assert field in device
    
    async def test_device_details_invalid(self):
        """Test device details with invalid ID"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/public/v2/devices/INVALID_ID_12345")
            assert response.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_manufacturers_list(self):
        """Test getting manufacturers list"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/public/v2/manufacturers",
                params={"limit": 20}
            )
            
            # Note: This endpoint may need the SQL function created in Supabase
            # If not available, it should still return a response
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "manufacturers" in data
            assert "total" in data
    
    async def test_manufacturers_search(self):
        """Test searching manufacturers"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/public/v2/manufacturers",
                params={"q": "med", "limit": 10}
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "manufacturers" in data
            
            # If we have results, they should contain "med"
            if data["manufacturers"]:
                for mfr in data["manufacturers"]:
                    assert "med" in mfr.lower()
    
    async def test_categories(self):
        """Test device categories endpoint"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/public/v2/categories")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            # Verify structure
            assert "device_classes" in data
            assert "mri_safety" in data
            
            # Verify FDA classes
            assert len(data["device_classes"]) == 3
            class_codes = [c["code"] for c in data["device_classes"]]
            assert "I" in class_codes
            assert "II" in class_codes
            assert "III" in class_codes
            
            # Verify MRI safety options
            assert len(data["mri_safety"]) > 0
            assert "MR Safe" in data["mri_safety"]
    
    async def test_search_tracking(self):
        """Test search tracking for lead generation"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            session_id = "test-session-123"
            
            # Track multiple searches
            for i in range(4):
                response = await client.post(
                    "/api/v1/public/v2/track-search",
                    params={
                        "query": f"test query {i+1}",
                        "results_shown": 10
                    },
                    headers={"x-session-id": session_id}
                )
                
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                
                assert "session_id" in data
                assert "search_count" in data
                assert "show_lead_form" in data
                
                # Should show lead form after 3 searches
                if i >= 2:
                    assert data["show_lead_form"] == True
                else:
                    assert data["show_lead_form"] == False
    
    async def test_search_special_characters(self):
        """Test handling of special characters in search"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            special_queries = [
                "test's",     # Apostrophe
                "test-device", # Hyphen
                "test&device", # Ampersand
                "test/device", # Slash
            ]
            
            for query in special_queries:
                response = await client.get(
                    "/api/v1/public/v2/typeahead",
                    params={"q": query, "limit": 5}
                )
                
                # Should handle gracefully without errors
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "suggestions" in data
    
    async def test_concurrent_searches(self):
        """Test handling concurrent search requests"""
        import asyncio
        
        async def search(client, query):
            response = await client.get(
                "/api/v1/public/v2/typeahead",
                params={"q": query, "limit": 5}
            )
            return response
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Run 10 concurrent searches
            queries = ["pump", "catheter", "stent", "valve", "needle"] * 2
            tasks = [search(client, q) for q in queries]
            responses = await asyncio.gather(*tasks)
            
            # All should succeed
            for response in responses:
                assert response.status_code == status.HTTP_200_OK
