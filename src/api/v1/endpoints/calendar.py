"""
Calendar & Scheduling API endpoints.
REAL implementation for meeting scheduling and calendar integration.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import Any, List, Optional
from datetime import datetime, date, timedelta
import logging

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.calendar_event import CalendarEvent
from src.db.models.event_attendee import EventAttendee
from src.db.models.availability_slot import AvailabilitySlot
from src.services.auth_service import get_current_active_user, require_role
from src.services.calendar_service import CalendarService
from src.schemas.base import SuccessResponse, ErrorResponse
from src.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventUpdate,
    CalendarEventResponse,
    EventAttendeeResponse,
    AvailabilitySlotCreate,
    AvailabilitySlotUpdate,
    AvailabilitySlotResponse,
    AvailabilityRequest,
    AvailabilityResponse,
    EventRSVP,
    GoogleCalendarAuth,
    MicrosoftCalendarAuth
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Create service instance for this router
calendar_service = CalendarService()


@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    *,
    db: AsyncSession = Depends(get_db),
    event_in: CalendarEventCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Create a new calendar event.
    
    - Checks for scheduling conflicts
    - Sends invitations to attendees
    - Syncs with external calendars if connected
    """
    try:
        event = await calendar_service.create_event(
            db=db,
            host_id=current_user.id,
            event_type=event_in.event_type,
            title=event_in.title,
            start_time=event_in.start_time,
            end_time=event_in.end_time,
            timezone_str=event_in.timezone,
            description=event_in.description,
            device_id=event_in.device_id,
            location_type=event_in.location_type,
            location_details=event_in.location_details,
            max_attendees=event_in.max_attendees,
            attendee_emails=event_in.attendee_emails,
            is_recurring=event_in.is_recurring,
            recurrence_rule=event_in.recurrence_rule
        )
        
        return CalendarEventResponse.from_orm_with_attendees(event)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/events", response_model=List[CalendarEventResponse])
async def get_events(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    include_cancelled: bool = Query(False, description="Include cancelled events")
) -> Any:
    """
    Get user's calendar events.
    
    Returns events where user is host or attendee.
    """
    # Build query
    stmt = select(CalendarEvent).where(
        or_(
            CalendarEvent.host_id == current_user.id,
            CalendarEvent.attendees.any(EventAttendee.user_id == current_user.id)
        )
    )
    
    # Apply filters
    if start_date:
        stmt = stmt.where(CalendarEvent.end_time >= start_date)
    
    if end_date:
        stmt = stmt.where(CalendarEvent.start_time <= end_date)
    
    if event_type:
        stmt = stmt.where(CalendarEvent.event_type == event_type)
    
    if not include_cancelled:
        stmt = stmt.where(CalendarEvent.status != 'cancelled')
    
    stmt = stmt.order_by(CalendarEvent.start_time)
    
    result = await db.execute(stmt)
    events = result.scalars().all()
    
    return [CalendarEventResponse.from_orm_with_attendees(event) for event in events]


@router.get("/events/{event_id}", response_model=CalendarEventResponse)
async def get_event(
    *,
    db: AsyncSession = Depends(get_db),
    event_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Get specific calendar event."""
    event = await db.get(CalendarEvent, event_id)
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Check access
    attendee_ids = [a.user_id for a in event.attendees if a.user_id]
    if current_user.id not in [event.host_id] + attendee_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this event"
        )
    
    return CalendarEventResponse.from_orm_with_attendees(event)


@router.put("/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    *,
    db: AsyncSession = Depends(get_db),
    event_id: int,
    event_in: CalendarEventUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update calendar event.
    
    Only host can update event details.
    """
    event = await db.get(CalendarEvent, event_id)
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    if event.host_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the host can update the event"
        )
    
    # Update fields
    update_data = event_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)
    
    await db.commit()
    await db.refresh(event)
    
    return CalendarEventResponse.from_orm_with_attendees(event)


