from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Index, CheckConstraint, Enum
)
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timedelta
import enum

from src.db.base_class import Base


class JobType(str, enum.Enum):
    """Background job types"""
    GUDID_SYNC = "gudid_sync"
    DOCUMENT_PROCESS = "document_process"
    VIDEO_TRANSCODE = "video_transcode"
    EMAIL_SEND = "email_send"
    REPORT_GENERATE = "report_generate"
    DATA_EXPORT = "data_export"
    ANALYTICS_AGGREGATE = "analytics_aggregate"
    CLEANUP_OLD_DATA = "cleanup_old_data"


class JobStatus(str, enum.Enum):
    """Background job statuses"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundJob(Base):
    """
    Async job processing queue for background tasks.
    Used for GUDID sync, document processing, video transcoding, etc.
    """
    __tablename__ = "background_jobs"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Job details
    job_type = Column(Enum(JobType), nullable=False)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    priority = Column(Integer, nullable=False, default=5, comment="1 (highest) to 10 (lowest)")
    
    # Job data
    payload = Column(JSONB, nullable=True, comment="Job parameters")
    result = Column(JSONB, nullable=True, comment="Job results")
    
    # Error handling
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    
    # Scheduling
    run_at = Column(DateTime(timezone=True), nullable=False, default='now()')
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    
    # No relationships needed - jobs are independent
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("priority >= 1 AND priority <= 10", name='check_priority_range'),
        CheckConstraint("attempts >= 0", name='check_attempts_positive'),
        CheckConstraint("max_attempts > 0", name='check_max_attempts_positive'),
        Index('idx_job_status_run_at', 'status', 'run_at'),
        Index('idx_job_type_status', 'job_type', 'status'),
        Index('idx_job_priority_run_at', 'priority', 'run_at'),
    )
    
    @property
    def is_ready(self) -> bool:
        """Check if job is ready to run"""
        return (self.status == JobStatus.PENDING and 
                self.run_at <= datetime.utcnow() and
                self.attempts < self.max_attempts)
    
    @property
    def is_retryable(self) -> bool:
        """Check if job can be retried"""
        return (self.status == JobStatus.FAILED and 
                self.attempts < self.max_attempts)
    
    @property
    def is_finished(self) -> bool:
        """Check if job is in a terminal state"""
        return self.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
    
    @property
    def execution_time_seconds(self) -> int:
        """Calculate job execution time"""
        if self.started_at and (self.completed_at or self.failed_at):
            end_time = self.completed_at or self.failed_at
            return int((end_time - self.started_at).total_seconds())
        return 0
    
    @property
    def wait_time_seconds(self) -> int:
        """Calculate time waited before execution"""
        if self.started_at:
            return int((self.started_at - self.created_at).total_seconds())
        return 0
    
    def start(self):
        """Mark job as started"""
        self.status = JobStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.attempts += 1
    
    def complete(self, result: dict = None):
        """Mark job as completed"""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if result:
            self.result = result
    
    def fail(self, error_message: str):
        """Mark job as failed"""
        self.status = JobStatus.FAILED
        self.failed_at = datetime.utcnow()
        self.error_message = error_message
        
        # Schedule retry if applicable
        if self.is_retryable:
            # Exponential backoff: 1min, 2min, 4min...
            retry_delay = 2 ** (self.attempts - 1)
            self.run_at = datetime.utcnow() + timedelta(minutes=retry_delay)
            self.status = JobStatus.PENDING
    
    def cancel(self):
        """Cancel the job"""
        if not self.is_finished:
            self.status = JobStatus.CANCELLED
            self.completed_at = datetime.utcnow()
    
    def reschedule(self, run_at: datetime = None, priority: int = None):
        """Reschedule the job"""
        if run_at:
            self.run_at = run_at
        if priority:
            self.priority = priority
        if self.status == JobStatus.FAILED:
            self.status = JobStatus.PENDING
    
    @classmethod
    def create_job(
        cls,
        job_type: JobType,
        payload: dict = None,
        priority: int = 5,
        run_at: datetime = None,
        max_attempts: int = 3
    ) -> 'BackgroundJob':
        """Create a new background job"""
        return cls(
            job_type=job_type,
            payload=payload or {},
            priority=priority,
            run_at=run_at or datetime.utcnow(),
            max_attempts=max_attempts
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "priority": self.priority,
            "payload": self.payload,
            "result": self.result,
            "error_message": self.error_message,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "is_ready": self.is_ready,
            "is_retryable": self.is_retryable,
            "is_finished": self.is_finished,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "execution_time_seconds": self.execution_time_seconds,
            "wait_time_seconds": self.wait_time_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<BackgroundJob {self.id}: {self.job_type} - {self.status}>"
