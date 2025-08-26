"""
Device Management & Search Tests
Based on NYELUX Test Coverage Document Section 3
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import asyncio
import hashlib
from unittest.mock import patch, MagicMock

from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.db.models.organization import Organization
from src.etl.gudid_sync import GUDIDETLService as GUDIDSyncService


class TestGUDIDSynchronization:
    """Test cases TC-DEVICE-001 through TC-DEVICE-003"""
    
    @pytest.mark.asyncio
    async def test_daily_fda_sync_success(
        self, db_session: AsyncSession, monkeypatch
    ):
        """TC-DEVICE-001: Daily FDA Sync Success"""
        # Mock FDA download
        mock_fda_data = self._generate_mock_fda_data(1000)  # Smaller set for testing
        
        def mock_download_fda_data():
            return mock_fda_data
        
        sync_service = GUDIDSyncService(db_session)
        monkeypatch.setattr(sync_service, "_download_fda_data", mock_download_fda_data)
        
        # Record start time
        start_time = datetime.utcnow()
        
        # Run sync
        result = await sync_service.run_daily_sync()
        
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Assertions
        assert result["status"] == "success"
        assert result["records_processed"] == 1000
        assert result["records_added"] > 0
        assert result["records_updated"] >= 0
        assert result["errors"] == 0
        assert duration < 1800  # Less than 30 minutes (scaled for test data)
        
        # Verify data integrity
        device_count = await db_session.execute(
            "SELECT COUNT(*) FROM gudid_devices"
        )
        assert device_count.scalar() == 1000
        
        # Verify search vectors generated
        vectors = await db_session.execute(
            "SELECT COUNT(*) FROM gudid_devices WHERE search_vector IS NOT NULL"
        )
        assert vectors.scalar() == 1000
        
        # Verify indexes updated
        # In real implementation, check pg_stat_user_indexes
    
    @pytest.mark.asyncio
    async def test_incremental_update_detection(
        self, db_session: AsyncSession, monkeypatch
    ):
        """TC-DEVICE-002: Incremental Update Detection"""
        sync_service = GUDIDSyncService(db_session)
        
        # Initial sync with 100 devices
        initial_data = self._generate_mock_fda_data(100)
        monkeypatch.setattr(sync_service, "_download_fda_data", lambda: initial_data)
        
        result1 = await sync_service.run_daily_sync()
        assert result1["records_added"] == 100
        assert result1["records_updated"] == 0
        
        # Modify 10 devices, add 5 new ones
        updated_data = initial_data.copy()
        for i in range(10):
            updated_data[i]["device_name"] += " UPDATED"
            updated_data[i]["version"] += 1
        
        for i in range(5):
            updated_data.append({
                "primary_di": f"NEW{i:06d}",
                "device_name": f"New Device {i}",
                "manufacturer_name": "NewCorp",
                "version": 1
            })
        
        monkeypatch.setattr(sync_service, "_download_fda_data", lambda: updated_data)
        
        # Run incremental sync
        result2 = await sync_service.run_daily_sync()
        
        # Verify incremental updates
        assert result2["records_processed"] == 105
        assert result2["records_added"] == 5
        assert result2["records_updated"] == 10
        assert result2["records_unchanged"] == 90
    
    @pytest.mark.asyncio
    async def test_fda_site_unavailable(
        self, db_session: AsyncSession, monkeypatch
    ):
        """TC-DEVICE-003: FDA Site Unavailable"""
        sync_service = GUDIDSyncService(db_session)
        
        # Add some existing data
        for i in range(10):
            device = GUDIDDevice(
                primary_di=f"EXISTING{i:06d}",
                device_name=f"Existing Device {i}",
                manufacturer_name="ExistingCorp"
            )
            db_session.add(device)
        await db_session.commit()
        
        # Mock FDA download failure
        attempt_count = 0
        def mock_failing_download():
            nonlocal attempt_count
            attempt_count += 1
            raise Exception("FDA site unavailable")
        
        monkeypatch.setattr(sync_service, "_download_fda_data", mock_failing_download)
        
        # Mock alert service
        alerts_sent = []
        def mock_send_alert(message):
            alerts_sent.append(message)
        
        monkeypatch.setattr(sync_service, "_send_admin_alert", mock_send_alert)
        
        # Run sync
        result = await sync_service.run_daily_sync()
        
        # Verify retry behavior
        assert attempt_count == 3  # 3 retry attempts
        assert result["status"] == "failed"
        assert "FDA site unavailable" in result["error"]
        
        # Verify alert sent
        assert len(alerts_sent) == 1
        assert "FDA sync failed" in alerts_sent[0]
        
        # Verify existing data remains valid
        device_count = await db_session.execute(
            "SELECT COUNT(*) FROM gudid_devices"
        )
        assert device_count.scalar() == 10  # Original data intact
    
    def _generate_mock_fda_data(self, count):
        """Generate mock FDA device data"""
        data = []
        for i in range(count):
            data.append({
                "primary_di": f"TEST{i:010d}",
                "device_name": f"Test Device {i}",
                "manufacturer_name": f"Manufacturer {i % 100}",
                "device_class": ["I", "II", "III"][i % 3],
                "gmdn_terms": f"Category {i % 50}",
                "mri_safety": ["MR Safe", "MR Conditional", "MR Unsafe"][i % 3],
                "sterile": i % 2 == 0,
                "implantable": i % 10 == 0,
                "version": 1
            })
        return data


class TestDeviceSearch:
    """Test cases TC-DEVICE-004 through TC-DEVICE-007"""
    
    @pytest.mark.asyncio
    async def test_search_performance_under_load(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-DEVICE-004: Search Performance Under Load"""
        # Create realistic test data (subset of 4.8M)
        print("Creating test devices...")
        devices = []
        for i in range(10000):  # Reduced for test performance
            device = GUDIDDevice(
                primary_di=f"PERF{i:010d}",
                device_name=f"Device {i} {'Infusion Pump' if i % 100 == 0 else 'Catheter' if i % 50 == 0 else 'Stent'}",
                manufacturer_name=f"Manufacturer {i % 500}",
                device_class=["I", "II", "III"][i % 3],
                mri_safety=["MR Safe", "MR Conditional", "MR Unsafe", None][i % 4],
                sterile=i % 2 == 0
            )
            devices.append(device)
            
            if len(devices) >= 1000:
                db_session.add_all(devices)
                await db_session.commit()
                devices = []
        
        if devices:
            db_session.add_all(devices)
            await db_session.commit()
        
        # Generate search queries
        search_queries = [
            "infusion pump",
            "catheter",
            "stent",
            "Manufacturer 123",
            "MRI safe devices",
            "class II sterile",
            "implantable",
            "PERF0001234567"
        ]
        
        # Run concurrent searches
        response_times = []
        
        async def run_search(query):
            start = datetime.utcnow()
            response = await client.get(
                f"/api/v1/devices/search?q={query}",
                headers={"Authorization": "Bearer valid_token"}
            )
            duration = (datetime.utcnow() - start).total_seconds() * 1000
            return response.status_code, duration
        
        # Simulate 1000 concurrent searches
        tasks = []
        for i in range(1000):
            query = search_queries[i % len(search_queries)]
            tasks.append(run_search(query))
        
        results = await asyncio.gather(*tasks)
        
        # Analyze results
        successful_searches = [r for r in results if r[0] == 200]
        response_times = [r[1] for r in successful_searches]
        response_times.sort()
        
        # Calculate percentiles
        p95 = response_times[int(len(response_times) * 0.95)]
        p99 = response_times[int(len(response_times) * 0.99)]
        
        # Assertions
        assert len(successful_searches) == 1000  # All searches succeeded
        assert p95 < 200  # 95th percentile < 200ms
        assert p99 < 500  # 99th percentile < 500ms
        
        # Check cache hit ratio (would check Redis in real implementation)
        # assert cache_hit_ratio > 0.8
    
    @pytest.mark.asyncio
    async def test_fuzzy_search_accuracy(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-DEVICE-005: Fuzzy Search Accuracy"""
        # Create test devices with commonly misspelled names
        test_devices = [
            ("Infusion Pump Advanced", "infusion pump"),
            ("Catheter Central Venous", "catheter"),
            ("Defibrillator Cardiac", "defibrillator"),
            ("Syringe Injection System", "syringe")
        ]
        
        for name, category in test_devices:
            device = GUDIDDevice(
                primary_di=f"FUZZY{hash(name)}",
                device_name=name,
                manufacturer_name="TestCorp",
                device_class="II"
            )
            db_session.add(device)
        await db_session.commit()
        
        # Test fuzzy matching with typos
        test_cases = [
            ("infuson pump", "Infusion Pump Advanced"),      # Missing 'i'
            ("cathetir", "Catheter Central Venous"),        # Typo
            ("defibrilator", "Defibrillator Cardiac"),      # Single 'l'
            ("syrnge", "Syringe Injection System"),          # Missing 'i'
            ("infusion pmp", "Infusion Pump Advanced"),      # Missing 'u'
        ]
        
        for misspelled, expected_device in test_cases:
            response = await client.get(
                f"/api/v1/devices/search?q={misspelled}",
                headers=authenticated_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) > 0
            
            # Check if expected device is in results
            device_names = [d["device_name"] for d in data["results"]]
            assert expected_device in device_names, f"Expected '{expected_device}' in results for '{misspelled}'"
            
            # Should be in top 3 results
            assert expected_device in device_names[:3]
    
    @pytest.mark.asyncio
    async def test_multi_field_search(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-DEVICE-006: Multi-Field Search"""
        # Create specific test device
        device = GUDIDDevice(
            primary_di="MULTI123456",
            device_name="Advanced Infusion Pump X2000",
            manufacturer_name="Medtronic",
            device_class="II",
            mri_safety="MR Safe",
            sterile=True,
            implantable=False,
            device_description="Advanced programmable infusion pump with MRI safety"
        )
        db_session.add(device)
        
        # Create similar devices that should NOT match all criteria
        decoy1 = GUDIDDevice(
            primary_di="DECOY1",
            device_name="Basic Infusion Pump",
            manufacturer_name="Medtronic",
            device_class="II",
            mri_safety="MR Unsafe"  # Different MRI safety
        )
        db_session.add(decoy1)
        
        decoy2 = GUDIDDevice(
            primary_di="DECOY2",
            device_name="Advanced Infusion Pump",
            manufacturer_name="OtherCorp",  # Different manufacturer
            device_class="II",
            mri_safety="MR Safe"
        )
        db_session.add(decoy2)
        
        await db_session.commit()
        
        # Search with multiple criteria
        response = await client.get(
            "/api/v1/devices/search?q=medtronic infusion MRI safe",
            headers=authenticated_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find our specific device
        assert len(data["results"]) >= 1
        
        # Verify the correct device is returned
        found_device = None
        for device in data["results"]:
            if device["primary_di"] == "MULTI123456":
                found_device = device
                break
        
        assert found_device is not None
        assert found_device["manufacturer_name"] == "Medtronic"
        assert "infusion" in found_device["device_name"].lower()
        assert found_device["mri_safety"] == "MR Safe"
    
    @pytest.mark.asyncio
    async def test_filter_combinations(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-DEVICE-007: Filter Combinations"""
        # Create devices with various combinations
        test_devices = [
            {"device_class": "II", "sterile": True, "mri_safety": "MR Safe"},
            {"device_class": "II", "sterile": True, "mri_safety": "MR Conditional"},
            {"device_class": "II", "sterile": False, "mri_safety": "MR Safe"},
            {"device_class": "III", "sterile": True, "mri_safety": "MR Safe"},
            {"device_class": "II", "sterile": True, "mri_safety": "MR Safe", "implantable": True},
            {"device_class": "II", "sterile": True, "mri_safety": "MR Safe", "life_supporting": True},
        ]
        
        for i, attrs in enumerate(test_devices):
            device = GUDIDDevice(
                primary_di=f"FILTER{i:06d}",
                device_name=f"Filter Test Device {i}",
                manufacturer_name="FilterCorp",
                **attrs
            )
            db_session.add(device)
        await db_session.commit()
        
        # Test filter combinations
        test_cases = [
            # (filters, expected_count)
            ({"device_class": ["II"], "sterile": True}, 4),
            ({"device_class": ["II"], "sterile": True, "mri_safety": "MR Safe"}, 3),
            ({"implantable": True, "life_supporting": True}, 0),  # None match both
            ({"device_class": ["II", "III"]}, 6),  # All devices
        ]
        
        for filters, expected_count in test_cases:
            response = await client.post(
                "/api/v1/devices/search",
                json={"query": "Filter Test Device", "filters": filters},
                headers=authenticated_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == expected_count, f"Expected {expected_count} results for filters {filters}"
            
            # Verify all results match ALL filters
            for device in data["results"]:
                for key, value in filters.items():
                    if isinstance(value, list):
                        assert device.get(key) in value
                    else:
                        assert device.get(key) == value


class TestDeviceComparison:
    """Test device comparison functionality"""
    
    @pytest.mark.asyncio
    async def test_device_comparison_feature(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """Test comparing up to 5 devices side-by-side"""
        # Create test devices with different attributes
        devices = []
        for i in range(6):
            device = GUDIDDevice(
                primary_di=f"COMP{i:06d}",
                device_name=f"Comparison Device {i}",
                manufacturer_name=f"Manufacturer {i}",
                device_class=["I", "II", "III"][i % 3],
                mri_safety=["MR Safe", "MR Conditional", "MR Unsafe"][i % 3],
                sterile=i % 2 == 0,
                single_use=i % 2 == 1,
                implantable=i < 2,
                life_supporting=i < 1
            )
            devices.append(device)
            db_session.add(device)
        await db_session.commit()
        
        # Test valid comparison (5 devices)
        comparison_data = {
            "device_ids": [f"COMP{i:06d}" for i in range(5)]
        }
        
        response = await client.post(
            "/api/v1/devices/compare",
            json=comparison_data,
            headers=authenticated_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["devices"]) == 5
        assert "comparison_id" in data
        assert "attributes" in data
        
        # Verify difference highlighting
        assert "differences" in data
        assert "mri_safety" in data["differences"]  # Should be highlighted as different
        
        # Test exceeding limit (6 devices)
        comparison_data_invalid = {
            "device_ids": [f"COMP{i:06d}" for i in range(6)]
        }
        
        response2 = await client.post(
            "/api/v1/devices/compare",
            json=comparison_data_invalid,
            headers=authenticated_headers
        )
        
        assert response2.status_code == 400
        assert "Maximum 5 devices" in response2.json()["detail"]
        
        # Test export functionality
        export_response = await client.get(
            f"/api/v1/devices/compare/{data['comparison_id']}/export?format=excel",
            headers=authenticated_headers
        )
        
        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
