from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, BigInteger, Index, Boolean, DateTime
)
from sqlalchemy.orm import relationship
from typing import TYPE_CHECKING

from src.db.base_class import Base

if TYPE_CHECKING:
    from src.db.models.device_incident import DeviceIncident
    from src.db.models.user import User


class IncidentAttachment(Base):
    """
    Files attached to device incident reports.
    """
    __tablename__ = "incident_attachments"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Incident association
    incident_id = Column(Integer, ForeignKey("device_incidents.id"), nullable=False)
    
    # Attachment details
    attachment_type = Column(String(50), nullable=True, comment="photo, document, video, etc.")
    file_url = Column(Text, nullable=False)
    file_size_bytes = Column(BigInteger, nullable=True)
    description = Column(Text, nullable=True)
    
    # Upload information
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    incident = relationship("DeviceIncident", back_populates="attachments")
    uploader = relationship("User", foreign_keys=[uploaded_by], back_populates="uploaded_attachments")
    
    # Indexes
    __table_args__ = (
        Index('idx_incident_attachment', 'incident_id', 'created_at'),
    )
    
    @property
    def file_size_mb(self) -> float:
        """Get file size in megabytes"""
        if self.file_size_bytes:
            return self.file_size_bytes / (1024 * 1024)
        return 0.0
    
    @property
    def file_extension(self) -> str:
        """Extract file extension from URL"""
        if self.file_url:
            import os
            return os.path.splitext(self.file_url)[1].lower()
        return ""
    
    @property
    def is_image(self) -> bool:
        """Check if attachment is an image"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        return self.file_extension in image_extensions
    
    @property
    def is_video(self) -> bool:
        """Check if attachment is a video"""
        video_extensions = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm']
        return self.file_extension in video_extensions
    
    @property
    def is_document(self) -> bool:
        """Check if attachment is a document"""
        doc_extensions = ['.pdf', '.doc', '.docx', '.txt', '.rtf']
        return self.file_extension in doc_extensions
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "attachment_type": self.attachment_type or self._guess_type(),
            "file_url": self.file_url,
            "file_size_bytes": self.file_size_bytes,
            "file_size_mb": round(self.file_size_mb, 2),
            "description": self.description,
            "uploaded_by": self.uploaded_by,
            "uploader_name": self.uploader.full_name if self.uploader else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def _guess_type(self) -> str:
        """Guess attachment type from file extension"""
        if self.is_image:
            return "photo"
        elif self.is_video:
            return "video"
        elif self.is_document:
            return "document"
        return "other"
    
    def __repr__(self):
        return f"<IncidentAttachment {self.id}: {self.attachment_type or 'unknown'}>"


class IncidentComment(Base):
    """
    Communication thread for device incidents.
    """
    __tablename__ = "incident_comments"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Incident association
    incident_id = Column(Integer, ForeignKey("device_incidents.id"), nullable=False)
    
    # Comment details
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment_text = Column(Text, nullable=False)
    is_internal = Column(Boolean, nullable=False, default=False, comment="Internal notes not visible to reporter")
    
    # Relationships
    incident = relationship("DeviceIncident", back_populates="comments")
    user = relationship("User", back_populates="incident_comments")
    
    # Indexes
    __table_args__ = (
        Index('idx_incident_comment_created', 'incident_id', 'created_at'),
        Index('idx_incident_comment_user', 'user_id', 'created_at'),
    )
    
    @property
    def is_from_reporter(self) -> bool:
        """Check if comment is from the incident reporter"""
        return self.incident and self.user_id == self.incident.reported_by
    
    @property
    def is_from_assignee(self) -> bool:
        """Check if comment is from the assigned agent"""
        return self.incident and self.user_id == self.incident.assigned_to
    
    @property
    def is_visible_to_reporter(self) -> bool:
        """Check if comment should be visible to the reporter"""
        return not self.is_internal
    
    def to_dict(self, include_internal: bool = False) -> dict:
        """Convert to dictionary for API responses"""
        # Skip internal comments unless explicitly requested
        if self.is_internal and not include_internal:
            return None
        
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "user_id": self.user_id,
            "user_name": self.user.full_name if self.user else None,
            "user_role": self._get_user_role(),
            "comment_text": self.comment_text,
            "is_internal": self.is_internal,
            "is_from_reporter": self.is_from_reporter,
            "is_from_assignee": self.is_from_assignee,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def _get_user_role(self) -> str:
        """Determine user's role in the incident"""
        if self.is_from_reporter:
            return "reporter"
        elif self.is_from_assignee:
            return "assignee"
        elif self.user and self.user.is_vendor:
            return "vendor"
        else:
            return "other"
    
    def __repr__(self):
        return f"<IncidentComment {self.id}: {'Internal' if self.is_internal else 'Public'}>"
