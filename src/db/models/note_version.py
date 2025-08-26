"""
NoteVersion model for tracking note history.
REAL implementation - no fake data.
"""
from sqlalchemy import Column, Integer, ForeignKey, Text, String, DateTime
from sqlalchemy.orm import relationship

from src.db.base_class import Base


class NoteVersion(Base):
    """
    Version history for notes.
    Tracks all changes to notes for audit and rollback.
    """
    __tablename__ = "note_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    
    # Snapshot of note content at this version
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    content_type = Column(String(20), nullable=False)
    
    # Who made the change
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    change_summary = Column(Text, nullable=True)
    
    # Relationships
    note = relationship("Note", back_populates="versions")
    created_by = relationship("User")
    
    def __repr__(self):
        return f"<NoteVersion {self.note_id}v{self.version_number}>"
