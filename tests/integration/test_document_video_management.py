"""
Document & Video Management Tests
Based on NYELUX Test Coverage Document Section 9
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import asyncio
import hashlib
from unittest.mock import patch, MagicMock

from src.db.models.device_document import DeviceDocument
from src.db.models.device_video import DeviceVideo
from src.db.models.video_progress import VideoProgress
from src.db.models.document_chunk import DocumentChunk
from src.db.models.vendor_device import VendorDevice


class TestDocumentSystem:
    """Test cases for document upload, processing, and management"""
    
    @pytest.mark.asyncio
    async def test_document_upload_processing(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """Test document upload with format validation and processing"""
        # Create test device
        device = VendorDevice(
            gudid_device_di="DOC001",
            custom_name="Test Medical Device"
        )
        db_session.add(device)
        await db_session.commit()
        
        # Test various file formats
        test_files = [
            {
                "filename": "user_manual.pdf",
                "content": b"PDF content here",
                "mime_type": "application/pdf",
                "size": 5 * 1024 * 1024,  # 5MB
                "expected_status": 201
            },
            {
                "filename": "specifications.docx",
                "content": b"Word document content",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size": 3 * 1024 * 1024,
                "expected_status": 201
            },
            {
                "filename": "oversized.pdf",
                "content": b"x" * (51 * 1024 * 1024),  # 51MB - over limit
                "mime_type": "application/pdf",
                "size": 51 * 1024 * 1024,
                "expected_status": 413,
                "expected_error": "File size exceeds 50MB limit"
            },
            {
                "filename": "malicious.exe",
                "content": b"MZ\x90\x00",  # EXE header
                "mime_type": "application/x-msdownload",
                "size": 1024,
                "expected_status": 400,
                "expected_error": "File type not allowed"
            }
        ]
        
        for test_file in test_files:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": (test_file["filename"], test_file["content"], test_file["mime_type"])},
                data={
                    "device_id": device.id,
                    "document_type": "manual",
                    "title": f"Test {test_file['filename']}",
                    "description": "Test document upload"
                },
                headers=authenticated_headers
            )
            
            assert response.status_code == test_file["expected_status"]
            
            if test_file["expected_status"] == 201:
                # Successful upload
                data = response.json()
                assert data["id"] is not None
                assert data["file_size_bytes"] == test_file["size"]
                assert data["mime_type"] == test_file["mime_type"]
                assert data["file_hash"] is not None
                assert data["scan_status"] == "pending"  # Virus scan queued
                
                # Wait for processing
                await asyncio.sleep(2)
                
                # Check processing status
                status_response = await client.get(
                    f"/api/v1/documents/{data['id']}/status",
                    headers=authenticated_headers
                )
                
                status_data = status_response.json()
                assert status_data["scan_status"] == "clean"
                assert status_data["processing_status"] == "completed"
                assert status_data["text_extracted"] is True
                assert status_data["page_count"] > 0
                
                # Verify thumbnail generated
                assert status_data["thumbnail_url"] is not None
            else:
                # Failed upload
                assert test_file["expected_error"] in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_document_version_control(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """Test document versioning functionality"""
        # Upload initial version
        v1_response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("manual_v1.pdf", b"Version 1 content", "application/pdf")},
            data={
                "device_id": 1,
                "document_type": "manual",
                "title": "Device Manual",
                "version": "1.0"
            },
            headers=authenticated_headers
        )
        
        assert v1_response.status_code == 201
        v1_id = v1_response.json()["id"]
        
        # Upload new version
        v2_response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("manual_v2.pdf", b"Version 2 content updated", "application/pdf")},
            data={
                "device_id": 1,
                "document_type": "manual",
                "title": "Device Manual",
                "version": "2.0",
                "previous_version_id": v1_id
            },
            headers=authenticated_headers
        )
        
        assert v2_response.status_code == 201
        v2_data = v2_response.json()
        
        # Verify version linking
        assert v2_data["previous_version_id"] == v1_id
        assert v2_data["version"] == "2.0"
        assert v2_data["is_current_version"] is True
        
        # Check v1 is no longer current
        v1_check = await client.get(
            f"/api/v1/documents/{v1_id}",
            headers=authenticated_headers
        )
        
        assert v1_check.json()["is_current_version"] is False
        
        # Get version history
        history_response = await client.get(
            f"/api/v1/documents/{v2_data['id']}/versions",
            headers=authenticated_headers
        )
        
        assert history_response.status_code == 200
        versions = history_response.json()["versions"]
        
        assert len(versions) == 2
        assert versions[0]["version"] == "2.0"
        assert versions[1]["version"] == "1.0"
        
        # Test version restoration
        restore_response = await client.post(
            f"/api/v1/documents/{v1_id}/restore",
            headers=authenticated_headers
        )
        
        assert restore_response.status_code == 200
        
        # Verify v1 is now current
        v1_restored = await client.get(
            f"/api/v1/documents/{v1_id}",
            headers=authenticated_headers
        )
        
        assert v1_restored.json()["is_current_version"] is True
    
    @pytest.mark.asyncio
    async def test_document_organization(
        self, client: AsyncClient, authenticated_headers
    ):
        """Test document organization with folders and tags"""
        # Create folder structure
        root_folder = await client.post(
            "/api/v1/documents/folders",
            json={
                "name": "Device Documentation",
                "parent_id": None
            },
            headers=authenticated_headers
        )
        
        folder_id = root_folder.json()["id"]
        
        # Create subfolder
        sub_folder = await client.post(
            "/api/v1/documents/folders",
            json={
                "name": "User Manuals",
                "parent_id": folder_id
            },
            headers=authenticated_headers
        )
        
        sub_folder_id = sub_folder.json()["id"]
        
        # Upload document to folder
        doc_response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("manual.pdf", b"content", "application/pdf")},
            data={
                "title": "Quick Start Guide",
                "folder_id": sub_folder_id,
                "tags": ["training", "quick-reference", "v2.0"]
            },
            headers=authenticated_headers
        )
        
        assert doc_response.status_code == 201
        doc_id = doc_response.json()["id"]
        
        # Test folder navigation
        folder_contents = await client.get(
            f"/api/v1/documents/folders/{sub_folder_id}/contents",
            headers=authenticated_headers
        )
        
        assert folder_contents.status_code == 200
        contents = folder_contents.json()
        
        assert len(contents["documents"]) == 1
        assert contents["documents"][0]["id"] == doc_id
        
        # Test tag search
        tag_search = await client.get(
            "/api/v1/documents/search?tags=training,v2.0",
            headers=authenticated_headers
        )
        
        assert tag_search.status_code == 200
        results = tag_search.json()["results"]
        
        assert len(results) > 0
        assert doc_id in [r["id"] for r in results]


class TestVideoProcessing:
    """Test video upload, processing, and streaming"""
    
    @pytest.mark.asyncio
    async def test_video_processing_pipeline(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """Test video upload and transcoding pipeline"""
        # Create test device
        device = VendorDevice(
            gudid_device_di="VID001",
            custom_name="Video Test Device"
        )
        db_session.add(device)
        await db_session.commit()
        
        # Upload video
        video_content = b"fake_video_content" * 1000  # Simulate video file
        
        upload_response = await client.post(
            "/api/v1/videos/upload",
            files={"file": ("training_video.mp4", video_content, "video/mp4")},
            data={
                "device_id": device.id,
                "video_type": "training",
                "title": "Device Operation Training",
                "description": "Complete training on device operation",
                "duration_seconds": 1800,  # 30 minutes
                "instructor_name": "Dr. Smith",
                "skill_level": "beginner",
                "ceu_credits": 1.5
            },
            headers=authenticated_headers
        )
        
        assert upload_response.status_code == 201
        video_data = upload_response.json()
        video_id = video_data["id"]
        
        assert video_data["processing_status"] == "queued"
        
        # Wait for processing (mocked in test)
        await asyncio.sleep(3)
        
        # Check processing status
        status_response = await client.get(
            f"/api/v1/videos/{video_id}/status",
            headers=authenticated_headers
        )
        
        status = status_response.json()
        assert status["processing_status"] == "completed"
        assert status["formats_available"] == ["360p", "720p", "1080p"]
        assert status["hls_playlist_ready"] is True
        assert status["thumbnail_generated"] is True
        
        # Test HLS playlist retrieval
        playlist_response = await client.get(
            f"/api/v1/videos/{video_id}/playlist.m3u8",
            headers=authenticated_headers
        )
        
        assert playlist_response.status_code == 200
        assert "EXTM3U" in playlist_response.text
        assert "#EXT-X-STREAM-INF" in playlist_response.text
        
        # Test adaptive bitrate info
        assert "BANDWIDTH=800000" in playlist_response.text  # 360p
        assert "BANDWIDTH=2500000" in playlist_response.text  # 720p
        assert "BANDWIDTH=5000000" in playlist_response.text  # 1080p
    
    @pytest.mark.asyncio
    async def test_video_progress_tracking(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """Test video viewing progress and completion tracking"""
        # Get test video
        video_response = await client.get(
            "/api/v1/videos?limit=1",
            headers=authenticated_headers
        )
        
        video_id = video_response.json()["results"][0]["id"]
        
        # Start watching
        start_response = await client.post(
            f"/api/v1/videos/{video_id}/progress",
            json={
                "action": "start",
                "position_seconds": 0
            },
            headers=authenticated_headers
        )
        
        assert start_response.status_code == 200
        
        # Update progress multiple times
        progress_updates = [
            {"position": 300, "percentage": 16.7},   # 5 minutes
            {"position": 900, "percentage": 50.0},   # 15 minutes
            {"position": 1500, "percentage": 83.3},  # 25 minutes
            {"position": 1800, "percentage": 100.0}  # 30 minutes (complete)
        ]
        
        for update in progress_updates:
            response = await client.put(
                f"/api/v1/videos/{video_id}/progress",
                json={
                    "position_seconds": update["position"],
                    "watch_percentage": update["percentage"]
                },
                headers=authenticated_headers
            )
            
            assert response.status_code == 200
            
            # Small delay between updates
            await asyncio.sleep(0.5)
        
        # Check final progress
        progress_response = await client.get(
            f"/api/v1/videos/{video_id}/progress",
            headers=authenticated_headers
        )
        
        progress_data = progress_response.json()
        assert progress_data["completed"] is True
        assert progress_data["watch_percentage"] == 100.0
        assert progress_data["last_position_seconds"] == 1800
        
        # Verify completion certificate available
        assert progress_data["certificate_available"] is True
        
        # Download certificate
        cert_response = await client.get(
            f"/api/v1/videos/{video_id}/certificate",
            headers=authenticated_headers
        )
        
        assert cert_response.status_code == 200
        assert cert_response.headers["content-type"] == "application/pdf"
        
        # Test resume functionality
        resume_response = await client.get(
            f"/api/v1/videos/{video_id}/resume-position",
            headers=authenticated_headers
        )
        
        assert resume_response.status_code == 200
        assert resume_response.json()["position_seconds"] == 1800
        assert resume_response.json()["completed"] is True
    
    @pytest.mark.asyncio
    async def test_video_learning_features(
        self, client: AsyncClient, authenticated_headers
    ):
        """Test video learning features: quizzes, bookmarks, notes"""
        video_id = 1  # Assume test video exists
        
        # Add bookmark
        bookmark_response = await client.post(
            f"/api/v1/videos/{video_id}/bookmarks",
            json={
                "position_seconds": 425,
                "title": "Important safety procedure",
                "notes": "Review this section before exam"
            },
            headers=authenticated_headers
        )
        
        assert bookmark_response.status_code == 201
        
        # Add video note
        note_response = await client.post(
            f"/api/v1/videos/{video_id}/notes",
            json={
                "position_seconds": 612,
                "content": "Alternative method mentioned by instructor"
            },
            headers=authenticated_headers
        )
        
        assert note_response.status_code == 201
        
        # Get all bookmarks and notes
        annotations_response = await client.get(
            f"/api/v1/videos/{video_id}/annotations",
            headers=authenticated_headers
        )
        
        annotations = annotations_response.json()
        assert len(annotations["bookmarks"]) >= 1
        assert len(annotations["notes"]) >= 1
        
        # Test chapter navigation
        chapters_response = await client.get(
            f"/api/v1/videos/{video_id}/chapters",
            headers=authenticated_headers
        )
        
        chapters = chapters_response.json()["chapters"]
        assert len(chapters) > 0
        
        for chapter in chapters:
            assert "title" in chapter
            assert "start_time" in chapter
            assert "duration" in chapter
        
        # Test quiz functionality
        quiz_response = await client.get(
            f"/api/v1/videos/{video_id}/quiz",
            headers=authenticated_headers
        )
        
        if quiz_response.status_code == 200:
            quiz = quiz_response.json()
            
            # Submit quiz answers
            answers = [
                {"question_id": q["id"], "answer": q["options"][0]["id"]}
                for q in quiz["questions"]
            ]
            
            submit_response = await client.post(
                f"/api/v1/videos/{video_id}/quiz/submit",
                json={"answers": answers},
                headers=authenticated_headers
            )
            
            assert submit_response.status_code == 200
            results = submit_response.json()
            
            assert "score" in results
            assert "passed" in results
            assert results["certificate_issued"] == results["passed"]
    
    @pytest.mark.asyncio
    async def test_video_analytics(
        self, client: AsyncClient, admin_headers
    ):
        """Test video analytics and engagement metrics"""
        video_id = 1
        
        # Get video analytics
        analytics_response = await client.get(
            f"/api/v1/videos/{video_id}/analytics",
            params={
                "start_date": (datetime.utcnow() - timedelta(days=30)).isoformat(),
                "end_date": datetime.utcnow().isoformat()
            },
            headers=admin_headers
        )
        
        assert analytics_response.status_code == 200
        analytics = analytics_response.json()
        
        # Verify metrics
        assert analytics["total_views"] >= 0
        assert analytics["unique_viewers"] >= 0
        assert analytics["average_watch_percentage"] >= 0
        assert analytics["completion_rate"] >= 0
        assert analytics["total_watch_time_hours"] >= 0
        
        # Check engagement graph
        assert "engagement_graph" in analytics
        assert len(analytics["engagement_graph"]) > 0
        
        for point in analytics["engagement_graph"]:
            assert "position_seconds" in point
            assert "retention_percentage" in point
            
        # Verify drop-off points identified
        assert "significant_drop_offs" in analytics
        for drop_off in analytics["significant_drop_offs"]:
            assert "position_seconds" in drop_off
            assert "percentage_lost" in drop_off
        
        # Get aggregated analytics for all training videos
        aggregate_response = await client.get(
            "/api/v1/videos/analytics/aggregate",
            params={
                "video_type": "training",
                "group_by": "skill_level"
            },
            headers=admin_headers
        )
        
        assert aggregate_response.status_code == 200
        aggregate_data = aggregate_response.json()
        
        assert "by_skill_level" in aggregate_data
        for level in ["beginner", "intermediate", "advanced"]:
            if level in aggregate_data["by_skill_level"]:
                level_data = aggregate_data["by_skill_level"][level]
                assert "average_completion_rate" in level_data
                assert "total_videos" in level_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
