"""
Image Recognition & Barcode Scanning Tests
Based on NYELUX Test Coverage Document Section 4
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import base64
import io
from PIL import Image
import numpy as np
from unittest.mock import patch, MagicMock

from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.services.image_recognition_service import ImageRecognitionService
from src.services.barcode_service import BarcodeService


class TestVisualDeviceRecognition:
    """Test cases TC-IMAGE-001 through TC-IMAGE-003"""
    
    @pytest.mark.asyncio
    async def test_clear_device_image_recognition(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-IMAGE-001: Clear Device Image Recognition"""
        # Create test devices that ML model might recognize
        devices = [
            {
                "primary_di": "PUMP001",
                "device_name": "SmartFlow Infusion Pump X200",
                "manufacturer_name": "MedTech Corp",
                "device_class": "II"
            },
            {
                "primary_di": "VENT001",
                "device_name": "BreathEasy Ventilator Pro",
                "manufacturer_name": "Respiratory Systems Inc",
                "device_class": "III"
            },
            {
                "primary_di": "SURG001",
                "device_name": "Precision Surgical Instrument Set",
                "manufacturer_name": "SurgiTool Co",
                "device_class": "II"
            }
        ]
        
        for device_data in devices:
            device = GUDIDDevice(**device_data)
            db_session.add(device)
        await db_session.commit()
        
        # Test cases with expected results
        test_images = [
            {
                "name": "infusion_pump_clear.jpg",
                "expected_device": "PUMP001",
                "expected_confidence": 0.85,
                "description": "High-res infusion pump photo"
            },
            {
                "name": "ventilator_front.jpg",
                "expected_device": "VENT001",
                "expected_confidence": 0.90,
                "description": "Ventilator front panel"
            },
            {
                "name": "surgical_instruments.jpg",
                "expected_device": "SURG001",
                "expected_confidence": 0.75,
                "description": "Surgical instrument set"
            }
        ]
        
        for test_case in test_images:
            # Create mock image (in real test, load actual test images)
            image = self._create_test_image(test_case["name"])
            
            # Convert to base64
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            # Test image recognition
            start_time = datetime.utcnow()
            
            response = await client.post(
                "/api/v1/devices/recognize",
                json={
                    "image": image_base64,
                    "image_format": "jpeg"
                },
                headers=authenticated_headers
            )
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Assertions
            assert response.status_code == 200
            data = response.json()
            
            # Check processing time
            assert processing_time < 2.0, f"Processing took {processing_time}s, expected < 2s"
            
            # Check results
            assert "predictions" in data
            assert len(data["predictions"]) > 0
            
            # Check top prediction
            top_prediction = data["predictions"][0]
            assert top_prediction["confidence"] >= test_case["expected_confidence"]
            assert top_prediction["device_id"] == test_case["expected_device"]
            assert "bounding_box" in top_prediction  # For localization
            
            # Check similar devices suggested
            assert "similar_devices" in data
            assert len(data["similar_devices"]) >= 2
    
    @pytest.mark.asyncio
    async def test_challenging_image_conditions(
        self, client: AsyncClient, authenticated_headers
    ):
        """TC-IMAGE-002: Challenging Conditions"""
        test_cases = [
            {
                "name": "blurry_image",
                "condition": "blur",
                "expected_behavior": "lower_confidence"
            },
            {
                "name": "partial_device",
                "condition": "partial",
                "expected_behavior": "best_match_with_warning"
            },
            {
                "name": "multiple_devices",
                "condition": "multiple",
                "expected_behavior": "all_identified"
            },
            {
                "name": "low_light",
                "condition": "dark",
                "expected_behavior": "enhanced_processing"
            }
        ]
        
        for test_case in test_cases:
            # Create test image with specific condition
            if test_case["condition"] == "blur":
                image = self._create_blurry_image()
            elif test_case["condition"] == "partial":
                image = self._create_partial_device_image()
            elif test_case["condition"] == "multiple":
                image = self._create_multiple_devices_image()
            elif test_case["condition"] == "dark":
                image = self._create_low_light_image()
            
            # Convert to base64
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            response = await client.post(
                "/api/v1/devices/recognize",
                json={"image": image_base64},
                headers=authenticated_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify expected behavior
            if test_case["expected_behavior"] == "lower_confidence":
                assert data["predictions"][0]["confidence"] < 0.7
                assert data.get("quality_warning") == "Image appears blurry"
                
            elif test_case["expected_behavior"] == "best_match_with_warning":
                assert "partial_device_warning" in data
                assert data["predictions"][0]["confidence"] < 0.8
                
            elif test_case["expected_behavior"] == "all_identified":
                assert len(data["predictions"]) > 1
                for pred in data["predictions"]:
                    assert "bounding_box" in pred
                    
            elif test_case["expected_behavior"] == "enhanced_processing":
                assert data.get("processing_applied", []) == ["brightness_enhancement"]
    
    @pytest.mark.asyncio
    async def test_malicious_image_security(
        self, client: AsyncClient, authenticated_headers
    ):
        """TC-IMAGE-003: Security - Malicious Images"""
        # Test various security scenarios
        security_tests = [
            {
                "name": "script_in_exif",
                "payload": self._create_image_with_malicious_exif(),
                "expected_status": 200  # Should sanitize and process
            },
            {
                "name": "oversized_image",
                "payload": self._create_oversized_image(100 * 1024 * 1024),  # 100MB
                "expected_status": 413,  # Payload too large
                "expected_error": "Image size exceeds 10MB limit"
            },
            {
                "name": "corrupted_jpeg",
                "payload": b"corrupted_data_not_valid_jpeg",
                "expected_status": 400,
                "expected_error": "Invalid image format"
            },
            {
                "name": "heic_exploit",
                "payload": self._create_heic_exploit_attempt(),
                "expected_status": 400,
                "expected_error": "Unsupported image format"
            }
        ]
        
        for test in security_tests:
            if isinstance(test["payload"], bytes):
                image_base64 = base64.b64encode(test["payload"]).decode()
            else:
                image_base64 = test["payload"]
            
            response = await client.post(
                "/api/v1/devices/recognize",
                json={"image": image_base64},
                headers=authenticated_headers
            )
            
            assert response.status_code == test["expected_status"]
            
            if test["expected_status"] != 200:
                assert test["expected_error"] in response.json()["detail"]
            else:
                # Verify no malicious content executed
                data = response.json()
                assert "predictions" in data  # Normal processing occurred
    
    def _create_test_image(self, name):
        """Create a test image"""
        img = Image.new('RGB', (800, 600), color='white')
        # In real implementation, load actual device images
        return img
    
    def _create_blurry_image(self):
        """Create a blurry test image"""
        img = Image.new('RGB', (800, 600), color='white')
        # Apply Gaussian blur
        return img
    
    def _create_partial_device_image(self):
        """Create image showing only part of device"""
        img = Image.new('RGB', (800, 600), color='white')
        # Show only half of device
        return img
    
    def _create_multiple_devices_image(self):
        """Create image with multiple devices"""
        img = Image.new('RGB', (1200, 800), color='white')
        # Add multiple device representations
        return img
    
    def _create_low_light_image(self):
        """Create dark/low light image"""
        img = Image.new('RGB', (800, 600), color=(30, 30, 30))
        return img
    
    def _create_image_with_malicious_exif(self):
        """Create image with script in EXIF data"""
        img = Image.new('RGB', (100, 100), color='white')
        # In real test, add malicious EXIF data
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode()
    
    def _create_oversized_image(self, size):
        """Create image exceeding size limit"""
        # Create minimal valid JPEG header then pad with data
        return b"fake_large_image_data" * (size // 20)
    
    def _create_heic_exploit_attempt(self):
        """Create fake HEIC with potential exploit"""
        return b"fake_heic_exploit_data"


class TestBarcodeScanning:
    """Test cases TC-BARCODE-001 through TC-BARCODE-003"""
    
    @pytest.mark.asyncio
    async def test_fda_udi_parsing(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-BARCODE-001: FDA UDI Parsing"""
        # Test various UDI formats
        test_cases = [
            {
                "barcode": "(01)00889842001234(17)250131(10)LOT123",
                "format": "GS1-128",
                "expected": {
                    "di": "00889842001234",
                    "expiry": "2025-01-31",
                    "lot": "LOT123",
                    "serial": None
                }
            },
            {
                "barcode": "(01)00889842001234(17)250131(21)SN12345",
                "format": "GS1-128",
                "expected": {
                    "di": "00889842001234",
                    "expiry": "2025-01-31",
                    "lot": None,
                    "serial": "SN12345"
                }
            },
            {
                "barcode": "(01)00889842001234(11)240615(10)BATCH789(21)SERIAL456",
                "format": "GS1-128",
                "expected": {
                    "di": "00889842001234",
                    "manufacturing_date": "2024-06-15",
                    "lot": "BATCH789",
                    "serial": "SERIAL456"
                }
            },
            {
                "barcode": "=/08888420012349LOT123456789$+240131",
                "format": "HIBCC",
                "expected": {
                    "di": "08888420012349",
                    "lot": "LOT123456789",
                    "expiry": "2024-01-31"
                }
            }
        ]
        
        for test in test_cases:
            response = await client.post(
                "/api/v1/devices/scan",
                json={
                    "barcode_data": test["barcode"],
                    "format": test["format"]
                },
                headers=authenticated_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify parsing
            assert data["device_identifier"] == test["expected"]["di"]
            
            if test["expected"]["expiry"]:
                assert data["expiry_date"] == test["expected"]["expiry"]
            
            if test["expected"]["lot"]:
                assert data["lot_number"] == test["expected"]["lot"]
                
            if test["expected"]["serial"]:
                assert data["serial_number"] == test["expected"]["serial"]
            
            # Verify device lookup
            if data.get("device_found"):
                assert "device_details" in data
            
            # Verify GTIN validation
            assert data["gtin_valid"] is True
    
    @pytest.mark.asyncio
    async def test_damaged_barcode_handling(
        self, client: AsyncClient, authenticated_headers
    ):
        """TC-BARCODE-002: Damaged Barcode Handling"""
        # Test Reed-Solomon error correction
        test_cases = [
            {
                "description": "30% obscured DataMatrix",
                "barcode_image": self._create_damaged_datamatrix(0.3),
                "expected_success": True,
                "expected_confidence": 0.7
            },
            {
                "description": "Curved surface barcode",
                "barcode_image": self._create_curved_barcode(),
                "expected_success": True,
                "expected_confidence": 0.8
            },
            {
                "description": "Poor lighting barcode",
                "barcode_image": self._create_low_contrast_barcode(),
                "expected_success": True,
                "expected_confidence": 0.6
            },
            {
                "description": "50% damaged - too much",
                "barcode_image": self._create_damaged_datamatrix(0.5),
                "expected_success": False,
                "expected_error": "Barcode too damaged to read"
            }
        ]
        
        for test in test_cases:
            response = await client.post(
                "/api/v1/devices/scan/image",
                json={
                    "image": test["barcode_image"],
                    "enhance": True  # Enable image enhancement
                },
                headers=authenticated_headers
            )
            
            if test["expected_success"]:
                assert response.status_code == 200
                data = response.json()
                assert data["confidence"] >= test["expected_confidence"]
                assert "device_identifier" in data
            else:
                assert response.status_code == 422
                assert test["expected_error"] in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_bulk_scanning_mode(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-BARCODE-003: Bulk Scanning Mode"""
        # Enable bulk scanning session
        session_response = await client.post(
            "/api/v1/devices/scan/bulk/start",
            json={"session_name": "Inventory Check 2024-01-15"},
            headers=authenticated_headers
        )
        
        assert session_response.status_code == 200
        session_id = session_response.json()["session_id"]
        
        # Scan 50 devices rapidly
        scanned_devices = []
        for i in range(50):
            barcode = f"(01)0088984200{i:04d}(17)250131(10)LOT{i:03d}"
            
            scan_response = await client.post(
                f"/api/v1/devices/scan/bulk/{session_id}",
                json={"barcode_data": barcode},
                headers=authenticated_headers
            )
            
            assert scan_response.status_code == 200
            scanned_devices.append(scan_response.json())
        
        # End session and get results
        end_response = await client.post(
            f"/api/v1/devices/scan/bulk/{session_id}/complete",
            headers=authenticated_headers
        )
        
        assert end_response.status_code == 200
        results = end_response.json()
        
        # Verify bulk scan results
        assert results["total_scanned"] == 50
        assert results["successful_scans"] == 50
        assert results["failed_scans"] == 0
        assert len(results["devices"]) == 50
        
        # Test export functionality
        export_response = await client.get(
            f"/api/v1/devices/scan/bulk/{session_id}/export?format=csv",
            headers=authenticated_headers
        )
        
        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "text/csv"
        
        # Verify all scans were saved
        csv_content = export_response.text
        assert csv_content.count('\n') >= 51  # Header + 50 devices
    
    def _create_damaged_datamatrix(self, damage_percent):
        """Create DataMatrix barcode with simulated damage"""
        # In real implementation, generate actual damaged barcode image
        return "base64_encoded_damaged_barcode_image"
    
    def _create_curved_barcode(self):
        """Create barcode on curved surface"""
        return "base64_encoded_curved_barcode_image"
    
    def _create_low_contrast_barcode(self):
        """Create low contrast barcode image"""
        return "base64_encoded_low_contrast_barcode"


class TestMobileSpecificFeatures:
    """Test mobile-specific camera and scanning features"""
    
    @pytest.mark.asyncio
    async def test_mobile_camera_integration(
        self, client: AsyncClient, authenticated_headers
    ):
        """Test mobile camera permission flow and live preview"""
        # Test camera permission request
        permission_response = await client.post(
            "/api/v1/devices/camera/request-permission",
            headers=authenticated_headers
        )
        
        assert permission_response.status_code == 200
        assert "permission_requested" in permission_response.json()
        
        # Test camera stream initialization
        stream_response = await client.post(
            "/api/v1/devices/camera/init-stream",
            json={
                "mode": "barcode_scan",
                "camera": "rear",
                "resolution": "1920x1080"
            },
            headers=authenticated_headers
        )
        
        assert stream_response.status_code == 200
        stream_data = stream_response.json()
        assert "stream_id" in stream_data
        assert "websocket_url" in stream_data
        
        # Test focus/exposure control
        control_response = await client.post(
            f"/api/v1/devices/camera/stream/{stream_data['stream_id']}/control",
            json={
                "focus_mode": "continuous",
                "exposure_compensation": 0,
                "flash": "off"
            },
            headers=authenticated_headers
        )
        
        assert control_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_offline_barcode_validation(
        self, client: AsyncClient, authenticated_headers
    ):
        """Test offline UDI validation capabilities"""
        # Download offline validation rules
        offline_response = await client.get(
            "/api/v1/devices/scan/offline-rules",
            headers=authenticated_headers
        )
        
        assert offline_response.status_code == 200
        rules = offline_response.json()
        
        assert "checksum_algorithms" in rules
        assert "format_patterns" in rules
        assert "date_formats" in rules
        
        # Test offline validation endpoint
        validation_response = await client.post(
            "/api/v1/devices/scan/validate-offline",
            json={
                "barcode_data": "(01)00889842001234(17)250131(10)LOT123",
                "rules": rules
            },
            headers=authenticated_headers
        )
        
        assert validation_response.status_code == 200
        validation = validation_response.json()
        
        assert validation["format_valid"] is True
        assert validation["checksum_valid"] is True
        assert validation["date_valid"] is True
        assert "parsed_data" in validation


class TestComplianceAndStandards:
    """Test FDA UDI compliance and international standards"""
    
    @pytest.mark.asyncio
    async def test_fda_udi_compliance(
        self, client: AsyncClient, authenticated_headers
    ):
        """Test complete FDA UDI compliance"""
        # Test all required date formats
        date_formats = [
            ("250131", "2025-01-31"),  # YYMMDD
            ("20250131", "2025-01-31"),  # YYYYMMDD
            ("25013100", "2025-01-31"),  # YYMMDDHH
        ]
        
        for date_input, expected_date in date_formats:
            response = await client.post(
                "/api/v1/devices/scan",
                json={
                    "barcode_data": f"(01)00889842001234(17){date_input}(10)LOT123"
                },
                headers=authenticated_headers
            )
            
            assert response.status_code == 200
            assert response.json()["expiry_date"] == expected_date
    
    @pytest.mark.asyncio
    async def test_international_barcode_formats(
        self, client: AsyncClient, authenticated_headers
    ):
        """Test international barcode format support"""
        formats = [
            {
                "name": "GS1-128",
                "sample": "(01)00889842001234(17)250131",
                "standard": "GS1"
            },
            {
                "name": "HIBCC",
                "sample": "=/08888420012349LOT123",
                "standard": "HIBCC"
            },
            {
                "name": "ICCBBA",
                "sample": "=)A99971234567890",
                "standard": "ICCBBA"
            },
            {
                "name": "EAN-13",
                "sample": "5901234123457",
                "standard": "GS1"
            }
        ]
        
        for format_test in formats:
            response = await client.post(
                "/api/v1/devices/scan",
                json={"barcode_data": format_test["sample"]},
                headers=authenticated_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["format_detected"] == format_test["name"]
            assert data["standard"] == format_test["standard"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
