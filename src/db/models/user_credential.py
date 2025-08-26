from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from src.db.base_class import Base


class UserCredential(Base):
    """
    User professional credentials and certifications.
    Tracks licenses, certifications, and training completions.
    """
    __tablename__ = 'user_credentials'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Credential details
    credential_type = Column(String(50), nullable=False)  # license, certification, training
    credential_name = Column(String(255), nullable=False)
    issuing_authority = Column(String(255), nullable=True)
    credential_number = Column(String(100), nullable=True, index=True)
    
    # Validity
    issue_date = Column(DateTime(timezone=True), nullable=False)
    expiry_date = Column(DateTime(timezone=True), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Verification
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verification_method = Column(String(50), nullable=True)
    
    # Documentation
    document_url = Column(Text, nullable=True)
    document_hash = Column(String(64), nullable=True)
    
    # Additional info
    specialties = Column(Text, nullable=True)  # JSON array
    notes = Column(Text, nullable=True)
    
    # Tracking
    last_checked = Column(DateTime(timezone=True), nullable=True)
    check_status = Column(String(50), nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="credentials")
    verifier = relationship("User", foreign_keys=[verified_by])
    
    @property
    def is_expired(self) -> bool:
        """Check if credential has expired"""
        if not self.expiry_date:
            return False
        from datetime import datetime
        return self.expiry_date < datetime.utcnow()
    
    @property
    def needs_renewal(self) -> bool:
        """Check if credential needs renewal (within 90 days of expiry)"""
        if not self.expiry_date:
            return False
        from datetime import datetime, timedelta
        return self.expiry_date < datetime.utcnow() + timedelta(days=90)
