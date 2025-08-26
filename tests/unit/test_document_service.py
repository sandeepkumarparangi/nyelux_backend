"""
Unit tests for document service.

Tests cover file upload, validation, text extraction, chunking, and S3 integration.
"""
import io
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.db.models.device_document import DeviceDocument
from src.db.models.document_chunk import DocumentChunk
from src.db.models.vendor_device import VendorDevice
from src.services.document_service import DocumentService


class TestDocumentService:
    """Test suite for DocumentService class."""
    
    @pytest.fixture
    def mock_cache(self):
        """Create mock cache service."""
        cache = AsyncMock()
        cache.delete.return_value = True
        return cache
    
    @pytest.fixture
    def mock_s3_service(self):
        """Create mock S3 service."""
        s3 = AsyncMock()
        # Return dict as per real S3 service implementation
        s3.upload_file.return_value = {
            "success": True,
            "key": "documents/10/5/test-file.pdf",
            "url": "https://s3.example.com/test-file.pdf",
            "etag": "abc123",
            "file_hash": "def456",
            "size": 1024,
            "content_type": "application/pdf",
            "uploaded_at": "2024-01-01T00:00:00"
        }
        s3.generate_presigned_url.return_value = "https://s3.example.com/signed-url"
        return s3
    
    @pytest.fixture
    def mock_ai_service(self):
        """Create mock AI service."""
        ai = AsyncMock()
        ai.get_embedding.return_value = [0.1] * 1536  # Mock embedding vector
        return ai
    
    @pytest.fixture
    def document_service(self, mock_cache):
        """Create DocumentService with mocked dependencies."""
        service = DocumentService()
        service.cache = mock_cache
        return service
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock()
        db.get = AsyncMock()
        db.add = Mock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_vendor_device(self):
        """Create mock vendor device."""
        device = MagicMock(spec=VendorDevice)
        device.id = 1
        device.organization_id = 10
        return device
    
    @pytest.fixture
    def sample_pdf_content(self):
        """Create sample PDF content."""
        # This is a minimal valid PDF structure
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n203\n%%EOF"
    
    @pytest.mark.asyncio
    async def test_upload_document_success(
        self, document_service, mock_db, mock_vendor_device, sample_pdf_content, mock_s3_service
    ):
        """Test successful document upload."""
        # Setup mock file
        file = io.BytesIO(sample_pdf_content)
        
        # Setup database mocks
        mock_db.get.return_value = mock_vendor_device
        
        # Create a proper mock for the execute result
        mock_execute_result = AsyncMock()
        mock_execute_result.scalar_one_or_none = AsyncMock(return_value=None)  # No duplicate
        mock_db.execute.return_value = mock_execute_result
        
        # Mock text extraction and factory functions
        with patch.object(
            document_service, 
            '_extract_text', 
            return_value=("Sample PDF text content", {"page_count": 1})
        ):
            with patch('src.services.document_service.get_s3_service', return_value=mock_s3_service):
                result = await document_service.upload_document(
                    db=mock_db,
                    file=file,
                    filename="test.pdf",
                    device_id=1,
                    organization_id=10,
                    document_type="manual",
                    user_id=100,
                    title="Test Manual"
                )
        
        # Verify document was created
        assert isinstance(result, DeviceDocument)
        assert result.title == "Test Manual"
        assert result.document_type == "manual"
        assert result.file_size_bytes == len(sample_pdf_content)
        
        # Verify S3 upload was called
        document_service.cache.delete.assert_called()
        mock_db.add.assert_called()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_document_invalid_type(
        self, document_service, mock_db, sample_pdf_content
    ):
        """Test document upload with invalid document type."""
        file = io.BytesIO(sample_pdf_content)
        
        with pytest.raises(ValueError, match="Invalid document type"):
            await document_service.upload_document(
                db=mock_db,
                file=file,
                filename="test.pdf",
                device_id=1,
                organization_id=10,
                document_type="invalid_type",
                user_id=100
            )
    
    @pytest.mark.asyncio
    async def test_upload_document_device_not_found(
        self, document_service, mock_db, sample_pdf_content
    ):
        """Test document upload when device not found."""
        file = io.BytesIO(sample_pdf_content)
        
        # Mock device not found
        mock_db.get.return_value = None
        
        with pytest.raises(ValueError, match="Device not found"):
            await document_service.upload_document(
                db=mock_db,
                file=file,
                filename="test.pdf",
                device_id=999,
                organization_id=10,
                document_type="manual",
                user_id=100
            )
    
    @pytest.mark.asyncio
    async def test_upload_document_duplicate_detection(
        self, document_service, mock_db, mock_vendor_device, sample_pdf_content
    ):
        """Test duplicate document detection."""
        file = io.BytesIO(sample_pdf_content)
        
        # Setup mocks
        mock_db.get.return_value = mock_vendor_device
        
        # Mock duplicate found
        mock_existing = MagicMock()
        mock_execute_result = AsyncMock()
        mock_execute_result.scalar_one_or_none = AsyncMock(return_value=mock_existing)
        mock_db.execute.return_value = mock_execute_result
        
        with pytest.raises(ValueError, match="already been uploaded"):
            await document_service.upload_document(
                db=mock_db,
                file=file,
                filename="test.pdf",
                device_id=1,
                organization_id=10,
                document_type="manual",
                user_id=100
            )
    
    @pytest.mark.asyncio
    async def test_validate_file_size_limit(self, document_service):
        """Test file size validation."""
        # Create oversized content
        oversized_content = b"x" * (document_service.max_file_size + 1)
        
        with pytest.raises(ValueError, match="File too large"):
            await document_service._validate_file(oversized_content, "large.pdf")
    
    @pytest.mark.asyncio
    async def test_validate_file_type_allowed(self, document_service):
        """Test allowed file type validation."""
        # Mock magic mime type detection
        with patch('magic.Magic.from_buffer', return_value="application/pdf"):
            mime_type = await document_service._validate_file(b"PDF content", "test.pdf")
            assert mime_type == "application/pdf"
    
    @pytest.mark.asyncio
    async def test_validate_file_type_not_allowed(self, document_service):
        """Test disallowed file type validation."""
        # Mock magic mime type detection
        with patch('magic.Magic.from_buffer', return_value="application/x-executable"):
            with pytest.raises(ValueError, match="File type not allowed"):
                await document_service._validate_file(b"EXE content", "malware.exe")
    
    @pytest.mark.asyncio
    async def test_scan_for_viruses_clean(self, document_service):
        """Test virus scanning with clean file."""
        clean_content = b"This is a clean PDF file content"
        
        # Should not raise any exception
        await document_service._scan_for_viruses(clean_content)
    
    @pytest.mark.asyncio
    async def test_scan_for_viruses_suspicious(self, document_service):
        """Test virus scanning with suspicious content."""
        suspicious_content = b"MZ\x90\x00\x03"  # DOS executable header
        
        with pytest.raises(ValueError, match="executable code"):
            await document_service._scan_for_viruses(suspicious_content)
    
    def test_generate_s3_key(self, document_service):
        """Test S3 key generation."""
        key = document_service._generate_s3_key(
            organization_id=10,
            device_id=5,
            filename="Test Document (v2).pdf"
        )
        
        # Verify key structure
        assert key.startswith("documents/10/5/")
        assert key.endswith("_Test_Document__v2_.pdf")  # Parentheses replaced with underscores
        # Verify UUID part exists
        parts = key.split("/")[-1].split("_", 1)
        assert len(parts[0]) == 8  # UUID hex part
    
    @pytest.mark.asyncio
    async def test_extract_pdf_text(self, document_service):
        """Test PDF text extraction."""
        # Create a more complete mock PDF
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is page 1 content"
        
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader.metadata = {
            '/Title': 'Test PDF',
            '/Author': 'Test Author'
        }
        
        with patch('pypdf.PdfReader', return_value=mock_reader):
            text, metadata = await document_service._extract_pdf(
                b"PDF content", "test.pdf"
            )
        
        assert "This is page 1 content" in text
        assert metadata["page_count"] == 1
        assert metadata["pdf_metadata"]["title"] == "Test PDF"
    
    @pytest.mark.asyncio
    async def test_extract_docx_text(self, document_service):
        """Test Word document text extraction."""
        # Create a simple mock that bypasses Document initialization
        with patch('src.services.document_service.DocxDocument') as mock_docx_class:
            # Mock document instance
            mock_doc = MagicMock()
            mock_para1 = MagicMock()
            mock_para1.text = "First paragraph"
            mock_para2 = MagicMock()
            mock_para2.text = "Second paragraph"
            
            mock_doc.paragraphs = [mock_para1, mock_para2]
            mock_doc.tables = []
            mock_doc.inline_shapes = []
            mock_doc.core_properties = MagicMock(
                title="Test Doc",
                author="Test Author",
                subject=None,
                keywords=None,
                created=datetime.now(),
                modified=datetime.now()
            )
            
            # Make the class return our mock instance
            mock_docx_class.return_value = mock_doc
            
            # Create large enough content to pass size check
            docx_content = b"PK" + b"x" * 200  # Fake ZIP content
            
            text, metadata = await document_service._extract_docx(
                docx_content, "test.docx"
            )
        
        assert "First paragraph" in text
        assert "Second paragraph" in text
        assert metadata["has_tables"] is False
    
    @pytest.mark.asyncio
    async def test_extract_image_text_ocr(self, document_service):
        """Test image text extraction with OCR."""
        # Mock PIL Image
        mock_image = MagicMock()
        mock_image.format = "PNG"
        mock_image.size = (800, 600)
        mock_image.mode = "RGB"
        
        # Mock pytesseract
        with patch('PIL.Image.open', return_value=mock_image):
            with patch('pytesseract.image_to_string', return_value="Extracted text from image"):
                text, metadata = await document_service._extract_image_text(
                    b"PNG content", "test.png"
                )
        
        assert text == "Extracted text from image"
        assert metadata["image_format"] == "PNG"
        assert metadata["dimensions"] == (800, 600)
        assert metadata["has_text"] is True
    
    def test_token_length_calculation(self, document_service):
        """Test token length calculation."""
        text = "This is a test sentence for token counting."
        
        # Token length should be greater than 0
        length = document_service._token_length(text)
        assert length > 0
        assert isinstance(length, int)
    
    @pytest.mark.asyncio
    async def test_create_document_chunks(self, document_service, mock_db, mock_ai_service):
        """Test document chunking for RAG."""
        document_id = 1
        text = "This is a long document. " * 100  # Create long text
        metadata = {"page_count": 5}
        
        # Mock text splitter to return 3 chunks
        mock_chunks = [
            "Page 1: First chunk of text",
            "Page 2: Second chunk of text",
            "Third chunk without page marker"
        ]
        
        # Mock settings to enable embeddings
        with patch('src.services.document_service.settings.ENABLE_EMBEDDINGS', True):
            with patch('src.services.document_service.get_ai_service', return_value=mock_ai_service):
                with patch.object(document_service.text_splitter, 'split_text', return_value=mock_chunks):
                    # Mock DocumentChunk to avoid SQLAlchemy initialization issues
                    with patch('src.services.document_service.DocumentChunk') as MockChunk:
                        mock_chunk_instances = []
                        
                        def create_mock_chunk(**kwargs):
                            mock_chunk = MagicMock()
                            for key, value in kwargs.items():
                                setattr(mock_chunk, key, value)
                            mock_chunk_instances.append(mock_chunk)
                            return mock_chunk
                        
                        MockChunk.side_effect = create_mock_chunk
                        
                        await document_service._create_document_chunks(
                            db=mock_db,
                            document_id=document_id,
                            text=text,
                            metadata=metadata
                        )
        
        # Verify chunks were created
        assert mock_db.add.call_count == 3
        assert len(mock_chunk_instances) == 3
        
        # Check first chunk
        first_chunk = mock_chunk_instances[0]
        assert first_chunk.document_id == document_id
        assert first_chunk.chunk_index == 0
        assert first_chunk.page_number == 1
        assert first_chunk.chunk_metadata["embedding"] is not None
        assert len(first_chunk.chunk_metadata["embedding"]) == 1536  # Mock embedding size
    
    @pytest.mark.asyncio
    async def test_get_document_url_success(
        self, document_service, mock_db, mock_s3_service
    ):
        """Test getting presigned URL for document."""
        # Mock document
        mock_doc = MagicMock(spec=DeviceDocument)
        mock_doc.id = 1
        mock_doc.file_key = "documents/10/5/test.pdf"
        mock_doc.title = "Test Document"
        mock_doc.access_level = "public"
        mock_doc.organization_id = 10
        mock_doc.download_count = 5
        mock_doc.deleted_at = None
        
        mock_db.get.return_value = mock_doc
        
        # Mock the S3 factory function
        with patch('src.services.document_service.get_s3_service', return_value=mock_s3_service):
            url = await document_service.get_document_url(
                db=mock_db,
                document_id=1,
                user_id=100,
                organization_id=10,
                action="download"
            )
        
        assert url == "https://s3.example.com/signed-url"
        assert mock_doc.download_count == 6
        mock_db.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_document_url_access_denied(
        self, document_service, mock_db
    ):
        """Test access denied for private document."""
        # Mock private document from different org
        mock_doc = MagicMock()
        mock_doc.access_level = "private"
        mock_doc.organization_id = 20  # Different org
        mock_doc.deleted_at = None
        
        mock_db.get.return_value = mock_doc
        
        with pytest.raises(ValueError, match="Access denied"):
            await document_service.get_document_url(
                db=mock_db,
                document_id=1,
                user_id=100,
                organization_id=10  # Different from document's org
            )
    
    @pytest.mark.asyncio
    async def test_search_documents(self, document_service, mock_db):
        """Test document search functionality."""
        # Mock documents
        mock_docs = [
            MagicMock(
                id=1,
                device_id=5,
                document_type="manual",
                title="User Manual",
                description="Complete user guide",
                file_size_bytes=1024000,
                page_count=50,
                language_code="en",
                download_count=10,
                created_at=datetime.now()
            ),
            MagicMock(
                id=2,
                device_id=5,
                document_type="quickstart",
                title="Quick Start Guide",
                description="Getting started guide",
                file_size_bytes=512000,
                page_count=10,
                language_code="en",
                download_count=25,
                created_at=datetime.now()
            )
        ]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_docs
        mock_db.execute.return_value = mock_result
        
        results = await document_service.search_documents(
            db=mock_db,
            query="manual",
            device_id=5,
            document_types=["manual", "quickstart"],
            limit=10
        )
        
        assert len(results) == 2
        assert results[0]["title"] == "User Manual"
        assert results[0]["document_type"] == "manual"
        assert results[1]["title"] == "Quick Start Guide"
    
    @pytest.mark.asyncio
    async def test_get_document_context_for_rag(self, document_service, mock_db):
        """Test getting document context for RAG system."""
        # Mock documents
        mock_docs = [MagicMock(id=1), MagicMock(id=2)]
        mock_doc_result = MagicMock()
        mock_doc_result.scalars.return_value.all.return_value = mock_docs
        
        # Mock chunks with documents
        mock_chunk1 = MagicMock(
            chunk_index=0,
            page_number=1,
            chunk_text="This is relevant content about pacemakers"
        )
        mock_doc1 = MagicMock(
            id=1,
            title="Pacemaker Manual",
            document_type="manual"
        )
        
        mock_chunk_result = MagicMock()
        mock_chunk_result.__iter__ = Mock(return_value=iter([(mock_chunk1, mock_doc1)]))
        
        mock_db.execute.side_effect = [mock_doc_result, mock_chunk_result]
        
        # Mock ENABLE_EMBEDDINGS setting to use AI service
        with patch('src.services.document_service.settings.ENABLE_EMBEDDINGS', True):
            contexts = await document_service.get_document_context_for_rag(
                db=mock_db,
                device_id=5,
                query="pacemaker settings",
                organization_id=10
            )
        
        assert len(contexts) == 1
        assert contexts[0]["document_title"] == "Pacemaker Manual"
        assert contexts[0]["text"] == "This is relevant content about pacemakers"
        assert contexts[0]["page_number"] == 1
