from sqlalchemy import (
    Column, Integer, Boolean, ForeignKey, ARRAY, String, Index, CheckConstraint, DateTime
)
from sqlalchemy.orm import relationship
from datetime import datetime

from src.db.base_class import Base


class AgentAvailability(Base):
    """
    Track vendor support agent availability and capacity for live support.
    """
    __tablename__ = "agent_availability"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Agent and organization
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Availability status
    available = Column(Boolean, nullable=False, default=False)
    available_channels = Column(ARRAY(String), nullable=False, default=list)
    
    # Capacity management
    current_capacity = Column(Integer, nullable=False, default=0)
    max_capacity = Column(Integer, nullable=False, default=5)
    
    # Agent capabilities
    skills = Column(ARRAY(String), nullable=True, comment="Product knowledge areas")
    languages = Column(ARRAY(String), nullable=False, default=['en'])
    
    # Status tracking
    last_status_change = Column(DateTime(timezone=True), nullable=False, server_default='now()')
    
    # Relationships
    agent = relationship("User", back_populates="agent_availability")
    organization = relationship("Organization")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("current_capacity >= 0", name='check_current_capacity_positive'),
        CheckConstraint("max_capacity > 0", name='check_max_capacity_positive'),
        CheckConstraint("current_capacity <= max_capacity", name='check_capacity_limit'),
        Index('idx_available_org', 'available', 'organization_id'),
        Index('idx_agent_available', 'agent_id', 'available'),
    )
    
    @property
    def is_available(self) -> bool:
        """Check if agent can accept new conversations"""
        return self.available and self.current_capacity < self.max_capacity
    
    @property
    def available_slots(self) -> int:
        """Get number of available conversation slots"""
        return max(0, self.max_capacity - self.current_capacity)
    
    @property
    def utilization_percentage(self) -> float:
        """Calculate current utilization percentage"""
        if self.max_capacity == 0:
            return 0.0
        return (self.current_capacity / self.max_capacity) * 100
    
    def can_handle_channel(self, channel: str) -> bool:
        """Check if agent can handle specific channel"""
        return channel in self.available_channels
    
    def can_handle_language(self, language: str) -> bool:
        """Check if agent can handle specific language"""
        return language in self.languages
    
    def can_handle_skill(self, skill: str) -> bool:
        """Check if agent has specific skill"""
        return self.skills and skill in self.skills
    
    def increment_capacity(self) -> bool:
        """Increment current capacity if possible"""
        if self.current_capacity < self.max_capacity:
            self.current_capacity += 1
            return True
        return False
    
    def decrement_capacity(self) -> bool:
        """Decrement current capacity"""
        if self.current_capacity > 0:
            self.current_capacity -= 1
            return True
        return False
    
    def set_available(self, available: bool = True):
        """Set availability status"""
        self.available = available
        self.last_status_change = datetime.utcnow()
        if not available:
            # When going offline, reset capacity
            self.current_capacity = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent.full_name if self.agent else None,
            "organization_id": self.organization_id,
            "available": self.available,
            "is_available": self.is_available,
            "available_channels": self.available_channels,
            "current_capacity": self.current_capacity,
            "max_capacity": self.max_capacity,
            "available_slots": self.available_slots,
            "utilization_percentage": round(self.utilization_percentage, 1),
            "skills": self.skills or [],
            "languages": self.languages,
            "last_status_change": self.last_status_change.isoformat() if self.last_status_change else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<AgentAvailability {self.agent_id}: {'Available' if self.is_available else 'Unavailable'} ({self.current_capacity}/{self.max_capacity})>"
