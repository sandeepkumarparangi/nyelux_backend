"""
User Certification Model - Track professional certifications and credentials
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, DateTime, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.db.base_class import Base


class UserCertification(Base):
    """
    Track user professional certifications for compliance
    """
    __tablename__ = "user_certifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_id = Column(Integer, ForeignKey("user_credentials.id", ondelete="SET NULL"), nullable=True)
    
    certification_name = Column(String(255), nullable=False)
    certification_type = Column(String(100), nullable=False)  # license, certification, training
    issuing_organization = Column(String(255), nullable=False)
    certification_number = Column(String(100))
    
    issue_date = Column(Date, nullable=False)
    expiration_date = Column(Date, nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime(timezone=True))
    verified_by = Column(Integer, ForeignKey("users.id"))
    
    document_url = Column(Text)  # Link to uploaded certification
    notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="certifications")
    verifier = relationship("User", foreign_keys=[verified_by])
    
    @property
    def is_expired(self) -> bool:
        """Check if certification is expired"""
        if self.expiration_date:
            from datetime import date
            return self.expiration_date < date.today()
        return False
    
    @property
    def days_until_expiration(self) -> int:
        """Get days until expiration"""
        if self.expiration_date:
            from datetime import date
            return (self.expiration_date - date.today()).days
        return -1
