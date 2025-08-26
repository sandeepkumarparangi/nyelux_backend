from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Time,
    Index, CheckConstraint, UniqueConstraint, Date
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from src.db.base_class import Base

class CalendarEvent(Base):
    """
    Meeting and training scheduling.
    Supports recurring events and calendar integration.
    """
    __tablename__ = "calendar_events"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Event details
    event_type = Column(String(50), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    
    # Host and device
    host_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True)
    
    # Timing
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False)
    timezone = Column(String(50), nullable=False)
    
    # Location
    location_type = Column(String(20), nullable=False)  # video, phone, in_person
    location_details = Column(Text, nullable=True)
    meeting_url = Column(Text, nullable=True)
    dial_in_number = Column(String(50), nullable=True)
    access_code = Column(String(50), nullable=True)
    
    # Capacity
    max_attendees = Column(Integer, nullable=True)
    
    # Recurrence
    is_recurring = Column(Boolean, default=False, nullable=False)
    recurrence_rule = Column(Text, nullable=True)  # RRULE format
    recurrence_id = Column(String(100), nullable=True, index=True)  # Groups recurring events
    
    # Status
    status = Column(String(20), default='scheduled', nullable=False, index=True)
    
    # Recording
    recording_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Reminders
    reminder_minutes = Column(ARRAY(Integer), nullable=True)  # [15, 60] = 15 min and 1 hour before
    
    # Cancellation
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationships
    host = relationship("User", back_populates="hosted_events", foreign_keys=[host_id])
    creator = relationship("User", back_populates="created_events", foreign_keys=[created_by])
    attendees = relationship("EventAttendee", back_populates="event", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('meeting', 'training', 'demo', 'webinar', 'support_call')", 
            name='check_event_type'
        ),
        CheckConstraint("location_type IN ('video', 'phone', 'in_person')", name='check_location_type'),
        CheckConstraint("status IN ('scheduled', 'in_progress', 'completed', 'cancelled')", name='check_event_status'),
        CheckConstraint("end_time > start_time", name='check_event_time_order'),
        CheckConstraint("max_attendees > 0", name='check_max_attendees_positive'),
        Index('idx_start_time', 'start_time'),
        Index('idx_host_start', 'host_id', 'start_time'),
        Index('idx_status', 'status'),
        Index('idx_recurrence_id', 'recurrence_id'),
    )
    
    @property
    def duration_minutes(self) -> int:
        """Get event duration in minutes"""
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)
    
    @property
    def is_upcoming(self) -> bool:
        """Check if event is upcoming"""
        from datetime import datetime
        return self.start_time > datetime.utcnow() and self.status == 'scheduled'
    
    @property
    def is_past(self) -> bool:
        """Check if event is past"""
        from datetime import datetime
        return self.end_time < datetime.utcnow()
    
    @property
    def attendee_count(self) -> int:
        """Get current attendee count"""
        return len([a for a in self.attendees if a.response_status == 'accepted'])
    
    @property
    def is_full(self) -> bool:
        """Check if event is at capacity"""
        if not self.max_attendees:
            return False
        return self.attendee_count >= self.max_attendees
    
    def get_ics_data(self) -> str:
        """Generate iCalendar data for the event"""
        from datetime import datetime
        import uuid
        
        # Basic ICS format
        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Nyelux//Medical Device Intelligence//EN",
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4()}@nyelux.com",
            f"DTSTART:{self.start_time.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{self.end_time.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{self.title}",
        ]
        
        if self.description:
            ics_lines.append(f"DESCRIPTION:{self.description}")
        
        if self.location_type == 'video' and self.meeting_url:
            ics_lines.append(f"LOCATION:{self.meeting_url}")
        elif self.location_details:
            ics_lines.append(f"LOCATION:{self.location_details}")
        
        if self.is_recurring and self.recurrence_rule:
            ics_lines.append(f"RRULE:{self.recurrence_rule}")
        
        ics_lines.extend([
            f"STATUS:CONFIRMED",
            f"SEQUENCE:0",
            "END:VEVENT",
            "END:VCALENDAR"
        ])
        
        return "\r\n".join(ics_lines)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "host_id": self.host_id,
            "device_id": self.device_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "timezone": self.timezone,
            "duration_minutes": self.duration_minutes,
            "location_type": self.location_type,
            "location_details": self.location_details,
            "meeting_url": self.meeting_url,
            "max_attendees": self.max_attendees,
            "attendee_count": self.attendee_count,
            "is_full": self.is_full,
            "is_recurring": self.is_recurring,
            "status": self.status,
            "is_upcoming": self.is_upcoming,
            "is_past": self.is_past,
            "has_recording": bool(self.recording_url),
            "reminder_minutes": self.reminder_minutes or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<CalendarEvent {self.id}: {self.title}>"

