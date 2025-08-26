"""
Calendar and scheduling schemas.
"""
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator

from src.schemas.base import BaseSchema, TimestampMixin


# Event Attendee Schemas
class EventAttendeeBase(BaseSchema):
    """Base event attendee schema"""
    email: str = Field(..., max_length=255)
    name: Optional[str] = Field(None, max_length=255)
    response_status: Literal["pending", "accepted", "declined", "tentative"] = "pending"


class EventAttendeeResponse(EventAttendeeBase):
    """Event attendee response schema"""
    id: int
    event_id: int
    user_id: Optional[int] = None
    attended: Optional[bool] = None
    join_time: Optional[datetime] = None
    leave_time: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True  # Enable from_orm


class EventRSVP(BaseSchema):
    """RSVP update schema"""
    response_status: Literal["accepted", "declined", "tentative"]


# Calendar Event Schemas
class CalendarEventBase(BaseSchema):
    """Base calendar event schema"""
    event_type: Literal["meeting", "training", "demo", "webinar", "support_call"]
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    device_id: Optional[int] = None
    start_time: datetime
    end_time: datetime
    timezone: str = Field(..., max_length=50)
    location_type: Literal["video", "phone", "in_person"] = "video"
    location_details: Optional[str] = None
    max_attendees: Optional[int] = Field(None, ge=1, le=1000)
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    reminder_minutes: Optional[List[int]] = [15, 60, 1440]
    
    @field_validator('end_time')
    def validate_end_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v


class CalendarEventCreate(CalendarEventBase):
    """Create calendar event schema"""
    attendee_emails: Optional[List[str]] = []


class CalendarEventUpdate(BaseSchema):
    """Update calendar event schema"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    timezone: Optional[str] = Field(None, max_length=50)
    location_type: Optional[Literal["video", "phone", "in_person"]] = None
    location_details: Optional[str] = None
    max_attendees: Optional[int] = Field(None, ge=1, le=1000)
    reminder_minutes: Optional[List[int]] = None


class CalendarEventInDB(CalendarEventBase, TimestampMixin):
    """Calendar event database schema"""
    id: int
    host_id: int
    meeting_url: Optional[str] = None
    dial_in_number: Optional[str] = None
    access_code: Optional[str] = None
    status: str = "scheduled"
    recording_url: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None


class CalendarEventResponse(CalendarEventInDB):
    """Calendar event response schema"""
    host_name: Optional[str] = None
    attendees: List[EventAttendeeResponse] = []  # No quotes needed now
    attendee_count: int = 0
    
    @classmethod
    def from_orm_with_attendees(cls, event):
        """Create response with attendees"""
        data = event.__dict__.copy()
        data["host_name"] = f"{event.host.first_name} {event.host.last_name}" if event.host else None
        data["attendees"] = [EventAttendeeResponse.model_validate(a) for a in event.attendees]
        data["attendee_count"] = len(event.attendees)
        return cls(**data)


# Availability Schemas
class AvailabilitySlotBase(BaseSchema):
    """Base availability slot schema"""
    day_of_week: int = Field(..., ge=0, le=6)  # 0=Monday, 6=Sunday
    start_time: time
    end_time: time
    timezone: str = Field(..., max_length=50)
    slot_duration_minutes: int = Field(30, ge=15, le=240)
    buffer_minutes: int = Field(0, ge=0, le=60)
    is_active: bool = True
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    
    @field_validator('end_time')
    def validate_end_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v


class AvailabilitySlotCreate(AvailabilitySlotBase):
    """Create availability slot schema"""
    pass


class AvailabilitySlotUpdate(BaseSchema):
    """Update availability slot schema"""
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    timezone: Optional[str] = Field(None, max_length=50)
    slot_duration_minutes: Optional[int] = Field(None, ge=15, le=240)
    buffer_minutes: Optional[int] = Field(None, ge=0, le=60)
    is_active: Optional[bool] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None


class AvailabilitySlotResponse(AvailabilitySlotBase):
    """Availability slot response schema"""
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


# Availability Request/Response
class AvailabilityRequest(BaseSchema):
    """Request available time slots"""
    user_id: Optional[int] = None
    start_date: datetime
    end_date: datetime
    duration_minutes: int = Field(30, ge=15, le=480)
    timezone: str = Field("UTC", max_length=50)
    
    @field_validator('end_date')
    def validate_date_range(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('End date must be after start date')
        # Limit to 90 days
        if 'start_date' in values and (v - values['start_date']).days > 90:
            raise ValueError('Date range cannot exceed 90 days')
        return v


class AvailabilitySlot(BaseSchema):
    """Available time slot"""
    start: datetime
    end: datetime
    duration_minutes: int


class AvailabilityResponse(BaseSchema):
    """Available time slots response"""
    user_id: int
    timezone: str
    slots: List[AvailabilitySlot]


# Calendar Sync Schemas
class GoogleCalendarAuth(BaseSchema):
    """Google Calendar OAuth data"""
    authorization_code: str
    redirect_uri: str


class MicrosoftCalendarAuth(BaseSchema):
    """Microsoft Calendar OAuth data"""
    authorization_code: str
    redirect_uri: str


# Calendar Settings
class CalendarSettings(BaseSchema):
    """User calendar settings"""
    default_event_duration_minutes: int = Field(30, ge=15, le=480)
    default_reminder_minutes: List[int] = [15, 60]
    working_hours_start: time = time(9, 0)
    working_hours_end: time = time(17, 0)
    working_days: List[int] = [0, 1, 2, 3, 4]  # Monday to Friday
    buffer_time_minutes: int = Field(15, ge=0, le=60)
    google_calendar_connected: bool = False
    microsoft_calendar_connected: bool = False
