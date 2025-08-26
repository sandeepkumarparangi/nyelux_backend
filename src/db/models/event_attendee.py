from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Index, 
    UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship

from src.db.base_class import Base


class EventAttendee(Base):
    """
    Track event participants and their response status.
    """
    __tablename__ = "event_attendees"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Event association
    event_id = Column(Integer, ForeignKey("calendar_events.id"), nullable=False)
    
    # Attendee identification (either user or external email)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    email = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    
    # Attendance information
    response_status = Column(String(20), nullable=False, default='pending')
    attended = Column(Boolean, nullable=True, comment="Did they actually attend?")
    join_time = Column(DateTime(timezone=True), nullable=True)
    leave_time = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    event = relationship("CalendarEvent", back_populates="attendees")
    user = relationship("User", back_populates="event_attendances")
    
    # Constraints and indexes
    __table_args__ = (
        # Either user_id or email must be provided
        CheckConstraint("user_id IS NOT NULL OR email IS NOT NULL", name='check_attendee_identifier'),
        # Ensure unique attendees per event
        UniqueConstraint('event_id', 'user_id', name='uq_event_user'),
        UniqueConstraint('event_id', 'email', name='uq_event_email'),
        # Valid response statuses
        CheckConstraint("response_status IN ('pending', 'accepted', 'declined', 'tentative')", name='check_response_status'),
        # Indexes
        Index('idx_attendee_event_status', 'event_id', 'response_status'),
        Index('idx_attendee_user', 'user_id'),
    )
    
    @property
    def display_name(self) -> str:
        """Get display name for attendee"""
        if self.user:
            return self.user.full_name
        return self.name or self.email or "Unknown"
    
    @property
    def email_address(self) -> str:
        """Get email address for attendee"""
        if self.user:
            return self.user.email
        return self.email
    
    @property
    def has_responded(self) -> bool:
        """Check if attendee has responded"""
        return self.response_status != 'pending'
    
    @property
    def is_attending(self) -> bool:
        """Check if attendee accepted invitation"""
        return self.response_status == 'accepted'
    
    @property
    def attendance_duration_minutes(self) -> int:
        """Calculate attendance duration in minutes"""
        if self.join_time and self.leave_time:
            return int((self.leave_time - self.join_time).total_seconds() / 60)
        return 0
    
    def mark_attended(self, join_time=None):
        """Mark attendee as having attended"""
        from datetime import datetime
        self.attended = True
        self.join_time = join_time or datetime.utcnow()
    
    def mark_left(self, leave_time=None):
        """Mark attendee as having left"""
        from datetime import datetime
        self.leave_time = leave_time or datetime.utcnow()
    
    def update_response(self, status: str):
        """Update attendee response status"""
        valid_statuses = ['pending', 'accepted', 'declined', 'tentative']
        if status in valid_statuses:
            self.response_status = status
            self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "user_id": self.user_id,
            "email": self.email_address,
            "name": self.display_name,
            "response_status": self.response_status,
            "attended": self.attended,
            "join_time": self.join_time.isoformat() if self.join_time else None,
            "leave_time": self.leave_time.isoformat() if self.leave_time else None,
            "attendance_duration_minutes": self.attendance_duration_minutes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<EventAttendee {self.display_name}: {self.response_status}>"
