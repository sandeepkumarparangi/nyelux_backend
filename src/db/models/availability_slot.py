from sqlalchemy import (
    Column, Integer, Time, Date, String, Boolean, ForeignKey, Index, 
    CheckConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime, time, timedelta

from src.db.base_class import Base


class AvailabilitySlot(Base):
    """
    Define recurring availability for users (e.g., vendor reps' office hours).
    """
    __tablename__ = "availability_slots"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User association
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Schedule details
    day_of_week = Column(Integer, nullable=False, comment="0=Monday, 6=Sunday")
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    timezone = Column(String(50), nullable=False)
    
    # Booking configuration
    slot_duration_minutes = Column(Integer, nullable=False, default=30)
    buffer_minutes = Column(Integer, nullable=False, default=0, comment="Buffer between slots")
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    valid_from = Column(Date, nullable=True, comment="Start date for this availability")
    valid_until = Column(Date, nullable=True, comment="End date for this availability")
    
    # Relationships
    user = relationship("User", back_populates="availability_slots")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name='check_valid_day_of_week'),
        CheckConstraint("end_time > start_time", name='check_end_after_start'),
        CheckConstraint("slot_duration_minutes > 0", name='check_slot_duration_positive'),
        CheckConstraint("buffer_minutes >= 0", name='check_buffer_positive'),
        CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name='check_valid_date_range'),
        Index('idx_availability_user_day', 'user_id', 'day_of_week'),
        Index('idx_availability_active', 'user_id', 'is_active'),
    )
    
    @property
    def day_name(self) -> str:
        """Get day name from day_of_week"""
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[self.day_of_week]
    
    @property
    def total_duration_minutes(self) -> int:
        """Calculate total duration of availability slot"""
        start_datetime = datetime.combine(datetime.today(), self.start_time)
        end_datetime = datetime.combine(datetime.today(), self.end_time)
        return int((end_datetime - start_datetime).total_seconds() / 60)
    
    @property
    def number_of_slots(self) -> int:
        """Calculate number of bookable slots within this availability"""
        effective_slot_duration = self.slot_duration_minutes + self.buffer_minutes
        return self.total_duration_minutes // effective_slot_duration
    
    def is_valid_on_date(self, date: Date) -> bool:
        """Check if slot is valid on a specific date"""
        if not self.is_active:
            return False
        
        # Check day of week matches
        if date.weekday() != self.day_of_week:
            return False
        
        # Check date range
        if self.valid_from and date < self.valid_from:
            return False
        if self.valid_until and date > self.valid_until:
            return False
        
        return True
    
    def get_slots_for_date(self, date: Date) -> list:
        """Generate available time slots for a specific date"""
        if not self.is_valid_on_date(date):
            return []
        
        slots = []
        current_time = datetime.combine(date, self.start_time)
        end_datetime = datetime.combine(date, self.end_time)
        
        while current_time + timedelta(minutes=self.slot_duration_minutes) <= end_datetime:
            slot_end = current_time + timedelta(minutes=self.slot_duration_minutes)
            slots.append({
                "start": current_time,
                "end": slot_end,
                "duration_minutes": self.slot_duration_minutes
            })
            current_time = slot_end + timedelta(minutes=self.buffer_minutes)
        
        return slots
    
    def overlaps_with(self, other_slot: 'AvailabilitySlot') -> bool:
        """Check if this slot overlaps with another slot on the same day"""
        if self.day_of_week != other_slot.day_of_week:
            return False
        
        # Check time overlap
        return not (self.end_time <= other_slot.start_time or 
                   other_slot.end_time <= self.start_time)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "day_of_week": self.day_of_week,
            "day_name": self.day_name,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "timezone": self.timezone,
            "slot_duration_minutes": self.slot_duration_minutes,
            "buffer_minutes": self.buffer_minutes,
            "total_duration_minutes": self.total_duration_minutes,
            "number_of_slots": self.number_of_slots,
            "is_active": self.is_active,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<AvailabilitySlot {self.day_name} {self.start_time}-{self.end_time}>"
