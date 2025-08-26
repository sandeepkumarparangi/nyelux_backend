"""
Pydantic schemas for document management.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, date


# Base schemas
class DocumentBase(BaseModel):
    device_id: Optional[int] = Field(None, description="Associated device ID")
    document_type: str = Field(..., description="Type of document")
    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    description: Optional[str] = Field(None, description="Document description")
    access_level: str = Field("public", description="Access level: public, restricted, private")


class DocumentChunkBase(BaseModel):
    chunk_text: str = Field(..., description="Chunk text content")
    page_number: Optional[int] = Field(None, description="Page number if applicable")
    section_heading: Optional[str] = Field(None, description="Section heading")


# Request schemas
class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    access_level: Optional[str] = Field(None, pattern="^(public|restricted|private)$")


# Response schemas
class DocumentResponse(DocumentBase):
    id: int
    organization_id: int
    file_url: str = Field(..., description="Document URL")
    file_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    file_hash: Optional[str] = Field(None, description="SHA-256 hash of file")
    mime_type: Optional[str] = Field(None, description="MIME type")
    language_code: str = Field("en", description="Language code")
    version: Optional[str] = Field(None, description="Document version")
    is_current_version: bool = Field(True, description="Is this the current version")
    page_count: Optional[int] = Field(None, description="Number of pages")
    download_count: int = Field(0, description="Download count")
    last_downloaded_at: Optional[datetime] = None
    expiration_date: Optional[date] = None
    created_by: Optional[int] = Field(None, description="User ID who created")
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class DocumentChunkResponse(DocumentChunkBase):
    id: int
    document_id: int
    chunk_index: int = Field(..., description="Order of chunk in document")
    embedding_model: Optional[str] = Field(None, description="Embedding model used")
    token_count: int = Field(..., description="Estimated token count")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    model_config = ConfigDict(from_attributes=True)


class DocumentList(BaseModel):
    documents: List[DocumentResponse]
    total: int = Field(..., description="Total number of documents")
    skip: int = Field(..., description="Number of documents skipped")
    limit: int = Field(..., description="Maximum number of documents returned")


# Analytics schemas
class DocumentStats(BaseModel):
    total_documents: int
    documents_by_type: Dict[str, int]
    total_size_bytes: int
    total_downloads: int
    average_document_size: float
    most_downloaded: List[DocumentResponse]
    
    model_config = ConfigDict(from_attributes=True)


class DocumentVersion(BaseModel):
    id: int
    version: str
    created_at: datetime
    created_by: Optional[int]
    is_current: bool
    changes: Optional[str] = Field(None, description="Version change description")
    
    model_config = ConfigDict(from_attributes=True)


# Processing schemas
class DocumentProcessingStatus(BaseModel):
    document_id: int
    status: str = Field(..., description="Status: pending, processing, completed, failed")
    progress: float = Field(0.0, ge=0, le=100, description="Processing progress percentage")
    chunks_created: int = Field(0, description="Number of chunks created")
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


# Search schemas
class DocumentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    device_id: Optional[int] = None
    document_type: Optional[str] = None
    organization_id: Optional[int] = None
    access_level: Optional[List[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class DocumentSearchResult(BaseModel):
    document: DocumentResponse
    relevance_score: float = Field(..., ge=0, le=1, description="Search relevance score")
    highlights: Optional[Dict[str, List[str]]] = Field(None, description="Highlighted matches")
    
    model_config = ConfigDict(from_attributes=True)
