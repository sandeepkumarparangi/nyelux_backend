"""
Vendor Service Scheduling Model.
Handles HCP requests for vendor service calls and scheduling.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, 
    UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from datetime import datetime

from src.db.base_class import Base


class VendorServiceRequest(Base):
    """
    Service requests from HCPs to vendors.
    Tracks equipment service, training, and support requests.
    """
    __tablename__ = "vendor_service_requests"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Request identification
    request_number = Column(String(20), unique=True, nullable=False, index=True)
    
    # Parties involved
    vendor_profile_id = Column(Integer, ForeignKey("vendor_profiles.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)  # Vendor org
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # HCP making request
    requester_organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)  # HCP's org
    
    # Service details
    service_type = Column(String(50), nullable=False)
    # maintenance, repair, training, installation, consultation, demo, calibration
    
    urgency = Column(String(20), nullable=False, default='routine')
    # emergency (2hr), urgent (24hr), routine (72hr), scheduled
    
    # Device information
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True)
    device_serial_number = Column(String(100), nullable=True)
    device_location = Column(String(255), nullable=True)  # Room/department location
    
    # Request details
    issue_description = Column(Text, nullable=False)
    symptoms = Column(ARRAY(String), nullable=True)  # For troubleshooting
    error_codes = Column(ARRAY(String), nullable=True)
    
    # Preferred scheduling
    preferred_dates = Column(JSONB, nullable=True)  # [{"date": "2024-01-15", "time_slots": ["morning", "afternoon"]}]
    availability_notes = Column(Text, nullable=True)
    on_site_required = Column(Boolean, default=True, nullable=False)
    
    # Assignment
    assigned_rep_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Vendor rep assigned
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    assignment_notes = Column(Text, nullable=True)
    
    # Scheduling
    scheduled_date = Column(DateTime(timezone=True), nullable=True)
    scheduled_duration_minutes = Column(Integer, nullable=True)
    calendar_event_id = Column(Integer, ForeignKey("calendar_events.id"), nullable=True)
    
    # Status tracking
    status = Column(String(30), default='pending', nullable=False)
    # pending, assigned, scheduled, in_progress, completed, cancelled, no_show
    
    status_history = Column(JSONB, nullable=True)
    # [{"status": "pending", "timestamp": "2024-01-01T10:00:00", "user_id": 1, "notes": ""}]
    
    # SLA tracking
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    sla_met = Column(Boolean, nullable=True)
    response_time_minutes = Column(Integer, nullable=True)  # Time to first response
    resolution_time_minutes = Column(Integer, nullable=True)  # Time to completion
    
    # Service completion
    service_started_at = Column(DateTime(timezone=True), nullable=True)
    service_completed_at = Column(DateTime(timezone=True), nullable=True)
    service_report = Column(Text, nullable=True)
    parts_used = Column(JSONB, nullable=True)  # [{"part_number": "", "quantity": 1, "description": ""}]
    follow_up_required = Column(Boolean, default=False, nullable=False)
    follow_up_notes = Column(Text, nullable=True)
    
    # Satisfaction
    satisfaction_rating = Column(Integer, nullable=True)  # 1-5 stars
    satisfaction_feedback = Column(Text, nullable=True)
    
    # Billing (if applicable)
    billable = Column(Boolean, default=False, nullable=False)
    estimated_cost = Column(String(50), nullable=True)
    actual_cost = Column(String(50), nullable=True)
    invoice_number = Column(String(50), nullable=True)
    
    # Communication log
    internal_notes = Column(Text, nullable=True)  # Vendor-only notes
    
    # Timestamps
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    # Relationships
    vendor_profile = relationship("VendorProfile")
    vendor_organization = relationship("Organization", foreign_keys=[organization_id])
    requester = relationship("User", foreign_keys=[requester_id])
    requester_organization = relationship("Organization", foreign_keys=[requester_organization_id])
    assigned_rep = relationship("User", foreign_keys=[assigned_rep_id])
    device = relationship("VendorDevice")
    calendar_event = relationship("CalendarEvent")
    cancelled_by_user = relationship("User", foreign_keys=[cancelled_by])
    communications = relationship("VendorServiceCommunication", back_populates="service_request", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("service_type IN ('maintenance', 'repair', 'training', 'installation', " +
                       "'consultation', 'demo', 'calibration', 'inspection', 'upgrade', 'other')",
                       name='check_service_type'),
        CheckConstraint("urgency IN ('emergency', 'urgent', 'routine', 'scheduled')",
                       name='check_urgency'),
        CheckConstraint("status IN ('pending', 'assigned', 'scheduled', 'in_progress', " +
                       "'completed', 'cancelled', 'no_show', 'rescheduled')",
                       name='check_service_status'),
        CheckConstraint("satisfaction_rating IS NULL OR (satisfaction_rating >= 1 AND satisfaction_rating <= 5)",
                       name='check_satisfaction_rating'),
        Index('idx_service_request_vendor', 'vendor_profile_id', 'status'),
        Index('idx_service_request_requester', 'requester_id', 'status'),
        Index('idx_service_request_rep', 'assigned_rep_id', 'status'),
        Index('idx_service_request_urgency', 'urgency', 'status'),
        Index('idx_service_request_number', 'request_number'),
    )
    
    @property
    def is_overdue(self) -> bool:
        """Check if request is overdue based on SLA"""
        if self.status in ['completed', 'cancelled']:
            return False
        if self.sla_deadline and self.sla_deadline < datetime.utcnow():
            return True
        return False
    
    @property
    def requires_immediate_attention(self) -> bool:
        """Check if request needs immediate attention"""
        return self.urgency == 'emergency' and self.status in ['pending', 'assigned']
    
    def calculate_sla_deadline(self) -> datetime:
        """Calculate SLA deadline based on urgency"""
        from datetime import timedelta
        
        if self.urgency == 'emergency':
            return self.created_at + timedelta(hours=2)
        elif self.urgency == 'urgent':
            return self.created_at + timedelta(hours=24)
        elif self.urgency == 'routine':
            return self.created_at + timedelta(hours=72)
        else:  # scheduled
            return None  # No SLA for scheduled maintenance
    
    def __repr__(self):
        return f"<VendorServiceRequest {self.request_number}: {self.service_type} - {self.status}>"


class VendorServiceCommunication(Base):
    """
    Communication log for service requests.
    Tracks all messages between HCPs and vendor reps.
    """
    __tablename__ = "vendor_service_communications"
    
    id = Column(Integer, primary_key=True, index=True)
    service_request_id = Column(Integer, ForeignKey("vendor_service_requests.id"), nullable=False)
    
    # Sender information
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sender_type = Column(String(20), nullable=False)  # hcp, vendor_rep, system
    
    # Message details
    message_type = Column(String(30), nullable=False)
    # text, status_update, schedule_proposal, schedule_confirmation, 
    # completion_report, feedback_request, escalation
    
    message = Column(Text, nullable=False)
    
    # Attachments
    attachments = Column(JSONB, nullable=True)
    # [{"filename": "", "url": "", "type": "image/document", "size": 1024}]
    
    # Visibility
    is_internal = Column(Boolean, default=False, nullable=False)  # Vendor-only visibility
    
    # Read status
    read_by = Column(JSONB, nullable=True)  # [{"user_id": 1, "read_at": "2024-01-01T10:00:00"}]
    
    # For scheduling proposals
    proposed_dates = Column(JSONB, nullable=True)
    # [{"date": "2024-01-15", "time": "14:00", "duration_minutes": 60}]
    
    # Relationships
    service_request = relationship("VendorServiceRequest", back_populates="communications")
    sender = relationship("User")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("sender_type IN ('hcp', 'vendor_rep', 'system')",
                       name='check_sender_type'),
        CheckConstraint("message_type IN ('text', 'status_update', 'schedule_proposal', " +
                       "'schedule_confirmation', 'completion_report', 'feedback_request', " +
                       "'escalation', 'cancellation', 'attachment')",
                       name='check_message_type'),
        Index('idx_service_communication_request', 'service_request_id', 'created_at'),
    )
    
    def mark_as_read(self, user_id: int):
        """Mark message as read by a user"""
        if not self.read_by:
            self.read_by = []
        
        # Check if already read
        for read in self.read_by:
            if read['user_id'] == user_id:
                return
        
        self.read_by.append({
            'user_id': user_id,
            'read_at': datetime.utcnow().isoformat()
        })
    
    def __repr__(self):
        return f"<VendorServiceCommunication {self.message_type} for Request {self.service_request_id}>"


class VendorRepAvailability(Base):
    """
    Vendor representative availability for service calls.
    Manages scheduling availability for vendor support staff.
    """
    __tablename__ = "vendor_rep_availability"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    vendor_profile_id = Column(Integer, ForeignKey("vendor_profiles.id"), nullable=False)
    
    # Availability window
    date = Column(DateTime(timezone=True), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Capacity
    max_appointments = Column(Integer, default=1, nullable=False)
    booked_appointments = Column(Integer, default=0, nullable=False)
    
    # Service types available
    available_service_types = Column(ARRAY(String), nullable=False)
    
    # Geographic coverage
    coverage_area = Column(JSONB, nullable=True)
    # {"type": "radius", "center": {"lat": 0, "lng": 0}, "radius_miles": 50}
    # OR {"type": "regions", "regions": ["NYC", "NJ"]}
    
    # Status
    is_available = Column(Boolean, default=True, nullable=False)
    block_reason = Column(String(100), nullable=True)  # If blocked
    
    # Recurring pattern (if applicable)
    is_recurring = Column(Boolean, default=False, nullable=False)
    recurrence_pattern = Column(JSONB, nullable=True)
    # {"type": "weekly", "days": ["monday", "wednesday"], "until": "2024-12-31"}
    
    # Relationships
    user = relationship("User")
    vendor_profile = relationship("VendorProfile")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'date', 'start_time', name='uq_rep_availability'),
        CheckConstraint("end_time > start_time", name='check_time_order'),
        CheckConstraint("max_appointments > 0", name='check_positive_capacity'),
        CheckConstraint("booked_appointments >= 0 AND booked_appointments <= max_appointments",
                       name='check_booking_capacity'),
        Index('idx_rep_availability_user', 'user_id', 'date'),
        Index('idx_rep_availability_vendor', 'vendor_profile_id', 'date'),
    )
    
    @property
    def has_capacity(self) -> bool:
        """Check if there's available capacity"""
        return self.is_available and self.booked_appointments < self.max_appointments
    
    @property
    def capacity_percentage(self) -> float:
        """Calculate capacity utilization"""
        if self.max_appointments == 0:
            return 0
        return (self.booked_appointments / self.max_appointments) * 100
    
    def __repr__(self):
        return f"<VendorRepAvailability User {self.user_id} - {self.date}>"
