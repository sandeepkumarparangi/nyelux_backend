"""
Unit tests for document service using REAL services.

IMPORTANT: These tests use REAL AWS S3 and OpenAI services.
They will incur costs and create real resources.
"""
import io
from datetime import datetime
from pathlib import Path

import pytest

from src.db.models.device_document import DeviceDocument
from src.db.models.document_chunk import DocumentChunk
from src.services.document_service import DocumentService
from src.services.s3_service import get_s3_service
from src.services.ai_service import get_ai_service
from src.core.exceptions import ExternalServiceError


@pytest.mark.external
class TestDocumentServiceReal:
    """Test suite for DocumentService with REAL external services."""
    
    @pytest.fixture
    def document_service(self):
        """Create DocumentService with real dependencies."""
        return DocumentService()
    
    @pytest.fixture
    def sample_pdf_content(self):
        """Create sample PDF content."""
        # This is a minimal valid PDF structure
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n203\n%%EOF"
    
    @pytest.fixture
    async def cleanup_s3_files(self, test_s3_cleanup):
        """Track S3 files for cleanup."""
        yield test_s3_cleanup
    
    @pytest.mark.asyncio
    async def test_upload_document_real_s3(
        self, 
        document_service, 
        db_session, 
        test_vendor_device, 
        test_organization,
        test_user,
        sample_pdf_content,
        cleanup_s3_files
    ):
        """Test document upload with REAL S3 service."""
        # Create file-like object
        file = io.BytesIO(sample_pdf_content)
        
        # Upload document - this will use REAL S3
        result = await document_service.upload_document(
            db=db_session,
            file=file,
            filename="test_document.pdf",
            device_id=test_vendor_device.id,
            organization_id=test_organization.id,
            document_type="manual",
            user_id=test_user.id,
            title="Test Manual for Real S3"
        )
        
        # Track for cleanup
        cleanup_s3_files.append(result.file_key)
        
        # Verify document was created
        assert isinstance(result, DeviceDocument)
        assert result.title == "Test Manual for Real S3"
        assert result.document_type == "manual"
        assert result.file_size_bytes == len(sample_pdf_content)
        assert result.file_key.startswith(f"documents/{test_organization.id}/{test_vendor_device.id}/")
        
        # Verify file exists in S3
        s3 = get_s3_service()
        presigned_url = await s3.generate_presigned_url(result.file_key)
        assert presigned_url is not None
        assert "https://" in presigned_url
        
        # Verify document in database
        db_doc = await db_session.get(DeviceDocument, result.id)
        assert db_doc is not None
        assert db_doc.file_url is not None
    
    @pytest.mark.asyncio
    @pytest.mark.expensive  # This test uses OpenAI API
    async def test_document_chunking_with_real_embeddings(
        self,
        document_service,
        db_session,
        test_vendor_device,
        test_organization,
        test_user,
        cleanup_s3_files
    ):
        """Test document chunking with REAL embedding generation."""
        # Create a longer document for chunking
        content = b"""
        DEVICE OPERATION MANUAL
        
        Chapter 1: Introduction
        This medical device is designed for precision infusion therapy.
        It provides accurate medication delivery with advanced safety features.
        
        Chapter 2: Safety Information
        Always verify patient information before starting infusion.
        Check medication compatibility with device materials.
        Monitor for air bubbles in the line.
        
        Chapter 3: Operation Instructions
        1. Power on the device using the main switch
        2. Load the medication syringe
        3. Prime the infusion line
        4. Set the infusion rate
        5. Start the infusion
        
        Chapter 4: Maintenance
        Clean the device daily with approved disinfectants.
        Perform calibration monthly.
        Replace consumables as indicated.
        """
        
        file = io.BytesIO(content)
        
        # Upload document
        result = await document_service.upload_document(
            db=db_session,
            file=file,
            filename="operation_manual.txt",
            device_id=test_vendor_device.id,
            organization_id=test_organization.id,
            document_type="manual",
            user_id=test_user.id,
            title="Operation Manual with Embeddings",
            description="Test manual for embedding generation"
        )
        
        cleanup_s3_files.append(result.file_key)
        
        # Verify chunks were created with embeddings
        chunks = await db_session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == result.id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunk_list = chunks.scalars().all()
        
        assert len(chunk_list) > 0
        
        # Verify embeddings were generated
        for chunk in chunk_list:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1536  # OpenAI embedding dimension
            assert chunk.chunk_metadata.get("model") == "text-embedding-ada-002"
    
    @pytest.mark.asyncio
    async def test_document_search_with_real_services(
        self,
        document_service,
        db_session,
        test_vendor_device,
        test_organization,
        test_user,
        cleanup_s3_files
    ):
        """Test document search functionality."""
        # Upload multiple documents
        doc_titles = [
            "Quick Start Guide",
            "User Manual", 
            "Maintenance Guide",
            "Safety Instructions"
        ]
        
        uploaded_docs = []
        for title in doc_titles:
            content = f"This is the {title} content.".encode()
            file = io.BytesIO(content)
            
            doc = await document_service.upload_document(
                db=db_session,
                file=file,
                filename=f"{title.lower().replace(' ', '_')}.txt",
                device_id=test_vendor_device.id,
                organization_id=test_organization.id,
                document_type="manual" if "manual" in title.lower() else "quickstart",
                user_id=test_user.id,
                title=title
            )
            cleanup_s3_files.append(doc.file_key)
            uploaded_docs.append(doc)
        
        # Search documents
        results = await document_service.search_documents(
            db=db_session,
            query="guide",
            device_id=test_vendor_device.id,
            organization_id=test_organization.id,
            limit=10
        )
        
        # Verify search results
        assert len(results) >= 2  # Should find "Quick Start Guide" and "Maintenance Guide"
        guide_titles = [r["title"] for r in results if "guide" in r["title"].lower()]
        assert len(guide_titles) >= 2
    
    @pytest.mark.asyncio
    async def test_presigned_url_generation(
        self,
        document_service,
        db_session,
        test_vendor_device,
        test_organization,
        test_user,
        sample_pdf_content,
        cleanup_s3_files
    ):
        """Test presigned URL generation for secure downloads."""
        # Upload a document
        file = io.BytesIO(sample_pdf_content)
        doc = await document_service.upload_document(
            db=db_session,
            file=file,
            filename="secure_document.pdf",
            device_id=test_vendor_device.id,
            organization_id=test_organization.id,
            document_type="manual",
            user_id=test_user.id,
            title="Secure Document"
        )
        cleanup_s3_files.append(doc.file_key)
        
        # Get presigned URL
        url = await document_service.get_document_url(
            db=db_session,
            document_id=doc.id,
            user_id=test_user.id,
            organization_id=test_organization.id,
            action="download"
        )
        
        assert url is not None
        assert "https://" in url
        assert "X-Amz-Signature" in url  # AWS signature
        assert "X-Amz-Expires" in url  # Expiration time
        
        # Verify download count was incremented
        await db_session.refresh(doc)
        assert doc.download_count == 1
    
    @pytest.mark.asyncio
    async def test_virus_scanning(
        self,
        document_service,
        db_session,
        test_vendor_device,
        test_organization,
        test_user
    ):
        """Test virus scanning rejects suspicious files."""
        # Create suspicious content (executable header)
        suspicious_content = b"MZ\x90\x00\x03\x00\x00\x00\x04"  # DOS executable header
        file = io.BytesIO(suspicious_content)
        
        # Attempt upload - should fail virus scan
        with pytest.raises(ValueError, match="executable code"):
            await document_service.upload_document(
                db=db_session,
                file=file,
                filename="malware.exe",
                device_id=test_vendor_device.id,
                organization_id=test_organization.id,
                document_type="manual",
                user_id=test_user.id,
                title="Suspicious File"
            )
    
    @pytest.mark.asyncio
    async def test_large_file_handling(
        self,
        document_service,
        db_session,
        test_vendor_device,
        test_organization,
        test_user
    ):
        """Test handling of files at size limit."""
        # Create file just under limit (50MB)
        large_content = b"x" * (49 * 1024 * 1024)  # 49MB
        file = io.BytesIO(large_content)
        
        # This should succeed
        doc = await document_service.upload_document(
            db=db_session,
            file=file,
            filename="large_manual.pdf",
            device_id=test_vendor_device.id,
            organization_id=test_organization.id,
            document_type="manual",
            user_id=test_user.id,
            title="Large Manual"
        )
        
        assert doc.file_size_bytes == len(large_content)
        
        # Create file over limit
        oversized_content = b"x" * (51 * 1024 * 1024)  # 51MB
        file = io.BytesIO(oversized_content)
        
        # This should fail
        with pytest.raises(ValueError, match="File too large"):
            await document_service.upload_document(
                db=db_session,
                file=file,
                filename="oversized.pdf",
                device_id=test_vendor_device.id,
                organization_id=test_organization.id,
                document_type="manual",
                user_id=test_user.id,
                title="Oversized Manual"
            )


# Import select for queries
from sqlalchemy import select
