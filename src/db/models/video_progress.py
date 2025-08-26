from sqlalchemy import (
    Column, Integer, Boolean, DateTime, ForeignKey, DECIMAL, Text,
    UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime

from src.db.base_class import Base


class VideoProgress(Base):
    """
    Track user video viewing progress and completion status.
    """
    __tablename__ = "video_progress"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User and video association
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("device_videos.id"), nullable=False)
    
    # Progress tracking
    watch_percentage = Column(DECIMAL(5, 2), nullable=False, default=0.0, comment="0.00 to 100.00")
    last_position_seconds = Column(Integer, nullable=False, default=0)
    completed = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Learning metrics
    quiz_score = Column(DECIMAL(5, 2), nullable=True, comment="Quiz score percentage if applicable")
    certificate_issued = Column(Boolean, nullable=False, default=False)
    certificate_url = Column(Text, nullable=True)
    
    # Timing
    started_at = Column(DateTime(timezone=True), nullable=False, server_default='now()')
    
    # Relationships
    user = relationship("User", back_populates="video_progress")
    video = relationship("DeviceVideo", back_populates="viewer_progress")
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('user_id', 'video_id', name='uq_user_video_progress'),
        CheckConstraint("watch_percentage >= 0 AND watch_percentage <= 100", name='check_watch_percentage_range'),
        CheckConstraint("last_position_seconds >= 0", name='check_position_positive'),
        CheckConstraint("quiz_score >= 0 AND quiz_score <= 100", name='check_quiz_score_range'),
        Index('idx_progress_user_completed', 'user_id', 'completed'),
        Index('idx_progress_video_completed', 'video_id', 'completed'),
    )
    
    @property
    def is_completed(self) -> bool:
        """Check if video is completed"""
        return self.completed or self.watch_percentage >= 95.0
    
    @property
    def needs_certificate(self) -> bool:
        """Check if certificate should be issued"""
        return (self.is_completed and 
                not self.certificate_issued and 
                self.video and 
                self.video.ceu_credits and 
                self.video.ceu_credits > 0)
    
    @property
    def passed_quiz(self) -> bool:
        """Check if user passed the quiz (if applicable)"""
        if self.quiz_score is None:
            return True  # No quiz required
        return float(self.quiz_score) >= 70.0  # 70% passing grade
    
    @property
    def time_watched_seconds(self) -> int:
        """Calculate total time watched based on percentage and video duration"""
        if self.video and self.video.duration_seconds:
            return int((float(self.watch_percentage) / 100) * self.video.duration_seconds)
        return 0
    
    def update_progress(self, position_seconds: int, video_duration_seconds: int):
        """Update viewing progress"""
        if video_duration_seconds > 0:
            # Update position
            self.last_position_seconds = position_seconds
            
            # Calculate percentage
            new_percentage = (position_seconds / video_duration_seconds) * 100
            
            # Only update if progress moved forward
            if new_percentage > float(self.watch_percentage):
                self.watch_percentage = min(new_percentage, 100.0)
            
            # Mark as completed if reached end
            if self.watch_percentage >= 95.0 and not self.completed:
                self.mark_completed()
    
    def mark_completed(self):
        """Mark video as completed"""
        self.completed = True
        self.completed_at = datetime.utcnow()
        self.watch_percentage = 100.0
    
    def record_quiz_score(self, score: float):
        """Record quiz score"""
        self.quiz_score = min(max(score, 0.0), 100.0)
        if self.passed_quiz and self.needs_certificate:
            # Trigger certificate generation
            self.certificate_issued = True
    
    def restart_video(self):
        """Reset progress to start over"""
        self.watch_percentage = 0.0
        self.last_position_seconds = 0
        self.completed = False
        self.completed_at = None
        # Keep quiz score and certificate for records
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "video_id": self.video_id,
            "video_title": self.video.title if self.video else None,
            "watch_percentage": float(self.watch_percentage),
            "last_position_seconds": self.last_position_seconds,
            "time_watched_seconds": self.time_watched_seconds,
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "quiz_score": float(self.quiz_score) if self.quiz_score else None,
            "passed_quiz": self.passed_quiz,
            "certificate_issued": self.certificate_issued,
            "certificate_url": self.certificate_url,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<VideoProgress user_{self.user_id}_video_{self.video_id}: {self.watch_percentage}%>"
