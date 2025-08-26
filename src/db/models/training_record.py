"""
Training and certification tracking models for the Nyelux platform.
Handles training completions, certifications, and CEU tracking.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Index, 
    DECIMAL, Enum, Date, UniqueConstraint, CheckConstraint, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from datetime import datetime, timedelta
import enum

from src.db.base_class import Base


class TrainingType(str, enum.Enum):
    """Training type enumeration"""
    VIDEO = "video"
    DOCUMENT = "document"
    WEBINAR = "webinar"
    IN_PERSON = "in_person"
    ONLINE_COURSE = "online_course"
    SIMULATION = "simulation"
    ASSESSMENT = "assessment"


class TrainingStatus(str, enum.Enum):
    """Training completion status"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"


class CertificationStatus(str, enum.Enum):
    """Certification status"""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING = "pending"


class TrainingRecord(Base):
    """
    Records of user training completions and progress.
    """
    __tablename__ = "training_records"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User and organization
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Training source
    training_type = Column(Enum(TrainingType), nullable=False)
    training_source_id = Column(String(100), nullable=False)  # ID of video, document, course, etc.
    training_source_type = Column(String(50), nullable=False)  # device_video, device_document, external
    
    # Training details
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True)
    vendor_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    
    # Progress tracking
    status = Column(Enum(TrainingStatus), nullable=False, default=TrainingStatus.NOT_STARTED)
    progress_percentage = Column(Float, nullable=False, default=0.0)
    time_spent_seconds = Column(Integer, nullable=False, default=0)
    
    # Dates
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Assessment/Quiz results
    assessment_score = Column(Float, nullable=True)
    assessment_passed = Column(Boolean, nullable=True)
    assessment_attempts = Column(Integer, nullable=False, default=0)
    max_assessment_attempts = Column(Integer, nullable=True)
    
    # CEU/Credits
    ceu_credits = Column(DECIMAL(4, 2), nullable=True)
    ceu_category = Column(String(100), nullable=True)
    
    # Certificate information
    certificate_issued = Column(Boolean, nullable=False, default=False)
    certificate_number = Column(String(100), nullable=True, unique=True)
    certificate_url = Column(Text, nullable=True)
    certificate_issued_at = Column(DateTime(timezone=True), nullable=True)
    
    # Requirements
    required = Column(Boolean, nullable=False, default=False)
    required_by_date = Column(Date, nullable=True)
    requirement_source = Column(String(100), nullable=True)  # regulatory, organization, department
    
    # Additional data
    training_metadata = Column(JSONB, nullable=False, default=lambda: {})
    completion_data = Column(JSONB, nullable=False, default=lambda: {})  # Quiz answers, etc.
    
    # Relationships
    user = relationship("User", back_populates="training_records")
    organization = relationship("Organization", foreign_keys=[organization_id])
    device = relationship("VendorDevice", back_populates="training_records")
    vendor = relationship("Organization", foreign_keys=[vendor_id])
    
    # Indexes
    __table_args__ = (
        Index('idx_training_user_status', 'user_id', 'status'),
        Index('idx_training_org_required', 'organization_id', 'required'),
        Index('idx_training_device', 'device_id'),
        Index('idx_training_expires', 'expires_at'),
        Index('idx_training_source', 'training_source_type', 'training_source_id'),
        UniqueConstraint('user_id', 'training_source_type', 'training_source_id', 
                         name='uq_user_training_source'),
        CheckConstraint('progress_percentage >= 0 AND progress_percentage <= 100', 
                       name='check_training_progress_range'),
        CheckConstraint('assessment_score IS NULL OR (assessment_score >= 0 AND assessment_score <= 100)', 
                       name='check_training_score_range'),
    )
    
    @property
    def is_expired(self) -> bool:
        """Check if training has expired"""
        if self.expires_at and self.expires_at < datetime.utcnow():
            return True
        return False
    
    @property
    def is_overdue(self) -> bool:
        """Check if required training is overdue"""
        if self.required and self.required_by_date and self.status != TrainingStatus.COMPLETED:
            return self.required_by_date < datetime.utcnow().date()
        return False
    
    @property
    def days_until_expiry(self) -> int:
        """Calculate days until training expires"""
        if self.expires_at:
            delta = self.expires_at - datetime.utcnow()
            return delta.days
        return None
    
    def mark_completed(self, score: float = None):
        """Mark training as completed"""
        self.status = TrainingStatus.COMPLETED
        self.progress_percentage = 100.0
        self.completed_at = datetime.utcnow()
        
        if score is not None:
            self.assessment_score = score
            self.assessment_passed = score >= 70.0  # Default passing score
    
    def issue_certificate(self, certificate_number: str, certificate_url: str):
        """Issue a certificate for completed training"""
        if self.status != TrainingStatus.COMPLETED:
            raise ValueError("Cannot issue certificate for incomplete training")
        
        self.certificate_issued = True
        self.certificate_number = certificate_number
        self.certificate_url = certificate_url
        self.certificate_issued_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "training_type": self.training_type.value,
            "training_source_id": self.training_source_id,
            "training_source_type": self.training_source_type,
            "title": self.title,
            "description": self.description,
            "device_id": self.device_id,
            "vendor_id": self.vendor_id,
            "status": self.status.value,
            "progress_percentage": self.progress_percentage,
            "time_spent_seconds": self.time_spent_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired,
            "days_until_expiry": self.days_until_expiry,
            "assessment_score": self.assessment_score,
            "assessment_passed": self.assessment_passed,
            "ceu_credits": float(self.ceu_credits) if self.ceu_credits else None,
            "certificate_issued": self.certificate_issued,
            "certificate_number": self.certificate_number,
            "certificate_url": self.certificate_url,
            "required": self.required,
            "required_by_date": self.required_by_date.isoformat() if self.required_by_date else None,
            "is_overdue": self.is_overdue,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<TrainingRecord {self.title} - User {self.user_id} - {self.status.value}>"


# UserCertification is now imported from user_certification.py to avoid duplication
