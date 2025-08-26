from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text,
    Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from typing import TYPE_CHECKING

from src.db.base_class import Base

if TYPE_CHECKING:
    from src.db.models.user import User
    from src.db.models.organization import Organization, Department
    from src.db.models.vendor_device import VendorDevice
    from src.db.models.device_incident import DeviceIncident


class Note(Base):
    """
    Team collaboration notes with real-time sync.
    Supports device-specific notes, team sharing, and rich content.
    """
    __tablename__ = "notes"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Owner and organization
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    
    # Note content
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    content_type = Column(String(20), default='markdown', nullable=False)  # markdown, plaintext, richtext
    
    # Association (optional)
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True, index=True)
    incident_id = Column(Integer, ForeignKey("device_incidents.id"), nullable=True)
    
    # Note type and categorization
    note_type = Column(String(50), default='general', nullable=False)
    category = Column(String(100), nullable=True)
    tags = Column(ARRAY(String), default=list, nullable=False)
    
    # Access control
    access_level = Column(String(20), default='private', nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    
    # Collaboration features
    is_pinned = Column(Boolean, default=False, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    allow_comments = Column(Boolean, default=True, nullable=False)
    
    # Version control
    version = Column(Integer, default=1, nullable=False)
    previous_version_id = Column(Integer, ForeignKey("notes.id"), nullable=True)
    
    # Real-time collaboration
    last_edited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_edited_at = Column(DateTime(timezone=True), nullable=True)
    edit_lock_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    edit_lock_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    attachments = Column(JSONB, default=list, nullable=False)  # List of file references
    note_metadata = Column(JSONB, nullable=True)  # Custom metadata
    
    # Full-text search
    search_vector = Column(Text, nullable=True)  # Will be TSVECTOR in PostgreSQL
    
    # Relationships
    created_by_user = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="notes"
    )
    organization = relationship("Organization", back_populates="notes")
    device = relationship("VendorDevice", back_populates="notes")
    incident = relationship("DeviceIncident", back_populates="notes")
    department = relationship("Department", back_populates="notes")
    team = relationship("Team", back_populates="notes")
    
    # Version history
    previous_version = relationship("Note", remote_side=[id], backref="newer_versions")
    versions = relationship(
        "NoteVersion",
        back_populates="note",
        cascade="all, delete-orphan"
    )
    
    # Collaboration relationships
    last_editor = relationship("User", foreign_keys=[last_edited_by])
    lock_holder = relationship("User", foreign_keys=[edit_lock_user_id])
    
    # Comments relationship
    comments = relationship(
        "NoteComment",
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="NoteComment.created_at"
    )
    
    # Collaboration relationships
    mentions = relationship(
        "NoteMention",
        back_populates="note",
        cascade="all, delete-orphan"
    )
    activities = relationship(
        "NoteActivity",
        back_populates="note",
        cascade="all, delete-orphan"
    )
    shares = relationship(
        "NoteShare",
        back_populates="note",
        cascade="all, delete-orphan"
    )
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("content_type IN ('markdown', 'plaintext', 'richtext')", name='check_content_type'),
        CheckConstraint("note_type IN ('general', 'device_specific', 'clinical', 'technical', 'safety', 'training')", 
                       name='check_note_type'),
        CheckConstraint("access_level IN ('private', 'team', 'department', 'organization', 'public')", 
                       name='check_access_level'),
        CheckConstraint("version > 0", name='check_version_positive'),
        Index('idx_note_user_created', 'created_by', 'created_at'),
        Index('idx_note_device', 'device_id'),
        Index('idx_note_access', 'organization_id', 'access_level'),
        Index('idx_note_type_category', 'note_type', 'category'),
        Index('idx_note_archived', 'is_archived'),
        Index('idx_note_search', 'search_vector'),  # GIN index in migration
    )
    
    @property
    def is_locked(self) -> bool:
        """Check if note is currently locked for editing"""
        if not self.edit_lock_user_id or not self.edit_lock_expires_at:
            return False
        from datetime import datetime
        return self.edit_lock_expires_at > datetime.utcnow()
    
    @property
    def can_user_edit(self, user_id: int) -> bool:
        """Check if user can edit the note"""
        # Owner can always edit
        if self.created_by == user_id:
            return True
        
        # Check if locked by another user
        if self.is_locked and self.edit_lock_user_id != user_id:
            return False
        
        # Check access level
        # (This would be more complex with proper permission checking)
        return self.access_level != 'private'
    
    @property
    def word_count(self) -> int:
        """Get word count of content"""
        if not self.content:
            return 0
        return len(self.content.split())
    
    def acquire_edit_lock(self, user_id: int, duration_minutes: int = 5) -> bool:
        """Acquire edit lock for real-time collaboration"""
        if self.is_locked and self.edit_lock_user_id != user_id:
            return False
        
        from datetime import datetime, timedelta
        self.edit_lock_user_id = user_id
        self.edit_lock_expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)
        return True
    
    def release_edit_lock(self, user_id: int):
        """Release edit lock"""
        if self.edit_lock_user_id == user_id:
            self.edit_lock_user_id = None
            self.edit_lock_expires_at = None
    
    def create_version(self) -> 'Note':
        """Create a new version of this note"""
        from datetime import datetime
        
        # Create new note as next version
        new_version = Note(
            created_by=self.created_by,
            organization_id=self.organization_id,
            title=self.title,
            content=self.content,
            content_type=self.content_type,
            device_id=self.device_id,
            incident_id=self.incident_id,
            note_type=self.note_type,
            category=self.category,
            tags=self.tags.copy() if self.tags else [],
            access_level=self.access_level,
            department_id=self.department_id,
            team_id=self.team_id,
            version=self.version + 1,
            previous_version_id=self.id,
            attachments=self.attachments.copy() if self.attachments else [],
            note_metadata=self.note_metadata.copy() if self.note_metadata else {}
        )
        
        return new_version
    
    def add_mention(self, user_id: int, mentioned_by_user_id: int, mention_text: str, position: int):
        """Add a user mention"""
        from src.db.models.note_mention import NoteMention
        mention = NoteMention(
            note_id=self.id,
            mentioned_user_id=user_id,
            mentioned_by_user_id=mentioned_by_user_id,
            mention_text=mention_text,
            mention_position=position
        )
        self.mentions.append(mention)
    
    def share_with_user(self, user_id: int, shared_by_user_id: int, permission: str = 'view'):
        """Share note with a user"""
        from src.db.models.note_collaboration import NoteShare
        share = NoteShare(
            note_id=self.id,
            shared_with_user_id=user_id,
            shared_by_user_id=shared_by_user_id,
            permission_level=permission,
            share_type='user'
        )
        self.shares.append(share)
    
    def to_dict(self, include_content: bool = True) -> dict:
        """Convert to dictionary for API responses"""
        result = {
            "id": self.id,
            "created_by": self.created_by,
            "organization_id": self.organization_id,
            "title": self.title,
            "note_type": self.note_type,
            "category": self.category,
            "tags": self.tags,
            "access_level": self.access_level,
            "device_id": self.device_id,
            "incident_id": self.incident_id,
            "is_pinned": self.is_pinned,
            "is_archived": self.is_archived,
            "is_locked": self.is_locked,
            "version": self.version,
            "word_count": self.word_count,
            "has_attachments": len(self.attachments) > 0,
            "comment_count": len(self.comments) if hasattr(self, 'comments') else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_edited_at": self.last_edited_at.isoformat() if self.last_edited_at else None,
            "last_edited_by": self.last_edited_by,
        }
        
        if include_content:
            result["content"] = self.content
            result["content_type"] = self.content_type
            result["attachments"] = self.attachments
        
        return result
    
    def __repr__(self):
        return f"<Note {self.id}: {self.title or 'Untitled'}>"


class NoteComment(Base):
    """
    Comments on notes for team collaboration.
    """
    __tablename__ = "note_comments"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Note association
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    
    # Comment details
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    
    # Threading
    parent_comment_id = Column(Integer, ForeignKey("note_comments.id"), nullable=True)
    
    # Status
    is_edited = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    note = relationship("Note", back_populates="comments")
    user = relationship("User", backref="note_comments")
    parent_comment = relationship("NoteComment", remote_side=[id], backref="replies")
    
    # Constraints and indexes
    __table_args__ = (
        Index('idx_comment_note_created', 'note_id', 'created_at'),
        Index('idx_comment_parent', 'parent_comment_id'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "note_id": self.note_id,
            "user_id": self.user_id,
            "content": self.content if not self.is_deleted else "[deleted]",
            "parent_comment_id": self.parent_comment_id,
            "is_edited": self.is_edited,
            "is_deleted": self.is_deleted,
            "reply_count": len(self.replies) if hasattr(self, 'replies') else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<NoteComment {self.id} on Note {self.note_id}>"
