from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, BIGINT,
    UniqueConstraint, Index, CheckConstraint, Date
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base_class import Base

class DeviceDocument(Base):
    """
    Device-related document storage.
    Handles manuals, datasheets, certificates, studies, etc.
    """
    __tablename__ = "device_documents"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Device association
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    
    # Document metadata
    document_type = Column(String(50), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    
    # File information
    file_url = Column(Text, nullable=False)
    file_key = Column(String(500), nullable=True, index=True)  # S3 key
    file_size_bytes = Column(BIGINT, nullable=True)
    file_hash = Column(String(64), nullable=True)  # SHA-256 hash
    mime_type = Column(String(100), nullable=True)
    
    # Document details
    language_code = Column(String(10), default='en', nullable=False)
    version = Column(String(50), nullable=True)
    is_current_version = Column(Boolean, default=True, nullable=False)
    previous_version_id = Column(Integer, ForeignKey("device_documents.id"), nullable=True)
    page_count = Column(Integer, nullable=True)
    
    # Additional metadata
    document_metadata = Column(JSONB, default=dict, nullable=True)
    
    # Access control
    access_level = Column(String(20), default='public', nullable=False)
    
    # Usage tracking
    download_count = Column(Integer, default=0, nullable=False)
    last_downloaded_at = Column(DateTime(timezone=True), nullable=True)
    
    # Expiration
    expiration_date = Column(Date, nullable=True)
    
    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    device = relationship("VendorDevice", backref="documents")
    organization = relationship("Organization", back_populates="device_documents")
    previous_version = relationship("DeviceDocument", remote_side=[id])
    created_by_user = relationship("User", foreign_keys=[created_by], back_populates="created_documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('manual', 'quickstart', 'datasheet', 'certificate', 'clinical_study', 'safety_notice', 'other')", 
            name='check_document_type'
        ),
        CheckConstraint("access_level IN ('public', 'restricted', 'private')", name='check_doc_access_level'),
        CheckConstraint("file_size_bytes >= 0", name='check_file_size_positive'),
        CheckConstraint("page_count >= 0", name='check_page_count_positive'),
        CheckConstraint("download_count >= 0", name='check_download_count_positive'),
        Index('idx_device_doc_type_current', 'device_id', 'document_type', 'is_current_version'),
        Index('idx_doc_organization', 'organization_id'),
        Index('idx_doc_file_key', 'file_key'),
    )
    
    @property
    def is_expired(self) -> bool:
        """Check if document has expired"""
        if not self.expiration_date:
            return False
        from datetime import date
        return self.expiration_date < date.today()
    
    @property
    def file_size_mb(self) -> float:
        """Get file size in megabytes"""
        if not self.file_size_bytes:
            return 0.0
        return self.file_size_bytes / (1024 * 1024)
    
    @property
    def is_large_file(self) -> bool:
        """Check if file is considered large (>10MB)"""
        return self.file_size_mb > 10
    
    def get_document_icon(self) -> str:
        """Get icon name based on document type"""
        icons = {
            'manual': 'book',
            'quickstart': 'rocket',
            'datasheet': 'file-text',
            'certificate': 'award',
            'clinical_study': 'activity',
            'safety_notice': 'alert-triangle',
            'other': 'file'
        }
        return icons.get(self.document_type, 'file')
    
    def increment_download_count(self):
        """Increment download counter"""
        from datetime import datetime
        self.download_count += 1
        self.last_downloaded_at = datetime.utcnow()
    
    def can_user_access(self, user) -> bool:
        """Check if a user can access this document"""
        # Public documents are accessible to all
        if self.access_level == 'public':
            return True
        
        # Check device access permissions
        if self.device and hasattr(self.device, 'can_user_access') and not self.device.can_user_access(user):
            return False
        
        # Organization members can access their documents
        if hasattr(user, 'organization_id') and user.organization_id == self.organization_id:
            return True
        
        # Super admins can access everything
        if hasattr(user, 'role') and user.role == 'super_admin':
            return True
        
        return False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "device_id": self.device_id,
            "document_type": self.document_type,
            "title": self.title,
            "description": self.description,
            "file_url": self.file_url,
            "file_size_mb": round(self.file_size_mb, 2),
            "mime_type": self.mime_type,
            "language_code": self.language_code,
            "version": self.version,
            "is_current_version": self.is_current_version,
            "page_count": self.page_count,
            "access_level": self.access_level,
            "download_count": self.download_count,
            "is_expired": self.is_expired,
            "icon": self.get_document_icon(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<DeviceDocument {self.id}: {self.title} ({self.document_type})>"
