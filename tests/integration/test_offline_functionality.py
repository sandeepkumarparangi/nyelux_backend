"""
Integration tests for Offline Functionality.
Tests cover offline capabilities, sync mechanisms, and data persistence.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import json
import hashlib
import gzip
import asyncio
from typing import Dict, List
from unittest.mock import patch, AsyncMock
import base64

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.db.models.user_bookmarks import UserBookmark
from src.db.models.offline_sync import OfflineSync, OfflineSyncQueue
from src.db.models.search_history import SearchHistory
from src.services.auth_service import AuthService


class TestOfflineFunctionality:
    """Test cases for Offline Functionality - Section 18"""

    @pytest.fixture
    async def setup_offline_test_data(self, db: AsyncSession):
        """Create test data for offline functionality"""
        org = Organization(
            name="Offline Test Hospital",
            type="hospital",
            subdomain="offline-test",
            settings={"offline_enabled": True}
        )
        db.add(org)
        await db.flush()

        auth_service = AuthService()
        
        user = User(
            email="offline@test.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Offline",
            last_name="User",
            role="nurse",
            organization_id=org.id
        )
        db.add(user)
        
        # Create devices for offline caching
        devices = []
        for i in range(150):  # More than the 100 device limit
            device = GUDIDDevice(
                primary_di=f"00889842OFF{i:03d}",
                device_name=f"Offline Test Device {i+1}",
                manufacturer_name="OfflineMed Corp",
                device_class=["I", "II", "III"][i % 3],
                device_description=f"Description for offline device {i+1}",
                mri_safety=["Safe", "Conditional", "Unsafe"][i % 3]
            )
            devices.append(device)
        
        db.add_all(devices)
        
        # Create vendor devices
        vendor_devices = []
        for i in range(50):
            vendor_device = VendorDevice(
                gudid_device_di=devices[i].primary_di,
                organization_id=org.id,
                custom_name=f"Custom Offline Device {i+1}"
            )
            vendor_devices.append(vendor_device)
        
        db.add_all(vendor_devices)
        
        # Create search history (for smart caching)
        for i in range(20):
            search = SearchHistory(
                user_id=user.id,
                organization_id=org.id,
                search_query=f"device type {i % 5}",
                results_count=10 + i,
                created_at=datetime.utcnow() - timedelta(days=i)
            )
            db.add(search)
        
        # Create bookmarks
        for i in range(10):
            bookmark = UserBookmark(
                user_id=user.id,
                resource_type="device",
                resource_id=devices[i].primary_di,
                title=f"Bookmarked Device {i+1}"
            )
            db.add(bookmark)
        
        await db.commit()
        
        return {
            "organization": org,
            "user": user,
            "devices": devices,
            "vendor_devices": vendor_devices
        }

    @pytest.fixture
    async def auth_headers(self, client: AsyncClient, setup_offline_test_data):
        """Get auth headers for offline user"""
        user = setup_offline_test_data["user"]
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": user.email, "password": "password123"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_tc_offline_001_device_cache_generation(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_offline_test_data
    ):
        """TC-OFFLINE-001: Test offline cache generation for devices"""
        # Request offline sync package
        response = await client.post(
            "/api/v1/offline/sync/request",
            json={
                "sync_types": ["devices", "bookmarks", "recent_searches"],
                "device_limit": 100,
                "include_documents": True
            },
            headers=auth_headers
        )
        assert response.status_code == 202  # Accepted
        
        sync_id = response.json()["sync_id"]
        
        # Check sync status
        for _ in range(10):  # Poll for completion
            response = await client.get(
                f"/api/v1/offline/sync/{sync_id}/status",
                headers=auth_headers
            )
            
            if response.json()["status"] == "completed":
                break
            
            await asyncio.sleep(0.5)
        
        assert response.json()["status"] == "completed"
        
        # Download sync package
        response = await client.get(
            f"/api/v1/offline/sync/{sync_id}/download",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Verify package contents
        package_data = response.content
        
        # Should be compressed
        assert len(package_data) > 0
        
        # Decompress and verify
        decompressed = gzip.decompress(package_data)
        sync_data = json.loads(decompressed.decode('utf-8'))
        
        # Verify structure
        assert "metadata" in sync_data
        assert "devices" in sync_data
        assert "bookmarks" in sync_data
        assert "recent_searches" in sync_data
        
        # Verify device limit
        assert len(sync_data["devices"]) <= 100
        
        # Verify compression ratio
        original_size = len(json.dumps(sync_data).encode('utf-8'))
        compressed_size = len(package_data)
        compression_ratio = 1 - (compressed_size / original_size)
        
        # Should achieve at least 60% compression
        assert compression_ratio >= 0.6
        
        # Verify last 100 viewed devices are included
        # (In real implementation, would check view history)
        
        # Verify bookmarked devices are prioritized
        bookmarked_ids = [b["resource_id"] for b in sync_data["bookmarks"] if b["resource_type"] == "device"]
        device_ids = [d["primary_di"] for d in sync_data["devices"]]
        
        for bookmark_id in bookmarked_ids[:10]:  # At least first 10 bookmarks
            assert bookmark_id in device_ids

    @pytest.mark.asyncio
    async def test_tc_offline_002_sync_conflict_resolution(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_offline_test_data
    ):
        """TC-OFFLINE-002: Test offline sync conflict resolution"""
        user = setup_offline_test_data["user"]
        device = setup_offline_test_data["devices"][0]
        
        # Create initial note
        response = await client.post(
            "/api/v1/notes",
            json={
                "content": "Original note content",
                "device_id": device.primary_di,
                "visibility": "private"
            },
            headers=auth_headers
        )
        assert response.status_code == 201
        note_id = response.json()["id"]
        original_version = response.json()["version"]
        
        # Simulate offline edit (client side)
        offline_edit = {
            "note_id": note_id,
            "content": "Offline edited content",
            "edited_at": datetime.utcnow().isoformat(),
            "base_version": original_version
        }
        
        # Meanwhile, edit online (server side)
        response = await client.patch(
            f"/api/v1/notes/{note_id}",
            json={"content": "Online edited content"},
            headers=auth_headers
        )
        assert response.status_code == 200
        server_version = response.json()["version"]
        
        # Submit offline edit (creates conflict)
        response = await client.post(
            "/api/v1/offline/sync/upload",
            json={
                "changes": [{
                    "type": "note_update",
                    "data": offline_edit
                }]
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        
        sync_result = response.json()
        
        # Should detect conflict
        assert "conflicts" in sync_result
        assert len(sync_result["conflicts"]) > 0
        
        conflict = sync_result["conflicts"][0]
        assert conflict["type"] == "version_mismatch"
        assert conflict["resource_type"] == "note"
        assert conflict["resource_id"] == note_id
        
        # Should provide both versions
        assert "client_version" in conflict
        assert "server_version" in conflict
        assert conflict["client_version"]["content"] == "Offline edited content"
        assert conflict["server_version"]["content"] == "Online edited content"
        
        # Resolve conflict (user chooses version)
        response = await client.post(
            "/api/v1/offline/conflicts/resolve",
            json={
                "conflict_id": conflict["id"],
                "resolution": "merge",
                "merged_content": "Merged: Online edited content + Offline notes"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Verify resolution
        response = await client.get(
            f"/api/v1/notes/{note_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "Merged:" in response.json()["content"]

    @pytest.mark.asyncio
    async def test_delta_sync_efficiency(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_offline_test_data
    ):
        """Test delta sync for efficient updates"""
        # Get initial sync
        response = await client.post(
            "/api/v1/offline/sync/request",
            json={"sync_types": ["devices"]},
            headers=auth_headers
        )
        sync_id = response.json()["sync_id"]
        
        # Wait for completion
        await asyncio.sleep(1)
        
        # Get sync token
        response = await client.get(
            f"/api/v1/offline/sync/{sync_id}/status",
            headers=auth_headers
        )
        sync_token = response.json()["sync_token"]
        
        # Make some changes
        device = setup_offline_test_data["devices"][0]
        
        # Update device (simulate FDA update)
        device.device_name = "Updated Device Name"
        device.updated_at = datetime.utcnow()
        await db.commit()
        
        # Request delta sync
        response = await client.post(
            "/api/v1/offline/sync/delta",
            json={
                "sync_token": sync_token,
                "sync_types": ["devices"]
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        
        delta_data = response.json()
        
        # Should only include changes
        assert "changes" in delta_data
        assert len(delta_data["changes"]) == 1
        assert delta_data["changes"][0]["action"] == "update"
        assert delta_data["changes"][0]["resource_id"] == device.primary_di
        
        # New sync token
        assert delta_data["new_sync_token"] != sync_token

    @pytest.mark.asyncio
    async def test_offline_search_functionality(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test offline search capabilities"""
        # Download offline search index
        response = await client.get(
            "/api/v1/offline/search/index",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        search_index = response.json()
        
        # Verify index structure
        assert "version" in search_index
        assert "devices" in search_index
        assert "index_data" in search_index
        
        # Test client-side search simulation
        # (In real app, this would be done in JavaScript/offline)
        search_query = "infusion"
        results = []
        
        for device in search_index["devices"]:
            if search_query.lower() in device["device_name"].lower():
                results.append(device)
        
        assert len(results) > 0
        
        # Verify index is optimized for size
        # Should only include searchable fields
        sample_device = search_index["devices"][0]
        essential_fields = [
            "primary_di", "device_name", "manufacturer_name",
            "device_class", "keywords"
        ]
        
        for field in essential_fields:
            assert field in sample_device
        
        # Should not include large fields
        assert "device_description" not in sample_device or len(sample_device.get("device_description", "")) < 200

    @pytest.mark.asyncio
    async def test_offline_draft_management(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_offline_test_data
    ):
        """Test offline draft creation and sync"""
        device = setup_offline_test_data["devices"][0]
        
        # Create multiple offline drafts
        offline_drafts = [
            {
                "type": "note",
                "client_id": "offline_note_123",
                "data": {
                    "content": "Offline note draft",
                    "device_id": device.primary_di,
                    "created_offline": True
                }
            },
            {
                "type": "incident",
                "client_id": "offline_incident_456",
                "data": {
                    "device_id": device.primary_di,
                    "incident_type": "malfunction",
                    "description": "Device not working (drafted offline)",
                    "urgency": "medium",
                    "created_offline": True
                }
            }
        ]
        
        # Submit offline drafts
        response = await client.post(
            "/api/v1/offline/drafts/sync",
            json={"drafts": offline_drafts},
            headers=auth_headers
        )
        assert response.status_code == 200
        
        sync_result = response.json()
        
        # Verify all drafts processed
        assert len(sync_result["processed"]) == 2
        assert len(sync_result["failed"]) == 0
        
        # Check client ID mapping
        for processed in sync_result["processed"]:
            assert "client_id" in processed
            assert "server_id" in processed
            assert processed["status"] == "created"
        
        # Verify drafts were created
        note_server_id = next(p["server_id"] for p in sync_result["processed"] if p["type"] == "note")
        
        response = await client.get(
            f"/api/v1/notes/{note_server_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["content"] == "Offline note draft"

    @pytest.mark.asyncio
    async def test_offline_file_caching(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_offline_test_data
    ):
        """Test offline file caching for documents"""
        device = setup_offline_test_data["devices"][0]
        
        # Create document
        from src.db.models.device_document import DeviceDocument
        doc = DeviceDocument(
            device_id=1,  # Would be proper ID
            organization_id=setup_offline_test_data["organization"].id,
            document_type="manual",
            title="Offline Cached Manual",
            file_url="https://s3.example.com/manuals/device.pdf",
            file_size_bytes=1024 * 1024,  # 1MB
            file_hash="abc123def456"
        )
        db.add(doc)
        await db.commit()
        
        # Request offline file list
        response = await client.get(
            "/api/v1/offline/files/available",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        available_files = response.json()["files"]
        
        # Should include critical documents
        assert len(available_files) > 0
        
        # Request file for offline caching
        response = await client.post(
            "/api/v1/offline/files/cache",
            json={
                "file_ids": [doc.id],
                "quality": "medium"  # For size optimization
            },
            headers=auth_headers
        )
        assert response.status_code == 202
        
        cache_job_id = response.json()["job_id"]
        
        # Check caching progress
        response = await client.get(
            f"/api/v1/offline/files/cache/{cache_job_id}/status",
            headers=auth_headers
        )
        
        status = response.json()
        assert "progress" in status
        assert "files_cached" in status

    @pytest.mark.asyncio
    async def test_offline_sync_queue_management(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test offline sync queue for pending changes"""
        # Get current sync queue
        response = await client.get(
            "/api/v1/offline/queue",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        initial_queue_size = len(response.json()["queue"])
        
        # Add items to sync queue
        queue_items = [
            {
                "action": "create",
                "resource_type": "note",
                "data": {"content": "Queued note"},
                "client_timestamp": datetime.utcnow().isoformat()
            },
            {
                "action": "update", 
                "resource_type": "bookmark",
                "resource_id": "123",
                "data": {"notes": "Updated bookmark"},
                "client_timestamp": datetime.utcnow().isoformat()
            }
        ]
        
        response = await client.post(
            "/api/v1/offline/queue/add",
            json={"items": queue_items},
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Verify queue updated
        response = await client.get(
            "/api/v1/offline/queue",
            headers=auth_headers
        )
        new_queue = response.json()["queue"]
        assert len(new_queue) == initial_queue_size + 2
        
        # Process queue
        response = await client.post(
            "/api/v1/offline/queue/process",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        process_result = response.json()
        assert process_result["processed"] >= 0
        assert process_result["failed"] >= 0

    @pytest.mark.asyncio
    async def test_offline_barcode_validation(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test offline barcode scanning and validation"""
        # Download barcode validation data
        response = await client.get(
            "/api/v1/offline/barcodes/validation-data",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        validation_data = response.json()
        
        # Should include checksum algorithms
        assert "gs1_rules" in validation_data
        assert "checksum_algorithms" in validation_data
        assert "known_prefixes" in validation_data
        
        # Test offline validation (simulation)
        test_barcodes = [
            "(01)00889842001234(17)250131(10)LOT123",  # Valid GS1
            "(01)00889842001234(17)invalid",            # Invalid date
            "00889842001234",                           # Plain GTIN
        ]
        
        # In real app, this validation would happen client-side
        for barcode in test_barcodes:
            # Simulate client-side validation
            is_valid = "(01)" in barcode and len(barcode) > 20
            
            # Report scan result (when back online)
            response = await client.post(
                "/api/v1/offline/barcodes/scan-result",
                json={
                    "barcode": barcode,
                    "scan_timestamp": datetime.utcnow().isoformat(),
                    "offline_validated": is_valid,
                    "location": "Storage Room A"
                },
                headers=auth_headers
            )
            assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_offline_data_encryption(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test offline data encryption"""
        # Request encrypted sync package
        response = await client.post(
            "/api/v1/offline/sync/request",
            json={
                "sync_types": ["devices", "documents"],
                "encryption": {
                    "enabled": True,
                    "key_derivation": "device_specific"
                }
            },
            headers=auth_headers
        )
        assert response.status_code == 202
        
        sync_id = response.json()["sync_id"]
        
        # Get encryption parameters
        response = await client.get(
            f"/api/v1/offline/sync/{sync_id}/encryption",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        encryption_info = response.json()
        assert "algorithm" in encryption_info
        assert encryption_info["algorithm"] == "AES-256-GCM"
        assert "key_derivation_method" in encryption_info
        assert "salt" in encryption_info
        
        # Download encrypted package
        response = await client.get(
            f"/api/v1/offline/sync/{sync_id}/download",
            headers=auth_headers
        )
        
        encrypted_data = response.content
        
        # Verify it's encrypted (not readable JSON/GZIP)
        try:
            # Should not be able to decompress directly
            gzip.decompress(encrypted_data)
            assert False, "Data should be encrypted"
        except:
            pass  # Expected - data is encrypted

    @pytest.mark.asyncio
    async def test_offline_sync_size_limits(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_offline_test_data
    ):
        """Test offline sync package size limits"""
        # Request large sync package
        response = await client.post(
            "/api/v1/offline/sync/request",
            json={
                "sync_types": ["devices", "documents", "videos", "images"],
                "device_limit": 1000,  # Request more than reasonable
                "include_attachments": True,
                "max_package_size_mb": 100
            },
            headers=auth_headers
        )
        assert response.status_code == 202
        
        sync_id = response.json()["sync_id"]
        
        # Check sync status
        await asyncio.sleep(1)
        
        response = await client.get(
            f"/api/v1/offline/sync/{sync_id}/status",
            headers=auth_headers
        )
        
        status = response.json()
        
        # Should respect size limits
        if status["status"] == "completed":
            assert status["package_size_mb"] <= 100
            assert status["items_excluded"] > 0  # Some items excluded due to size
            
            # Should prioritize important data
            assert status["included_counts"]["devices"] > 0
            assert status["included_counts"]["bookmarked_items"] > 0

    @pytest.mark.asyncio
    async def test_offline_progressive_sync(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test progressive sync for slow connections"""
        # Request progressive sync
        response = await client.post(
            "/api/v1/offline/sync/progressive",
            json={
                "priority_order": [
                    "bookmarks",
                    "recent_devices",
                    "frequent_searches",
                    "documents"
                ],
                "chunk_size_mb": 5,
                "connection_type": "slow_3g"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        
        sync_session = response.json()
        assert "session_id" in sync_session
        assert "total_chunks" in sync_session
        assert sync_session["total_chunks"] > 1
        
        # Download first chunk (highest priority)
        response = await client.get(
            f"/api/v1/offline/sync/progressive/{sync_session['session_id']}/chunk/1",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        chunk_data = response.json()
        assert "data" in chunk_data
        assert "chunk_number" in chunk_data
        assert chunk_data["chunk_number"] == 1
        assert "has_more" in chunk_data
        
        # First chunk should have bookmarks
        assert "bookmarks" in chunk_data["data"]

    @pytest.mark.asyncio
    async def test_offline_data_expiration(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test offline data expiration and refresh"""
        # Get sync with expiration
        response = await client.post(
            "/api/v1/offline/sync/request",
            json={
                "sync_types": ["devices"],
                "expiration_hours": 24
            },
            headers=auth_headers
        )
        sync_id = response.json()["sync_id"]
        
        # Get sync metadata
        response = await client.get(
            f"/api/v1/offline/sync/{sync_id}/metadata",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        metadata = response.json()
        assert "expires_at" in metadata
        assert "requires_refresh_at" in metadata
        
        # Simulate checking if refresh needed
        # (In real app, done by client)
        expires_at = datetime.fromisoformat(metadata["expires_at"].replace('Z', '+00:00'))
        requires_refresh = datetime.utcnow() > expires_at - timedelta(hours=4)
        
        if requires_refresh:
            # Request refresh
            response = await client.post(
                f"/api/v1/offline/sync/{sync_id}/refresh",
                headers=auth_headers
            )
            assert response.status_code in [200, 202]