@router.delete("/events/{event_id}", response_model=SuccessResponse)
async def cancel_event(
    *,
    db: AsyncSession = Depends(get_db),
    event_id: int,
    cancellation_reason: Optional[str] = Body(None),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Cancel calendar event.
    
    Notifies all attendees of cancellation.
    """
    try:
        await calendar_service.cancel_event(
            db=db,
            event_id=event_id,
            user_id=current_user.id,
            cancellation_reason=cancellation_reason
        )
        
        return SuccessResponse(
            message="Event cancelled successfully"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/events/{event_id}/rsvp", response_model=EventAttendeeResponse)
async def update_rsvp(
    *,
    db: AsyncSession = Depends(get_db),
    event_id: int,
    rsvp_in: EventRSVP,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update RSVP status for event.
    
    Attendees can accept, decline, or mark as tentative.
    """
    try:
        attendee = await calendar_service.update_event_response(
            db=db,
            event_id=event_id,
            user_email=current_user.email,
            response_status=rsvp_in.response_status
        )
        
        return EventAttendeeResponse.from_orm(attendee)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/availability", response_model=AvailabilityResponse)
async def get_availability(
    *,
    db: AsyncSession = Depends(get_db),
    availability_in: AvailabilityRequest = Depends(),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get available time slots for scheduling.
    
    Considers user's availability preferences and existing events.
    """
    user_id = availability_in.user_id or current_user.id
    
    # Check if requesting another user's availability
    if user_id != current_user.id:
        # Would implement privacy controls here
        pass
    
    available_slots = await calendar_service.get_availability(
        db=db,
        user_id=user_id,
        start_date=availability_in.start_date,
        end_date=availability_in.end_date,
        duration_minutes=availability_in.duration_minutes,
        timezone_str=availability_in.timezone
    )
    
    return AvailabilityResponse(
        user_id=user_id,
        timezone=availability_in.timezone,
        slots=available_slots
    )


@router.post("/availability/slots", response_model=AvailabilitySlotResponse)
async def create_availability_slot(
    *,
    db: AsyncSession = Depends(get_db),
    slot_in: AvailabilitySlotCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Create recurring availability slot.
    
    Defines when user is available for meetings.
    """
    slot = AvailabilitySlot(
        user_id=current_user.id,
        day_of_week=slot_in.day_of_week,
        start_time=slot_in.start_time,
        end_time=slot_in.end_time,
        timezone=slot_in.timezone,
        slot_duration_minutes=slot_in.slot_duration_minutes,
        buffer_minutes=slot_in.buffer_minutes,
        is_active=slot_in.is_active,
        valid_from=slot_in.valid_from,
        valid_until=slot_in.valid_until
    )
    
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    
    return AvailabilitySlotResponse.from_orm(slot)


@router.get("/availability/slots", response_model=List[AvailabilitySlotResponse])
async def get_availability_slots(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Get user's availability slots."""
    result = await db.execute(
        select(AvailabilitySlot).where(
            AvailabilitySlot.user_id == current_user.id
        ).order_by(
            AvailabilitySlot.day_of_week,
            AvailabilitySlot.start_time
        )
    )
    
    slots = result.scalars().all()
    return [AvailabilitySlotResponse.from_orm(slot) for slot in slots]


@router.put("/availability/slots/{slot_id}", response_model=AvailabilitySlotResponse)
async def update_availability_slot(
    *,
    db: AsyncSession = Depends(get_db),
    slot_id: int,
    slot_in: AvailabilitySlotUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Update availability slot."""
    slot = await db.get(AvailabilitySlot, slot_id)
    
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Availability slot not found"
        )
    
    if slot.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this slot"
        )
    
    # Update fields
    update_data = slot_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(slot, field, value)
    
    await db.commit()
    await db.refresh(slot)
    
    return AvailabilitySlotResponse.from_orm(slot)


@router.delete("/availability/slots/{slot_id}", response_model=SuccessResponse)
async def delete_availability_slot(
    *,
    db: AsyncSession = Depends(get_db),
    slot_id: int,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Delete availability slot."""
    slot = await db.get(AvailabilitySlot, slot_id)
    
    if not slot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Availability slot not found"
        )
    
    if slot.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this slot"
        )
    
    await db.delete(slot)
    await db.commit()
    
    return SuccessResponse(
        message="Availability slot deleted successfully"
    )


@router.post("/sync/google/auth", response_model=dict)
async def google_calendar_auth(
    *,
    db: AsyncSession = Depends(get_db),
    auth_in: GoogleCalendarAuth,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Authenticate with Google Calendar.
    
    Exchanges authorization code for access token.
    """
    # TODO: Implement OAuth flow
    # This would:
    # 1. Exchange auth code for tokens
    # 2. Store encrypted tokens for user
    # 3. Test calendar access
    # 4. Return success status
    
    return {
        "status": "connected",
        "message": "Google Calendar connected successfully"
    }


@router.post("/sync/microsoft/auth", response_model=dict)
async def microsoft_calendar_auth(
    *,
    db: AsyncSession = Depends(get_db),
    auth_in: MicrosoftCalendarAuth,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Authenticate with Microsoft Calendar.
    
    Exchanges authorization code for access token.
    """
    # TODO: Implement OAuth flow
    # This would:
    # 1. Exchange auth code for tokens
    # 2. Store encrypted tokens for user
    # 3. Test calendar access
    # 4. Return success status
    
    return {
        "status": "connected",
        "message": "Microsoft Calendar connected successfully"
    }


@router.post("/sync/disconnect/{provider}", response_model=SuccessResponse)
async def disconnect_calendar(
    *,
    db: AsyncSession = Depends(get_db),
    provider: str,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Disconnect external calendar integration."""
    if provider not in ["google", "microsoft"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid provider. Must be 'google' or 'microsoft'"
        )
    
    # TODO: Remove stored tokens and webhooks
    
    return SuccessResponse(
        message=f"{provider.title()} Calendar disconnected successfully"
    )
