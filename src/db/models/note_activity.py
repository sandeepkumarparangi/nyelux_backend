"""
Note-related helper models - Activity tracking and sharing
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.db.base_class import Base


class NoteActivity(Base):
    """
    Track user activities on notes for audit trail
    """
    __tablename__ = "note_activities"

    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type = Column(String(50), nullable=False)  # view, edit, share, mention
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    note = relationship("Note", back_populates="activities")
    user = relationship("User", back_populates="note_activities")


class NoteShare(Base):
    """
    Track note sharing with teams
    """
    __tablename__ = "note_shares"

    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_with_team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    shared_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    permission = Column(String(20), default="view", nullable=False)  # view, edit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    note = relationship("Note", back_populates="shares")
    shared_with_team = relationship("Team", back_populates="shared_notes")
    shared_by_user = relationship("User")
