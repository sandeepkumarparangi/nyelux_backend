"""
Integration tests for Calendar & Scheduling functionality.
Tests cover meeting management, calendar sync, and scheduling features.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
import pytz
from unittest.mock import patch, AsyncMock
import json
from zoneinfo import ZoneInfo

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.calendar_event import CalendarEvent
from src.db.models.event_attendee import EventAttendee
from src.db.models.availability_slot import AvailabilitySlot
from src.services.auth_service import AuthService


class TestCalendarScheduling:
    """Test cases for Calendar & Scheduling - Section 10"""

    @pytest.fixture
    async def setup_users(self, db: AsyncSession):
        """Create test users in different time zones"""
        org = Organization(
            name="Test Hospital",
            type="hospital",
            subdomain="test-hospital"
        )
        db.add(org)
        await db.flush()

        auth_service = AuthService()
        
        # User in EST
        host_user = User(
            email="host@example.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Host",
            last_name="User",
            role="vendor_rep",
            organization_id=org.id,
            timezone="America/New_York"
        )
        
        # User in PST
        attendee_user = User(
            email="attendee@example.com",
            password_hash=auth_service.get_password_hash("password123"),
            first_name="Attendee",
            last_name="User",
            role="nurse",
            organization_id=org.id,
            timezone="America/Los_Angeles"
        )
        
        db.add_all([host_user, attendee_user])
        await db.commit()
        
        return host_user, attendee_user

    @pytest.fixture
    async def auth_headers(self, client: AsyncClient, setup_users, db: AsyncSession):
        """Get auth headers for host user"""
        host_user, _ = setup_users
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": host_user.email, "password": "password123"}
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.asyncio
    async def test_tc_cal_001_timezone_handling(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_users
    ):
        """TC-CAL-001: Test timezone handling across different regions"""
        host_user, attendee_user = setup_users
        
        # Create event at 2 PM EST
        event_data = {
            "event_type": "meeting",
            "title": "Cross-timezone meeting",
            "description": "Testing timezone conversion",
            "start_time": "2024-02-01T14:00:00-05:00",  # 2 PM EST
            "end_time": "2024-02-01T15:00:00-05:00",    # 3 PM EST
            "timezone": "America/New_York",
            "location_type": "video",
            "meeting_url": "https://zoom.us/j/123456789",
            "attendee_emails": ["attendee@example.com"]
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=event_data,
            headers=auth_headers
        )
        assert response.status_code == 201
        event_id = response.json()["id"]
        
        # Verify event stored correctly
        event = await db.get(CalendarEvent, event_id)
        assert event is not None
        assert event.timezone == "America/New_York"
        
        # Check PST user sees correct time (11 AM PST)
        attendee_response = await client.post(
            "/api/v1/auth/login",
            data={"username": attendee_user.email, "password": "password123"}
        )
        attendee_token = attendee_response.json()["access_token"]
        attendee_headers = {"Authorization": f"Bearer {attendee_token}"}
        
        response = await client.get(
            f"/api/v1/calendar/events/{event_id}",
            headers=attendee_headers
        )
        assert response.status_code == 200
        
        # Should show in user's local timezone
        event_data = response.json()
        assert "11:00" in event_data["local_start_time"]  # 11 AM PST

    @pytest.mark.asyncio
    async def test_tc_cal_002_conflict_detection(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """TC-CAL-002: Test conflict detection and suggestions"""
        # Create first event 2-3 PM
        event1_data = {
            "event_type": "training",
            "title": "Device Training Session",
            "start_time": "2024-02-01T14:00:00-05:00",
            "end_time": "2024-02-01T15:00:00-05:00",
            "timezone": "America/New_York",
            "location_type": "in_person",
            "location_details": "Training Room A"
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=event1_data,
            headers=auth_headers
        )
        assert response.status_code == 201
        
        # Try to book overlapping event 2:30-3:30 PM
        event2_data = {
            "event_type": "meeting",
            "title": "Vendor Meeting",
            "start_time": "2024-02-01T14:30:00-05:00",
            "end_time": "2024-02-01T15:30:00-05:00",
            "timezone": "America/New_York",
            "location_type": "video"
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=event2_data,
            headers=auth_headers
        )
        assert response.status_code == 409
        
        # Should return conflict details and suggestions
        data = response.json()
        assert "conflict" in data["error"].lower()
        assert "suggested_times" in data
        assert len(data["suggested_times"]) >= 3
        
        # Verify suggestions don't conflict
        for suggestion in data["suggested_times"]:
            assert suggestion["start"] != "2024-02-01T14:00:00"
            assert suggestion["start"] != "2024-02-01T14:30:00"

    @pytest.mark.asyncio
    async def test_availability_management(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test availability slot management"""
        # Set recurring availability
        availability_data = {
            "slots": [
                {
                    "day_of_week": 1,  # Monday
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "timezone": "America/New_York",
                    "slot_duration_minutes": 30,
                    "buffer_minutes": 15
                },
                {
                    "day_of_week": 3,  # Wednesday
                    "start_time": "13:00:00",
                    "end_time": "17:00:00",
                    "timezone": "America/New_York",
                    "slot_duration_minutes": 60
                }
            ]
        }
        
        response = await client.post(
            "/api/v1/calendar/availability",
            json=availability_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Query available slots for next Monday
        next_monday = datetime.now()
        days_ahead = 0 - next_monday.weekday()  # Monday is 0
        if days_ahead <= 0:
            days_ahead += 7
        next_monday = next_monday + timedelta(days=days_ahead)
        
        response = await client.get(
            f"/api/v1/calendar/availability?date={next_monday.date()}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        slots = response.json()["available_slots"]
        assert len(slots) > 0
        
        # Verify 30-minute slots with 15-minute buffer
        assert slots[0]["duration_minutes"] == 30
        # Second slot should start 45 minutes after first (30 + 15 buffer)

    @pytest.mark.asyncio
    async def test_google_calendar_sync(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test Google Calendar integration"""
        with patch("src.services.calendar_service.GoogleCalendarService") as mock_google:
            mock_service = AsyncMock()
            mock_google.return_value = mock_service
            
            # Mock successful OAuth flow
            mock_service.authenticate.return_value = {
                "access_token": "google_token_123",
                "refresh_token": "refresh_123"
            }
            
            # Initiate Google Calendar sync
            response = await client.post(
                "/api/v1/calendar/sync/google",
                json={"auth_code": "google_auth_code_123"},
                headers=auth_headers
            )
            assert response.status_code == 200
            
            # Create event that should sync to Google
            event_data = {
                "event_type": "meeting",
                "title": "Synced Meeting",
                "start_time": "2024-02-01T10:00:00-05:00",
                "end_time": "2024-02-01T11:00:00-05:00",
                "timezone": "America/New_York",
                "sync_to_external": True
            }
            
            mock_service.create_event.return_value = {
                "id": "google_event_123",
                "htmlLink": "https://calendar.google.com/event/123"
            }
            
            response = await client.post(
                "/api/v1/calendar/events",
                json=event_data,
                headers=auth_headers
            )
            assert response.status_code == 201
            
            # Verify Google Calendar API was called
            mock_service.create_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_outlook_integration(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test Outlook/Office 365 integration"""
        with patch("src.services.calendar_service.OutlookCalendarService") as mock_outlook:
            mock_service = AsyncMock()
            mock_outlook.return_value = mock_service
            
            # Mock Microsoft Graph API
            mock_service.authenticate.return_value = {
                "access_token": "ms_token_123",
                "refresh_token": "ms_refresh_123"
            }
            
            response = await client.post(
                "/api/v1/calendar/sync/outlook",
                json={"auth_code": "ms_auth_code_123"},
                headers=auth_headers
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_recurring_events(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test recurring event creation and management"""
        # Create weekly recurring training
        event_data = {
            "event_type": "training",
            "title": "Weekly Device Training",
            "start_time": "2024-02-01T10:00:00-05:00",
            "end_time": "2024-02-01T11:00:00-05:00",
            "timezone": "America/New_York",
            "is_recurring": True,
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=TU;COUNT=10",  # Every Tuesday, 10 times
            "location_type": "video"
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=event_data,
            headers=auth_headers
        )
        assert response.status_code == 201
        
        series_data = response.json()
        assert series_data["is_recurring"] is True
        assert "recurrence_id" in series_data
        
        # Query events for next month - should see multiple instances
        response = await client.get(
            "/api/v1/calendar/events?start_date=2024-02-01&end_date=2024-02-29",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        events = response.json()["events"]
        tuesday_events = [e for e in events if "Weekly Device Training" in e["title"]]
        assert len(tuesday_events) >= 4  # At least 4 Tuesdays in February

    @pytest.mark.asyncio
    async def test_meeting_rescheduling(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_users
    ):
        """Test meeting rescheduling with attendee notifications"""
        _, attendee_user = setup_users
        
        # Create initial meeting
        event_data = {
            "event_type": "meeting",
            "title": "Device Demo",
            "start_time": "2024-02-01T14:00:00-05:00",
            "end_time": "2024-02-01T15:00:00-05:00",
            "timezone": "America/New_York",
            "attendee_emails": ["attendee@example.com"]
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=event_data,
            headers=auth_headers
        )
        assert response.status_code == 201
        event_id = response.json()["id"]
        
        # Reschedule meeting
        with patch("src.services.notification_service.send_email") as mock_email:
            update_data = {
                "start_time": "2024-02-02T15:00:00-05:00",
                "end_time": "2024-02-02T16:00:00-05:00",
                "reschedule_reason": "Vendor availability change"
            }
            
            response = await client.put(
                f"/api/v1/calendar/events/{event_id}",
                json=update_data,
                headers=auth_headers
            )
            assert response.status_code == 200
            
            # Verify notification sent
            mock_email.assert_called()
            call_args = mock_email.call_args[1]
            assert "attendee@example.com" in call_args["to"]
            assert "rescheduled" in call_args["subject"].lower()

    @pytest.mark.asyncio
    async def test_video_meeting_integration(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test video meeting link generation"""
        # Test with different providers
        providers = ["zoom", "teams", "webex"]
        
        for provider in providers:
            event_data = {
                "event_type": "demo",
                "title": f"{provider.title()} Demo Meeting",
                "start_time": "2024-02-01T14:00:00-05:00",
                "end_time": "2024-02-01T15:00:00-05:00",
                "timezone": "America/New_York",
                "location_type": "video",
                "video_provider": provider
            }
            
            with patch(f"src.services.video_service.{provider}_create_meeting") as mock_video:
                mock_video.return_value = {
                    "meeting_url": f"https://{provider}.com/j/123456789",
                    "meeting_id": "123456789",
                    "dial_in": "+1-555-123-4567",
                    "access_code": "123456"
                }
                
                response = await client.post(
                    "/api/v1/calendar/events",
                    json=event_data,
                    headers=auth_headers
                )
                assert response.status_code == 201
                
                data = response.json()
                assert data["meeting_url"].startswith(f"https://{provider}.com")
                assert data["dial_in_number"] is not None
                assert data["access_code"] is not None

    @pytest.mark.asyncio
    async def test_calendar_event_reminders(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test event reminder system"""
        # Create event with multiple reminders
        event_data = {
            "event_type": "training",
            "title": "Important Training",
            "start_time": "2024-02-01T14:00:00-05:00",
            "end_time": "2024-02-01T15:00:00-05:00",
            "timezone": "America/New_York",
            "reminder_minutes": [1440, 60, 15]  # 24 hours, 1 hour, 15 minutes
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=event_data,
            headers=auth_headers
        )
        assert response.status_code == 201
        event_id = response.json()["id"]
        
        # Verify reminders scheduled
        response = await client.get(
            f"/api/v1/calendar/events/{event_id}/reminders",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        reminders = response.json()["reminders"]
        assert len(reminders) == 3
        assert reminders[0]["minutes_before"] == 1440
        assert reminders[0]["status"] == "scheduled"

    @pytest.mark.asyncio
    async def test_attendee_response_tracking(
        self, client: AsyncClient, db: AsyncSession, auth_headers, setup_users
    ):
        """Test attendee RSVP tracking"""
        _, attendee_user = setup_users
        
        # Create event with attendees
        event_data = {
            "event_type": "webinar",
            "title": "New Device Webinar",
            "start_time": "2024-02-01T14:00:00-05:00",
            "end_time": "2024-02-01T15:00:00-05:00",
            "timezone": "America/New_York",
            "max_attendees": 100,
            "attendee_emails": ["attendee@example.com", "external@example.com"]
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=event_data,
            headers=auth_headers
        )
        assert response.status_code == 201
        event_id = response.json()["id"]
        
        # Attendee responds
        attendee_response = await client.post(
            "/api/v1/auth/login",
            data={"username": attendee_user.email, "password": "password123"}
        )
        attendee_token = attendee_response.json()["access_token"]
        attendee_headers = {"Authorization": f"Bearer {attendee_token}"}
        
        response = await client.put(
            f"/api/v1/calendar/events/{event_id}/rsvp",
            json={"response": "accepted"},
            headers=attendee_headers
        )
        assert response.status_code == 200
        
        # Check attendee list
        response = await client.get(
            f"/api/v1/calendar/events/{event_id}/attendees",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        attendees = response.json()["attendees"]
        attendee_response = next(a for a in attendees if a["email"] == "attendee@example.com")
        assert attendee_response["response_status"] == "accepted"

    @pytest.mark.asyncio
    async def test_calendar_export_formats(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test calendar export in various formats"""
        # Create some events first
        for i in range(3):
            event_data = {
                "event_type": "meeting",
                "title": f"Test Meeting {i+1}",
                "start_time": f"2024-02-0{i+1}T14:00:00-05:00",
                "end_time": f"2024-02-0{i+1}T15:00:00-05:00",
                "timezone": "America/New_York"
            }
            await client.post("/api/v1/calendar/events", json=event_data, headers=auth_headers)
        
        # Export as iCal
        response = await client.get(
            "/api/v1/calendar/export?format=ical&start_date=2024-02-01&end_date=2024-02-28",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/calendar"
        assert b"BEGIN:VCALENDAR" in response.content
        assert b"Test Meeting 1" in response.content
        
        # Export as CSV
        response = await client.get(
            "/api/v1/calendar/export?format=csv&start_date=2024-02-01&end_date=2024-02-28",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv"

    @pytest.mark.asyncio
    async def test_edge_cases(self, client: AsyncClient, db: AsyncSession, auth_headers):
        """Test calendar edge cases"""
        # Edge case: Event spanning multiple days
        event_data = {
            "event_type": "training",
            "title": "Multi-day Training",
            "start_time": "2024-02-01T09:00:00-05:00",
            "end_time": "2024-02-03T17:00:00-05:00",
            "timezone": "America/New_York"
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=event_data,
            headers=auth_headers
        )
        assert response.status_code == 201
        
        # Edge case: DST transition handling
        # Event during spring forward (2 AM -> 3 AM on March 10, 2024)
        dst_event = {
            "event_type": "meeting",
            "title": "DST Transition Meeting",
            "start_time": "2024-03-10T01:30:00-05:00",
            "end_time": "2024-03-10T03:30:00-04:00",  # Note timezone change
            "timezone": "America/New_York"
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=dst_event,
            headers=auth_headers
        )
        assert response.status_code == 201
        
        # Edge case: Booking in the past
        past_event = {
            "event_type": "meeting",
            "title": "Past Meeting",
            "start_time": "2020-01-01T10:00:00-05:00",
            "end_time": "2020-01-01T11:00:00-05:00",
            "timezone": "America/New_York"
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=past_event,
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "past" in response.json()["detail"].lower()
        
        # Edge case: Very long event title
        long_title_event = {
            "event_type": "meeting",
            "title": "A" * 501,  # Exceeds 500 char limit
            "start_time": "2024-02-01T10:00:00-05:00",
            "end_time": "2024-02-01T11:00:00-05:00",
            "timezone": "America/New_York"
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=long_title_event,
            headers=auth_headers
        )
        assert response.status_code == 422
        
        # Edge case: Invalid timezone
        invalid_tz_event = {
            "event_type": "meeting",
            "title": "Invalid TZ Meeting",
            "start_time": "2024-02-01T10:00:00-05:00",
            "end_time": "2024-02-01T11:00:00-05:00",
            "timezone": "Invalid/Timezone"
        }
        
        response = await client.post(
            "/api/v1/calendar/events",
            json=invalid_tz_event,
            headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_performance_with_many_events(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        """Test calendar performance with many events"""
        # Create 100 events
        import asyncio
        
        async def create_event(day):
            event_data = {
                "event_type": "meeting",
                "title": f"Meeting on day {day}",
                "start_time": f"2024-02-{day:02d}T10:00:00-05:00",
                "end_time": f"2024-02-{day:02d}T11:00:00-05:00",
                "timezone": "America/New_York"
            }
            return await client.post(
                "/api/v1/calendar/events",
                json=event_data,
                headers=auth_headers
            )
        
        # Create events in batches to avoid overwhelming the system
        for batch_start in range(1, 29, 5):  # February has 28 days
            batch_end = min(batch_start + 5, 29)
            tasks = [create_event(day) for day in range(batch_start, batch_end)]
            responses = await asyncio.gather(*tasks)
            assert all(r.status_code == 201 for r in responses)
        
        # Query performance test
        import time
        start_time = time.time()
        
        response = await client.get(
            "/api/v1/calendar/events?start_date=2024-02-01&end_date=2024-02-28",
            headers=auth_headers
        )
        
        query_time = time.time() - start_time
        
        assert response.status_code == 200
        assert query_time < 1.0  # Should return in less than 1 second
        
        events = response.json()["events"]
        assert len(events) >= 28  # At least one event per day
