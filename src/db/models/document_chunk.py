from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base_class import Base


class DocumentChunk(Base):
    """
    Document chunks for RAG (Retrieval-Augmented Generation) system.
    Each chunk represents a searchable portion of a document with embeddings.
    """
    __tablename__ = "document_chunks"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Document association
    document_id = Column(Integer, ForeignKey("device_documents.id"), nullable=False)
    
    # Chunk details
    chunk_index = Column(Integer, nullable=False, comment="Order of chunk in document")
    chunk_text = Column(Text, nullable=False, comment="Actual text content")
    page_number = Column(Integer, nullable=True, comment="Page number if applicable")
    section_heading = Column(Text, nullable=True, comment="Section or chapter heading")
    
    # Embedding information
    embedding_model = Column(String(50), nullable=True, comment="Model used for embedding")
    # NOTE: Vector embedding column requires pgvector extension
    # embedding = Column(VECTOR(1536), nullable=True, comment="Vector embedding for similarity search")
    # For now, we'll store embeddings in a separate table or use a JSON column
    
    # Additional metadata
    chunk_metadata = Column(JSONB, nullable=True, comment="Additional chunk metadata")
    
    # Relationships
    document = relationship("DeviceDocument", back_populates="chunks")
    
    # Indexes
    __table_args__ = (
        UniqueConstraint('document_id', 'chunk_index', name='uq_document_chunk_index'),
        Index('idx_document_chunks', 'document_id', 'chunk_index'),
        # Index for vector search will be added when pgvector is installed
        # Index('idx_embedding_vector', 'embedding', postgresql_using='ivfflat'),
        Index('idx_chunk_page', 'document_id', 'page_number'),
    )
    
    @property
    def token_count(self) -> int:
        """Estimate token count for the chunk"""
        # Rough approximation: 1 token ≈ 4 characters
        return len(self.chunk_text) // 4
    
    @property
    def preview(self) -> str:
        """Get preview of chunk text"""
        max_length = 200
        if len(self.chunk_text) <= max_length:
            return self.chunk_text
        return self.chunk_text[:max_length] + "..."
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "page_number": self.page_number,
            "section_heading": self.section_heading,
            "preview": self.preview,
            "token_count": self.token_count,
            "embedding_model": self.embedding_model,
            "metadata": self.chunk_metadata or {}
        }
    
    def __repr__(self):
        return f"<DocumentChunk {self.id}: doc_{self.document_id}_chunk_{self.chunk_index}>"
