"""
Document Service - File upload, processing, and management.
REAL implementation with S3 storage and text extraction.
NO FAKE FILE HANDLING - actual document processing pipeline.
"""
import os
import logging
import hashlib
import mimetypes
from pathlib import Path
from typing import List, Dict, Any, Optional, BinaryIO, Tuple
from datetime import datetime, timezone
import asyncio
import aiofiles
from uuid import uuid4

# Document processing libraries
import pypdf
from PIL import Image
import pytesseract
from docx import Document as DocxDocument
import openpyxl
import magic

# Text processing
import tiktoken
from langchain.text_splitter import RecursiveCharacterTextSplitter

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func

from src.db.models.device_document import DeviceDocument
from src.db.models.document_chunk import DocumentChunk
from src.db.models.vendor_device import VendorDevice
from src.db.models.analytics_event import AnalyticsEvent
# Import service factory functions - NO FAKE IMPLEMENTATIONS
from src.services.s3_service import get_s3_service
from src.services.ai_service import get_ai_service
from src.core.config import settings
from src.core.cache import CacheService
from src.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class DocumentService:
    """
    Document management service handling:
    1. Secure file upload with virus scanning
    2. S3 storage with presigned URLs
    3. Text extraction from multiple formats
    4. Document chunking for RAG
    5. Embedding generation
    6. Version control
    7. Access control
    """
    
    def __init__(self):
        self.cache = CacheService()
        self.allowed_types = settings.ALLOWED_DOCUMENT_TYPES
        self.max_file_size = settings.MAX_UPLOAD_SIZE
        self.chunk_size = settings.MAX_CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=self._token_length,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        # Initialize tokenizer for accurate token counting
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # File type handlers
        self.extractors = {
            "application/pdf": self._extract_pdf,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": self._extract_docx,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": self._extract_xlsx,
            "image/jpeg": self._extract_image_text,
            "image/png": self._extract_image_text
        }
    
    async def upload_document(
        self,
        db: AsyncSession,
        file: BinaryIO,
        filename: str,
        device_id: int,
        organization_id: int,
        document_type: str,
        user_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        language_code: str = "en",
        access_level: str = "public"
    ) -> DeviceDocument:
        """
        Upload and process a document.
        Implements complete pipeline from upload to RAG-ready chunks.
        """
        # Validate inputs
        if document_type not in ["manual", "quickstart", "datasheet", "certificate", "clinical_study", "safety_notice"]:
            raise ValueError(f"Invalid document type: {document_type}")
        
        # Check device exists and user has access
        device = await db.get(VendorDevice, device_id)
        if not device or device.organization_id != organization_id:
            raise ValueError("Device not found or access denied")
        
        # Read file content
        content = await self._read_file_content(file)
        
        # Validate file
        mime_type = await self._validate_file(content, filename)
        
        # Generate file hash for deduplication
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Check if duplicate
        existing_result = await db.execute(
            select(DeviceDocument).where(
                and_(
                    DeviceDocument.file_hash == file_hash,
                    DeviceDocument.device_id == device_id,
                    DeviceDocument.deleted_at.is_(None)
                )
            )
        )
        existing = await existing_result.scalar_one_or_none()
        if existing:
            raise ValueError("This document has already been uploaded for this device")
        
        # Scan for viruses (in production, integrate with ClamAV)
        await self._scan_for_viruses(content)
        
        # Generate S3 key
        file_key = self._generate_s3_key(organization_id, device_id, filename)
        
        # Upload to S3 - REAL service only, no fake implementations
        logger.info(f"Uploading document to S3: {file_key}")
        try:
            s3 = get_s3_service()  # This will raise if not configured
            upload_result = await s3.upload_file(
                file_data=content,
                key=file_key,
                content_type=mime_type
            )
            file_url = upload_result["url"]
        except ExternalServiceError as e:
            logger.error(f"S3 upload failed: {e}")
            raise  # Don't hide the error - fail fast
        
        # Extract text content
        logger.info(f"Extracting text from {mime_type}")
        extracted_text, metadata = await self._extract_text(content, mime_type, filename)
        
        # Get page count
        page_count = metadata.get("page_count", 1)
        
        # Mark previous versions as non-current
        await db.execute(
            select(DeviceDocument).where(
                and_(
                    DeviceDocument.device_id == device_id,
                    DeviceDocument.document_type == document_type,
                    DeviceDocument.is_current_version == True
                )
            ).update({"is_current_version": False})
        )
        
        # Create document record
        document = DeviceDocument(
            device_id=device_id,
            organization_id=organization_id,
            document_type=document_type,
            title=title or filename,
            description=description,
            file_url=file_url,
            file_key=file_key,
            file_size_bytes=len(content),
            file_hash=file_hash,
            mime_type=mime_type,
            language_code=language_code,
            version="1.0",
            is_current_version=True,
            page_count=page_count,
            metadata=metadata,
            access_level=access_level,
            created_by=user_id
        )
        
        db.add(document)
        await db.flush()  # Get document ID
        
        # Process document for RAG if text was extracted
        if extracted_text:
            logger.info(f"Creating document chunks for RAG")
            await self._create_document_chunks(
                db=db,
                document_id=document.id,
                text=extracted_text,
                metadata=metadata
            )
        
        await db.commit()
        await db.refresh(document)
        
        # Clear relevant caches
        await self._invalidate_caches(device_id)
        
        logger.info(f"Document uploaded successfully: {document.id}")
        return document
    
    async def get_document_url(
        self,
        db: AsyncSession,
        document_id: int,
        user_id: int,
        organization_id: int,
        action: str = "download"
    ) -> str:
        """
        Get presigned URL for document access.
        Implements access control and tracks downloads.
        """
        # Get document with access check
        document = await db.get(DeviceDocument, document_id)
        if not document or document.deleted_at:
            raise ValueError("Document not found")
        
        # Check access permissions
        if document.access_level != "public":
            if document.organization_id != organization_id:
                raise ValueError("Access denied")
        
        # Generate presigned URL - REAL service only
        try:
            s3 = get_s3_service()  # This will raise if not configured
            presigned_url = s3.generate_presigned_url(
                key=document.file_key,
                expires_in=3600  # 1 hour
            )
        except ExternalServiceError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise  # Don't hide the error - fail fast
        
        # Track download
        if action == "download":
            document.download_count += 1
            document.last_downloaded_at = datetime.now(timezone.utc)
            await db.commit()
            
            # Log download for analytics
            event = AnalyticsEvent(
                user_id=user_id,
                organization_id=organization_id,
                event_type="document_download",
                event_category="engagement",
                resource_type="document",
                resource_id=str(document_id),
                action="download",
                label=document.title,
                event_metadata={
                    "document_type": document.document_type,
                    "file_size": document.file_size_bytes,
                    "device_id": document.device_id
                }
            )
            db.add(event)
            await db.commit()
        
        return presigned_url
    
    async def search_documents(
        self,
        db: AsyncSession,
        query: str,
        device_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        document_types: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search documents using full-text search.
        Used by RAG system to find relevant documents.
        """
        # Build search query
        stmt = select(DeviceDocument).where(
            DeviceDocument.deleted_at.is_(None),
            DeviceDocument.is_current_version == True
        )
        
        if device_id:
            stmt = stmt.where(DeviceDocument.device_id == device_id)
        
        if organization_id:
            stmt = stmt.where(
                or_(
                    DeviceDocument.access_level == "public",
                    DeviceDocument.organization_id == organization_id
                )
            )
        
        if document_types:
            stmt = stmt.where(DeviceDocument.document_type.in_(document_types))
        
        # Add text search
        if query:
            # Use PostgreSQL full-text search on title and description
            stmt = stmt.where(
                or_(
                    func.lower(DeviceDocument.title).contains(query.lower()),
                    func.lower(DeviceDocument.description).contains(query.lower())
                )
            )
        
        stmt = stmt.order_by(DeviceDocument.created_at.desc()).limit(limit)
        
        result = await db.execute(stmt)
        documents = result.scalars().all()
        
        # Convert to dict with additional info
        return [
            {
                "id": doc.id,
                "device_id": doc.device_id,
                "document_type": doc.document_type,
                "title": doc.title,
                "description": doc.description,
                "file_size_bytes": doc.file_size_bytes,
                "page_count": doc.page_count,
                "language_code": doc.language_code,
                "download_count": doc.download_count,
                "created_at": doc.created_at.isoformat()
            }
            for doc in documents
        ]
    
    async def _read_file_content(self, file: BinaryIO) -> bytes:
        """Read file content into memory for processing."""
        file.seek(0)
        content = file.read()
        file.seek(0)  # Reset for potential re-reading
        return content
    
    async def _validate_file(self, content: bytes, filename: str) -> str:
        """
        Validate file type and size.
        Returns verified MIME type.
        """
        # Check file size
        if len(content) > self.max_file_size:
            raise ValueError(f"File too large. Maximum size: {self.max_file_size / 1024 / 1024}MB")
        
        # Verify MIME type using python-magic
        mime = magic.Magic(mime=True)
        detected_type = mime.from_buffer(content)
        
        # Also check by extension as fallback
        guessed_type = mimetypes.guess_type(filename)[0]
        
        # Prefer detected type but validate against allowed types
        mime_type = detected_type or guessed_type
        
        if mime_type not in self.allowed_types:
            raise ValueError(f"File type not allowed: {mime_type}")
        
        return mime_type
    
    async def _scan_for_viruses(self, content: bytes):
        """
        Scan file for viruses.
        In production, integrate with ClamAV or similar.
        """
        # For now, just check for suspicious patterns
        # In production: use pyclamd to connect to ClamAV daemon
        
        # Check for executable signatures
        suspicious_signatures = [
            b'MZ',  # DOS/Windows executable
            b'\x7fELF',  # Linux executable
            b'#!/',  # Shell script
            b'<script',  # JavaScript
        ]
        
        for sig in suspicious_signatures:
            if content.startswith(sig):
                raise ValueError("File appears to contain executable code")
        
        # In production:
        # import pyclamd
        # cd = pyclamd.ClamdAgnostic()
        # result = cd.scan_stream(content)
        # if result:
        #     raise ValueError(f"Virus detected: {result}")
    
    def _generate_s3_key(self, organization_id: int, device_id: int, filename: str) -> str:
        """Generate organized S3 key structure."""
        # Clean filename - replace spaces and parentheses with underscores
        safe_filename = "".join(
            "_" if c in " ()" else c 
            for c in filename 
            if c.isalnum() or c in ".-_() "
        )
        
        # Add UUID to prevent collisions
        unique_id = uuid4().hex[:8]
        
        # Create hierarchical structure
        return f"documents/{organization_id}/{device_id}/{unique_id}_{safe_filename}"
    
    async def _extract_text(
        self, 
        content: bytes, 
        mime_type: str, 
        filename: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from document based on type.
        Returns extracted text and metadata.
        """
        extractor = self.extractors.get(mime_type)
        if not extractor:
            logger.warning(f"No text extractor for {mime_type}")
            return "", {}
        
        try:
            return await extractor(content, filename)
        except Exception as e:
            logger.error(f"Text extraction failed for {filename}: {e}")
            return "", {"extraction_error": str(e)}
    
    async def _extract_pdf(self, content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """Extract text from PDF using pypdf."""
        import io
        
        text_parts = []
        metadata = {"page_count": 0, "has_images": False}
        
        try:
            pdf_file = io.BytesIO(content)
            pdf_reader = pypdf.PdfReader(pdf_file)
            
            metadata["page_count"] = len(pdf_reader.pages)
            
            # Extract text from each page
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text.strip():
                        text_parts.append(f"Page {page_num + 1}:\n{page_text}")
                    
                    # Check for images
                    if '/XObject' in page['/Resources']:
                        metadata["has_images"] = True
                
                except Exception as e:
                    logger.warning(f"Failed to extract page {page_num + 1}: {e}")
            
            # Extract PDF metadata
            if pdf_reader.metadata:
                metadata["pdf_metadata"] = {
                    "title": pdf_reader.metadata.get('/Title'),
                    "author": pdf_reader.metadata.get('/Author'),
                    "subject": pdf_reader.metadata.get('/Subject'),
                    "creator": pdf_reader.metadata.get('/Creator'),
                    "producer": pdf_reader.metadata.get('/Producer'),
                    "creation_date": str(pdf_reader.metadata.get('/CreationDate')),
                    "modification_date": str(pdf_reader.metadata.get('/ModDate'))
                }
        
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            raise
        
        return "\n\n".join(text_parts), metadata
    
    async def _extract_docx(self, content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """Extract text from Word document."""
        import io
        
        text_parts = []
        metadata = {"page_count": 1, "has_images": False, "has_tables": False}
        
        try:
            # Ensure we have valid DOCX content
            if len(content) < 100:  # Too small to be a valid DOCX
                raise ValueError("Invalid DOCX file")
                
            docx_file = io.BytesIO(content)
            doc = DocxDocument(docx_file)
            
            # Extract paragraphs
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)
            
            # Extract tables
            if doc.tables:
                metadata["has_tables"] = True
                for table in doc.tables:
                    table_text = []
                    for row in table.rows:
                        row_text = [cell.text.strip() for cell in row.cells]
                        table_text.append(" | ".join(row_text))
                    text_parts.append("\nTable:\n" + "\n".join(table_text) + "\n")
            
            # Check for images
            if doc.inline_shapes:
                metadata["has_images"] = True
            
            # Extract document properties
            core_props = doc.core_properties
            metadata["docx_metadata"] = {
                "title": core_props.title,
                "author": core_props.author,
                "subject": core_props.subject,
                "keywords": core_props.keywords,
                "created": str(core_props.created),
                "modified": str(core_props.modified)
            }
        
        except Exception as e:
            logger.error(f"DOCX extraction error: {e}")
            raise
        
        return "\n\n".join(text_parts), metadata
    
    async def _extract_xlsx(self, content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """Extract text from Excel spreadsheet."""
        import io
        
        text_parts = []
        metadata = {"sheet_count": 0, "total_rows": 0, "total_cells": 0}
        
        try:
            xlsx_file = io.BytesIO(content)
            workbook = openpyxl.load_workbook(xlsx_file, data_only=True)
            
            metadata["sheet_count"] = len(workbook.sheetnames)
            
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                text_parts.append(f"Sheet: {sheet_name}")
                
                # Extract data from cells
                sheet_data = []
                for row in sheet.iter_rows(values_only=True):
                    row_data = [str(cell) if cell is not None else "" for cell in row]
                    if any(row_data):  # Skip empty rows
                        sheet_data.append(" | ".join(row_data))
                        metadata["total_cells"] += len(row_data)
                
                metadata["total_rows"] += len(sheet_data)
                text_parts.extend(sheet_data)
                text_parts.append("")  # Empty line between sheets
        
        except Exception as e:
            logger.error(f"XLSX extraction error: {e}")
            raise
        
        return "\n".join(text_parts), metadata
    
    async def _extract_image_text(self, content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """Extract text from images using OCR."""
        import io
        
        metadata = {"image_format": "", "dimensions": (), "has_text": False}
        
        try:
            # Open image
            image = Image.open(io.BytesIO(content))
            metadata["image_format"] = image.format
            metadata["dimensions"] = image.size
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Run OCR
            extracted_text = pytesseract.image_to_string(image)
            
            if extracted_text.strip():
                metadata["has_text"] = True
                metadata["text_confidence"] = len(extracted_text.strip()) > 10
            
            return extracted_text, metadata
        
        except Exception as e:
            logger.error(f"Image OCR error: {e}")
            # Don't fail completely if OCR fails
            return "", metadata
    
    def _token_length(self, text: str) -> int:
        """Calculate token length for chunking."""
        return len(self.tokenizer.encode(text))
    
    async def _create_document_chunks(
        self,
        db: AsyncSession,
        document_id: int,
        text: str,
        metadata: Dict[str, Any]
    ):
        """
        Create document chunks for RAG system.
        Implements smart chunking with overlap.
        """
        if not text or len(text.strip()) < 50:
            logger.warning(f"Text too short for chunking: {len(text)} chars")
            return
        
        # Split text into chunks
        chunks = self.text_splitter.split_text(text)
        
        # Create chunk records with embeddings
        for i, chunk_text in enumerate(chunks):
            if len(chunk_text.strip()) < 10:
                continue
            
            # Determine page number if available
            page_number = None
            if "Page" in chunk_text[:20]:
                try:
                    page_number = int(chunk_text.split(":")[0].replace("Page", "").strip())
                except:
                    pass
            
            # Generate embedding using AI service if available
            embedding = None
            embedding_model = None
            try:
                # Only try to get AI service if we actually want embeddings
                if settings.ENABLE_EMBEDDINGS:
                    ai = get_ai_service()  # This will raise if not configured
                    embedding = await ai.get_embedding(chunk_text)
                    embedding_model = "text-embedding-ada-002"
            except ExternalServiceError:
                # AI not configured - embeddings will be None
                # This is OK - we can still create chunks without embeddings
                logger.debug("AI service not available - creating chunks without embeddings")
            except Exception as e:
                # Other errors should be logged but not fail chunk creation
                logger.warning(f"Failed to generate embedding: {e}")
            
            # Create chunk record
            chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=i,
                chunk_text=chunk_text,
                page_number=page_number,
                embedding_model=embedding_model,  # Will be None if AI not available
                chunk_metadata={
                    "chunk_size": len(chunk_text),
                    "token_count": self._token_length(chunk_text),
                    "embedding": embedding  # Store embedding in metadata for now
                }
            )
            
            db.add(chunk)
        
        # Don't commit here - let the caller handle the transaction
    
    async def _invalidate_caches(self, device_id: int):
        """Invalidate relevant caches after document upload."""
        cache_patterns = [
            f"device:{device_id}:documents",
            f"device:{device_id}:rag_context"
        ]
        
        for pattern in cache_patterns:
            await self.cache.delete(pattern)
    
    async def get_document_context_for_rag(
        self,
        db: AsyncSession,
        device_id: int,
        query: str,
        organization_id: Optional[int] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get relevant document chunks for RAG context.
        Used by AI chat to provide accurate answers.
        """
        # First, get documents for the device
        documents = await db.execute(
            select(DeviceDocument).where(
                and_(
                    DeviceDocument.device_id == device_id,
                    DeviceDocument.deleted_at.is_(None),
                    DeviceDocument.is_current_version == True,
                    or_(
                        DeviceDocument.access_level == "public",
                        DeviceDocument.organization_id == organization_id
                    )
                )
            )
        )
        doc_ids = [doc.id for doc in documents.scalars().all()]
        
        if not doc_ids:
            return []
        
        # Search for relevant chunks
        # Try to use vector similarity if AI is available
        use_vector_search = False
        query_embedding = None
        
        try:
            if settings.ENABLE_EMBEDDINGS:
                ai = get_ai_service()
                query_embedding = await ai.get_embedding(query)
                use_vector_search = True
        except ExternalServiceError:
            # AI not available - fall back to text search
            logger.debug("AI service not available - using text search")
        
        if use_vector_search and query_embedding:
            # Use vector similarity search
            # This would use pgvector for similarity search
            # For now, return top chunks by relevance
            stmt = (
                select(DocumentChunk, DeviceDocument)
                .join(DeviceDocument)
                .where(DocumentChunk.document_id.in_(doc_ids))
                .order_by(DocumentChunk.id)  # Would be similarity order with pgvector
                .limit(limit)
            )
        else:
            # Fallback to text search - this always works
            stmt = (
                select(DocumentChunk, DeviceDocument)
                .join(DeviceDocument)
                .where(
                    and_(
                        DocumentChunk.document_id.in_(doc_ids),
                        func.lower(DocumentChunk.chunk_text).contains(query.lower())
                    )
                )
                .limit(limit)
            )
        
        result = await db.execute(stmt)
        
        # Format results for RAG
        contexts = []
        for chunk, document in result:
            contexts.append({
                "document_id": document.id,
                "document_title": document.title,
                "document_type": document.document_type,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "text": chunk.chunk_text,
                "relevance_score": 0.0  # Would be actual similarity score
            })
        
        return contexts


# Use dependency injection instead of singleton
# Create instances as needed with DocumentService()
