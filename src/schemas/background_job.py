"""
Background job schemas.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from src.db.models.background_job import JobType, JobStatus


class BackgroundJobBase(BaseModel):
    """Base schema for background jobs."""
    job_type: JobType
    priority: int = Field(5, ge=1, le=10)
    payload: Optional[Dict[str, Any]] = None


class BackgroundJobCreate(BackgroundJobBase):
    """Schema for creating a background job."""
    run_at: Optional[datetime] = None
    max_attempts: int = 3


class BackgroundJobUpdate(BaseModel):
    """Schema for updating a background job."""
    priority: Optional[int] = Field(None, ge=1, le=10)
    run_at: Optional[datetime] = None
    status: Optional[JobStatus] = None


class BackgroundJobResponse(BackgroundJobBase):
    """Schema for background job responses."""
    id: int
    status: JobStatus
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    attempts: int
    max_attempts: int
    run_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Computed properties
    is_ready: bool = False
    is_retryable: bool = False
    is_finished: bool = False
    execution_time_seconds: Optional[int] = None
    wait_time_seconds: Optional[int] = None
    
    class Config:
        from_attributes = True
        
    @classmethod
    def from_orm(cls, obj):
        """Create response from ORM object with computed fields."""
        data = {
            "id": obj.id,
            "job_type": obj.job_type,
            "status": obj.status,
            "priority": obj.priority,
            "payload": obj.payload,
            "result": obj.result,
            "error_message": obj.error_message,
            "attempts": obj.attempts,
            "max_attempts": obj.max_attempts,
            "run_at": obj.run_at,
            "started_at": obj.started_at,
            "completed_at": obj.completed_at,
            "failed_at": obj.failed_at,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "is_ready": obj.is_ready,
            "is_retryable": obj.is_retryable,
            "is_finished": obj.is_finished,
            "execution_time_seconds": obj.execution_time_seconds,
            "wait_time_seconds": obj.wait_time_seconds
        }
        return cls(**data)


class BackgroundJobList(BaseModel):
    """Schema for paginated list of background jobs."""
    items: List[BackgroundJobResponse]
    total: int
    skip: int
    limit: int
    
    class Config:
        from_attributes = True


class JobMetrics(BaseModel):
    """Schema for job metrics and statistics."""
    total_jobs: int
    jobs_by_status: Dict[str, int]
    jobs_by_type: Dict[str, int]
    average_execution_time: float
    average_wait_time: float
    success_rate: float
    failure_rate: float
    
    class Config:
        from_attributes = True
