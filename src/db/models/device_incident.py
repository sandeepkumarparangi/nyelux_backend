from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text,
    Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY
import secrets
import string

from src.db.base_class import Base

class DeviceIncident(Base):
    """
    Device issue reporting and tracking.
    Handles malfunctions, damages, safety issues, etc.
    """
    __tablename__ = "device_incidents"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Unique ticket number
    ticket_number = Column(String(20), unique=True, nullable=False, index=True)
    
    # Device and organization
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    
    # People involved
    reported_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Incident details
    incident_type = Column(String(50), nullable=False, index=True)
    incident_date = Column(DateTime(timezone=True), nullable=False, index=True)
    description = Column(Text, nullable=False)
    
    # Impact and urgency
    patient_impact = Column(String(50), nullable=True)
    urgency = Column(String(20), nullable=False, index=True)
    
    # Status tracking
    status = Column(String(50), default='open', nullable=False, index=True)
    
    # Resolution details
    resolution_summary = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    corrective_actions = Column(Text, nullable=True)
    
    # Device identification
    serial_number = Column(String(100), nullable=True)
    lot_number = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    
    # Additional information
    witnesses = Column(ARRAY(Text), nullable=True)
    vendor_ticket_id = Column(String(100), nullable=True)
    
    # FDA reporting
    fda_reportable = Column(Boolean, default=False, nullable=False)
    fda_report_number = Column(String(100), nullable=True)
    
    # Timestamps
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    first_response_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    device = relationship("VendorDevice", back_populates="incidents")
    organization = relationship("Organization", back_populates="device_incidents")
    reporter = relationship("User", back_populates="reported_incidents", foreign_keys=[reported_by])
    assignee = relationship("User", back_populates="assigned_incidents", foreign_keys=[assigned_to])
    attachments = relationship("IncidentAttachment", back_populates="incident", cascade="all, delete-orphan")
    comments = relationship("IncidentComment", back_populates="incident", cascade="all, delete-orphan", order_by="IncidentComment.created_at")
    notes = relationship("Note", back_populates="incident")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "incident_type IN ('malfunction', 'damage', 'safety_issue', 'user_error', 'other')", 
            name='check_incident_type'
        ),
        CheckConstraint(
            "urgency IN ('critical', 'high', 'medium', 'low')", 
            name='check_urgency'
        ),
        CheckConstraint(
            "status IN ('open', 'assigned', 'in_progress', 'pending_info', 'resolved', 'closed')", 
            name='check_incident_status'
        ),
        CheckConstraint(
            "patient_impact IN ('none', 'minor', 'moderate', 'severe', 'death')", 
            name='check_patient_impact'
        ),
        Index('idx_status_urgency', 'status', 'urgency'),
        Index('idx_device_created', 'device_id', 'created_at'),
        Index('idx_incident_date', 'incident_date'),
    )
    
    def __init__(self, **kwargs):
        """Initialize with auto-generated ticket number"""
        super().__init__(**kwargs)
        if not self.ticket_number:
            self.ticket_number = self.generate_ticket_number()
    
    @staticmethod
    def generate_ticket_number() -> str:
        """Generate unique ticket number"""
        # Format: INC-YYYYMM-XXXX
        from datetime import datetime
        date_part = datetime.utcnow().strftime("%Y%m")
        random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        return f"INC-{date_part}-{random_part}"
    
    @property
    def is_overdue(self) -> bool:
        """Check if incident is overdue based on urgency SLA"""
        if self.status in ['resolved', 'closed']:
            return False
        
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        
        # SLA times based on urgency
        sla_hours = {
            'critical': 1,  # 1 hour
            'high': 4,      # 4 hours
            'medium': 24,   # 24 hours
            'low': 72       # 72 hours
        }
        
        sla_time = self.created_at + timedelta(hours=sla_hours.get(self.urgency, 24))
        return now > sla_time
    
    @property
    def response_time_minutes(self) -> int:
        """Calculate response time in minutes"""
        if not self.first_response_at:
            return None
        delta = self.first_response_at - self.created_at
        return int(delta.total_seconds() / 60)
    
    @property
    def resolution_time_hours(self) -> float:
        """Calculate resolution time in hours"""
        if not self.resolved_at:
            return None
        delta = self.resolved_at - self.created_at
        return round(delta.total_seconds() / 3600, 1)
    
    def requires_fda_reporting(self) -> bool:
        """Determine if incident requires FDA reporting"""
        # Critical safety issues always require reporting
        if self.incident_type == 'safety_issue' and self.urgency == 'critical':
            return True
        
        # Severe patient impact requires reporting
        if self.patient_impact in ['severe', 'death']:
            return True
        
        # Device malfunction in life-supporting devices
        if self.device and self.device.gudid_device and self.device.gudid_device.life_supporting:
            if self.incident_type == 'malfunction':
                return True
        
        return self.fda_reportable
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "ticket_number": self.ticket_number,
            "device_id": self.device_id,
            "incident_type": self.incident_type,
            "incident_date": self.incident_date.isoformat() if self.incident_date else None,
            "description": self.description,
            "patient_impact": self.patient_impact,
            "urgency": self.urgency,
            "status": self.status,
            "is_overdue": self.is_overdue,
            "requires_fda_reporting": self.requires_fda_reporting(),
            "fda_report_number": self.fda_report_number,
            "response_time_minutes": self.response_time_minutes,
            "resolution_time_hours": self.resolution_time_hours,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<DeviceIncident {self.ticket_number}: {self.incident_type}>"
