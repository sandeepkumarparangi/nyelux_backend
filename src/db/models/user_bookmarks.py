from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, ARRAY, Text, Index,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import secrets

from src.db.base_class import Base


class UserBookmark(Base):
    """
    Save favorites across different resource types (devices, documents, videos, etc.)
    """
    __tablename__ = "user_bookmarks"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User association
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Bookmarked resource
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(255), nullable=False)
    
    # Bookmark metadata
    title = Column(String(500), nullable=True, comment="Cached title for quick display")
    notes = Column(Text, nullable=True, comment="User notes about the bookmark")
    tags = Column(ARRAY(String), nullable=True, comment="User-defined tags")
    
    # Organization
    folder = Column(String(100), nullable=True, comment="User-defined folder/category")
    position = Column(Integer, nullable=True, comment="Order within folder")
    
    # Relationships
    user = relationship("User", back_populates="bookmarks")
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('user_id', 'resource_type', 'resource_id', name='uq_user_bookmark'),
        Index('idx_bookmark_user_folder', 'user_id', 'folder'),
        Index('idx_bookmark_user_type', 'user_id', 'resource_type'),
        Index('idx_bookmark_user_created', 'user_id', 'created_at'),
    )
    
    @property
    def resource_url(self) -> str:
        """Get URL to the bookmarked resource"""
        url_patterns = {
            'device': f'/devices/{self.resource_id}',
            'document': f'/documents/{self.resource_id}',
            'video': f'/videos/{self.resource_id}',
            'search': f'/search?saved={self.resource_id}',
            'comparison': f'/comparisons/{self.resource_id}',
        }
        return url_patterns.get(self.resource_type, f'/{self.resource_type}/{self.resource_id}')
    
    @property
    def has_tags(self) -> bool:
        """Check if bookmark has tags"""
        return bool(self.tags and len(self.tags) > 0)
    
    def add_tag(self, tag: str):
        """Add a tag to the bookmark"""
        if self.tags is None:
            self.tags = []
        tag = tag.lower().strip()
        if tag and tag not in self.tags:
            self.tags.append(tag)
    
    def remove_tag(self, tag: str):
        """Remove a tag from the bookmark"""
        if self.tags:
            tag = tag.lower().strip()
            self.tags = [t for t in self.tags if t != tag]
    
    def move_to_folder(self, folder: str, position: int = None):
        """Move bookmark to a different folder"""
        self.folder = folder
        self.position = position
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_url": self.resource_url,
            "title": self.title,
            "notes": self.notes,
            "tags": self.tags or [],
            "folder": self.folder,
            "position": self.position,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<UserBookmark {self.id}: {self.resource_type}/{self.resource_id}>"
