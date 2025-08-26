"""
Device Comparison Model - Save device comparison sessions
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, DateTime, JSON, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.db.base_class import Base


class DeviceComparison(Base):
    """
    Save device comparison sessions for easy access and sharing.
    """
    __tablename__ = "device_comparisons"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255))
    device_ids = Column(ARRAY(Integer), nullable=False)  # Array of vendor_device IDs
    comparison_data = Column(JSON)  # Cached comparison data
    is_public = Column(Boolean, default=False, nullable=False)
    share_token = Column(String(100), unique=True, index=True)
    view_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    
    def __repr__(self):
        return f"<DeviceComparison({self.name}, devices={len(self.device_ids)})>"
