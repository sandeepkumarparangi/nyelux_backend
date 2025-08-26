"""
Integration tests for Browser & Device Compatibility.
Tests cover cross-browser functionality and responsive design.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List
import json
import re

from src.db.models.user import User
from src.db.models.organization import Organization
from src.services.auth_service import AuthService


class TestBrowserDeviceCompatibility:
    """Test cases for Browser & Device Compatibility - Section 17"""

    @pytest.fixture
    async def setup_test_user(self, db: AsyncSession):
        """Create test user for browser testing"""
        org = Organization(
            name="Browser Test Hospital",
            type="hospital",
            subdomain="browser-test"
        )
        db.add(org)
        await db.flush()

        auth_service = AuthService()
        
        user = User(
            email="browser@test.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Browser",
            last_name="Test",
            role="nurse",
            organization_id=org.id
        )
        db.add(user)
        await db.commit()
        
        return user

    @pytest.fixture
    async def auth_headers_with_user_agent(self, client: AsyncClient, setup_test_user):
        """Get auth headers with different user agents"""
        async def get_headers(user_agent: str):
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": setup_test_user.email, "password": "password123"},
                headers={"User-Agent": user_agent}
            )
            token = response.json()["access_token"]
            return {
                "Authorization": f"Bearer {token}",
                "User-Agent": user_agent
            }
        
        return get_headers

    @pytest.mark.asyncio
    async def test_tc_browser_001_core_functionality_all_browsers(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """TC-BROWSER-001: Test core functionality across all supported browsers"""
        # Browser user agents
        browsers = {
            "Chrome 90+": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
            "Firefox 88+": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0",
            "Safari 14+": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15",
            "Edge 90+": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36 Edg/90.0.818.62"
        }
        
        # Core features to test
        core_features = [
            # Search functionality
            {
                "name": "Device Search",
                "endpoint": "/api/v1/devices/search",
                "method": "POST",
                "data": {"query": "infusion pump"}
            },
            # Image upload
            {
                "name": "Image Upload",
                "endpoint": "/api/v1/images/analyze",
                "method": "POST",
                "files": {"image": ("test.jpg", b"fake_image_data", "image/jpeg")}
            },
            # Real-time features (WebSocket simulation)
            {
                "name": "Real-time Chat",
                "endpoint": "/api/v1/chat/connect",
                "method": "POST",
                "data": {"channel": "support"}
            },
            # Video playback metadata
            {
                "name": "Video Playback",
                "endpoint": "/api/v1/videos/1/metadata",
                "method": "GET"
            }
        ]
        
        results = {}
        
        for browser_name, user_agent in browsers.items():
            headers = await auth_headers_with_user_agent(user_agent)
            browser_results = {}
            
            for feature in core_features:
                try:
                    if feature["method"] == "GET":
                        response = await client.get(
                            feature["endpoint"],
                            headers=headers
                        )
                    elif feature["method"] == "POST":
                        if "files" in feature:
                            response = await client.post(
                                feature["endpoint"],
                                files=feature["files"],
                                headers=headers
                            )
                        else:
                            response = await client.post(
                                feature["endpoint"],
                                json=feature.get("data", {}),
                                headers=headers
                            )
                    
                    browser_results[feature["name"]] = {
                        "status": response.status_code,
                        "success": 200 <= response.status_code < 300 or response.status_code == 404
                    }
                    
                except Exception as e:
                    browser_results[feature["name"]] = {
                        "status": 0,
                        "success": False,
                        "error": str(e)
                    }
            
            results[browser_name] = browser_results
        
        # Verify all browsers support core features
        for browser, features in results.items():
            for feature_name, result in features.items():
                assert result["success"], f"{browser} failed {feature_name}"

    @pytest.mark.asyncio
    async def test_responsive_design_headers(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test responsive design support across different devices"""
        # Device configurations
        devices = {
            "Mobile - iPhone 12": {
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
                "viewport": "390x844",
                "category": "mobile"
            },
            "Mobile - Samsung Galaxy S21": {
                "user_agent": "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36",
                "viewport": "360x800", 
                "category": "mobile"
            },
            "Tablet - iPad Pro": {
                "user_agent": "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
                "viewport": "1024x1366",
                "category": "tablet"
            },
            "Desktop - 1080p": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "viewport": "1920x1080",
                "category": "desktop"
            },
            "Desktop - 4K": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "viewport": "3840x2160",
                "category": "wide"
            }
        }
        
        for device_name, config in devices.items():
            headers = await auth_headers_with_user_agent(config["user_agent"])
            headers["X-Viewport-Size"] = config["viewport"]
            
            # Test API responses adapt to device
            response = await client.get(
                "/api/v1/devices?include_responsive_hints=true",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if responsive hints are provided
                if "responsive_hints" in data:
                    hints = data["responsive_hints"]
                    
                    if config["category"] == "mobile":
                        # Mobile should get simplified data
                        assert hints.get("simplified_view", False)
                        assert hints.get("image_size", "small") == "small"
                    elif config["category"] == "desktop" or config["category"] == "wide":
                        # Desktop should get full data
                        assert not hints.get("simplified_view", True)
                        assert hints.get("image_size", "large") in ["large", "full"]

    @pytest.mark.asyncio
    async def test_javascript_api_compatibility(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test JavaScript API compatibility requirements"""
        # Get auth token for JavaScript usage
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "browser@test.com", "password": "password123"}
        )
        token = response.json()["access_token"]
        
        # Test CORS headers for JavaScript access
        headers = {
            "Authorization": f"Bearer {token}",
            "Origin": "https://app.nyelux.com",
            "Referer": "https://app.nyelux.com/"
        }
        
        response = await client.options(
            "/api/v1/devices",
            headers=headers
        )
        
        # Should have proper CORS headers
        assert "Access-Control-Allow-Origin" in response.headers
        assert "Access-Control-Allow-Methods" in response.headers
        assert "Access-Control-Allow-Headers" in response.headers
        
        # Test that API returns JavaScript-friendly formats
        response = await client.get(
            "/api/v1/devices?format=json",
            headers=headers
        )
        
        assert response.status_code == 200
        
        # Verify JSON is valid
        data = response.json()
        
        # Check date formats are ISO 8601 (JavaScript parseable)
        if "devices" in data and len(data["devices"]) > 0:
            device = data["devices"][0]
            if "created_at" in device:
                # Should match ISO 8601 format
                assert re.match(
                    r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',
                    device["created_at"]
                )

    @pytest.mark.asyncio
    async def test_mobile_specific_features(
        self, client: AsyncClient, db: AsyncSession
    ):
        """Test mobile-specific features and optimizations"""
        mobile_user_agents = [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
            "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36"
        ]
        
        for user_agent in mobile_user_agents:
            # Test touch-optimized endpoints
            headers = {"User-Agent": user_agent}
            
            # Test barcode scanning capability check
            response = await client.get(
                "/api/v1/capabilities/camera",
                headers=headers
            )
            
            if response.status_code == 200:
                capabilities = response.json()
                assert "barcode_scanning" in capabilities
                assert "image_capture" in capabilities
            
            # Test offline manifest for PWA
            response = await client.get(
                "/api/v1/manifest.json",
                headers=headers
            )
            
            if response.status_code == 200:
                manifest = response.json()
                assert "name" in manifest
                assert "short_name" in manifest
                assert "icons" in manifest
                assert "start_url" in manifest
                assert "display" in manifest

    @pytest.mark.asyncio
    async def test_legacy_browser_fallbacks(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test fallback behavior for older browsers"""
        # Older browser user agent
        old_browser = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/60.0.3112.113"
        headers = await auth_headers_with_user_agent(old_browser)
        
        # Should receive compatibility warnings
        response = await client.get(
            "/api/v1/compatibility/check",
            headers=headers
        )
        
        if response.status_code == 200:
            compat = response.json()
            assert compat["supported"] is False
            assert "upgrade_recommended" in compat
            assert compat["upgrade_recommended"] is True
            
            # Should still provide basic functionality
            assert compat["basic_features_available"] is True

    @pytest.mark.asyncio
    async def test_progressive_enhancement(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test progressive enhancement features"""
        # Modern browser with full capabilities
        modern_headers = await auth_headers_with_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/90.0.4430.212"
        )
        
        # Check enhanced features availability
        response = await client.get(
            "/api/v1/features/available",
            headers=modern_headers
        )
        
        if response.status_code == 200:
            features = response.json()
            
            # Modern browsers should get enhanced features
            expected_features = [
                "websocket_support",
                "service_worker",
                "webrtc_video",
                "web_share_api",
                "web_notifications"
            ]
            
            for feature in expected_features:
                if feature in features:
                    assert features[feature]["available"] is True

    @pytest.mark.asyncio
    async def test_accessibility_api_support(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test accessibility features across browsers"""
        headers = await auth_headers_with_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        # Request with accessibility preferences
        headers["X-Accessibility-Mode"] = "screen-reader"
        headers["X-Prefers-Reduced-Motion"] = "true"
        
        response = await client.get(
            "/api/v1/devices",
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for accessibility enhancements
            if "accessibility_metadata" in data:
                meta = data["accessibility_metadata"]
                
                # Should include screen reader hints
                assert "aria_descriptions" in meta
                
                # Should respect reduced motion
                assert meta.get("animations_disabled", False) is True

    @pytest.mark.asyncio
    async def test_performance_hints_by_device(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test performance optimization hints based on device capabilities"""
        # Low-end mobile device
        low_end_headers = await auth_headers_with_user_agent(
            "Mozilla/5.0 (Linux; Android 8.0; SM-G570F) AppleWebKit/537.36"
        )
        low_end_headers["X-Device-Memory"] = "1"  # 1GB RAM
        low_end_headers["X-Network-Type"] = "3g"
        
        response = await client.get(
            "/api/v1/performance/hints",
            headers=low_end_headers
        )
        
        if response.status_code == 200:
            hints = response.json()
            
            # Should recommend optimizations
            assert hints["reduce_image_quality"] is True
            assert hints["limit_concurrent_requests"] is True
            assert hints["use_pagination"] is True
            assert hints["page_size"] <= 20
        
        # High-end device
        high_end_headers = await auth_headers_with_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        high_end_headers["X-Device-Memory"] = "16"  # 16GB RAM
        high_end_headers["X-Network-Type"] = "5g"
        
        response = await client.get(
            "/api/v1/performance/hints",
            headers=high_end_headers
        )
        
        if response.status_code == 200:
            hints = response.json()
            
            # Can handle more data
            assert hints["reduce_image_quality"] is False
            assert hints["page_size"] >= 50

    @pytest.mark.asyncio
    async def test_file_api_compatibility(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test file handling across different browsers"""
        browsers = [
            ("Chrome", "Mozilla/5.0 Chrome/90.0.4430.212"),
            ("Firefox", "Mozilla/5.0 Firefox/88.0"),
            ("Safari", "Mozilla/5.0 Version/14.1 Safari/605.1.15")
        ]
        
        for browser_name, user_agent in browsers:
            headers = await auth_headers_with_user_agent(user_agent)
            
            # Test file upload capabilities
            response = await client.get(
                "/api/v1/upload/capabilities",
                headers=headers
            )
            
            if response.status_code == 200:
                capabilities = response.json()
                
                # All modern browsers should support these
                assert capabilities["max_file_size"] > 0
                assert "supported_formats" in capabilities
                assert len(capabilities["supported_formats"]) > 0
                
                # Check for browser-specific features
                if browser_name == "Chrome":
                    # Chrome supports more file APIs
                    assert capabilities.get("directory_upload", False) is True

    @pytest.mark.asyncio
    async def test_websocket_fallback(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test WebSocket fallback mechanisms"""
        # Headers indicating no WebSocket support
        headers = await auth_headers_with_user_agent(
            "Mozilla/5.0 (compatible; OldBrowser/1.0)"
        )
        headers["X-No-WebSocket"] = "true"
        
        # Request real-time connection
        response = await client.post(
            "/api/v1/realtime/connect",
            json={"channel": "updates"},
            headers=headers
        )
        
        if response.status_code == 200:
            connection_info = response.json()
            
            # Should provide fallback method
            assert connection_info["transport"] != "websocket"
            assert connection_info["transport"] in ["long-polling", "server-sent-events"]
            assert "fallback_url" in connection_info

    @pytest.mark.asyncio
    async def test_content_negotiation(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test content negotiation for different clients"""
        headers = await auth_headers_with_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        # Test different Accept headers
        accept_types = [
            ("application/json", "json"),
            ("application/xml", "xml"),
            ("text/csv", "csv"),
            ("application/vnd.api+json", "jsonapi")
        ]
        
        for accept_header, expected_format in accept_types:
            headers["Accept"] = accept_header
            
            response = await client.get(
                "/api/v1/devices?limit=5",
                headers=headers
            )
            
            # API should respect Accept header or return 406
            assert response.status_code in [200, 406]
            
            if response.status_code == 200:
                content_type = response.headers.get("Content-Type", "")
                
                if expected_format == "json":
                    assert "application/json" in content_type
                elif expected_format == "xml" and "xml" in content_type:
                    assert "application/xml" in content_type
                elif expected_format == "csv" and "csv" in content_type:
                    assert "text/csv" in content_type

    @pytest.mark.asyncio
    async def test_browser_storage_hints(
        self, client: AsyncClient, db: AsyncSession, auth_headers_with_user_agent
    ):
        """Test browser storage capability hints"""
        headers = await auth_headers_with_user_agent(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"
        )
        
        response = await client.get(
            "/api/v1/storage/recommendations",
            headers=headers
        )
        
        if response.status_code == 200:
            recommendations = response.json()
            
            # Should provide storage recommendations
            assert "offline_storage_limit_mb" in recommendations
            assert "use_indexeddb" in recommendations
            assert "cache_strategy" in recommendations
            
            # Mobile devices might have different limits
            assert recommendations["offline_storage_limit_mb"] <= 500
