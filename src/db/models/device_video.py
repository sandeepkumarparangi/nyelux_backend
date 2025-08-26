from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, DECIMAL,
    Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from src.db.base_class import Base

class DeviceVideo(Base):
    """
    Training and promotional videos for devices.
    Supports streaming, transcripts, and progress tracking.
    """
    __tablename__ = "device_videos"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Device and organization
    device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    
    # Video metadata
    video_type = Column(String(50), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=False)
    
    # URLs
    thumbnail_url = Column(Text, nullable=True)
    video_url = Column(Text, nullable=False)
    hls_playlist_url = Column(Text, nullable=True)  # For adaptive streaming
    transcript_url = Column(Text, nullable=True)
    captions_url = Column(Text, nullable=True)
    
    # Video details
    language_code = Column(String(10), default='en', nullable=False)
    instructor_name = Column(String(255), nullable=True)
    skill_level = Column(String(20), nullable=True)  # beginner, intermediate, advanced
    ceu_credits = Column(DECIMAL(3, 1), nullable=True)  # Continuing Education Units
    
    # Categorization
    tags = Column(ARRAY(Text), nullable=True)
    
    # Engagement metrics
    view_count = Column(Integer, default=0, nullable=False)
    average_watch_percentage = Column(DECIMAL(5, 2), nullable=True)  # 0.00 to 100.00
    likes = Column(Integer, default=0, nullable=False)
    dislikes = Column(Integer, default=0, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    device = relationship("VendorDevice", back_populates="videos")
    organization = relationship("Organization", back_populates="device_videos")
    created_by_user = relationship("User", foreign_keys=[created_by], back_populates="created_videos")
    viewer_progress = relationship("VideoProgress", back_populates="video", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "video_type IN ('training', 'demo', 'troubleshooting', 'marketing', 'webinar')", 
            name='check_video_type'
        ),
        CheckConstraint("skill_level IN ('beginner', 'intermediate', 'advanced')", name='check_skill_level'),
        CheckConstraint("duration_seconds > 0", name='check_duration_positive'),
        CheckConstraint("view_count >= 0", name='check_view_count_positive'),
        CheckConstraint("likes >= 0", name='check_likes_positive'),
        CheckConstraint("dislikes >= 0", name='check_dislikes_positive'),
        CheckConstraint("average_watch_percentage >= 0 AND average_watch_percentage <= 100", name='check_watch_percentage'),
        CheckConstraint("ceu_credits >= 0", name='check_ceu_positive'),
        Index('idx_device_active', 'device_id', 'is_active'),
        Index('idx_video_type', 'video_type'),
        Index('idx_published_at', 'published_at'),
    )
    
    @property
    def duration_formatted(self) -> str:
        """Format duration as HH:MM:SS or MM:SS"""
        if not self.duration_seconds:
            return "00:00"
        
        hours = self.duration_seconds // 3600
        minutes = (self.duration_seconds % 3600) // 60
        seconds = self.duration_seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def engagement_score(self) -> float:
        """Calculate engagement score based on metrics"""
        if self.view_count == 0:
            return 0.0
        
        # Factors: watch percentage, like ratio
        watch_score = float(self.average_watch_percentage or 0) / 100
        
        total_votes = self.likes + self.dislikes
        if total_votes > 0:
            like_ratio = self.likes / total_votes
        else:
            like_ratio = 0.5  # Neutral if no votes
        
        # Weighted average
        score = (watch_score * 0.7) + (like_ratio * 0.3)
        return round(score * 100, 1)
    
    @property
    def is_popular(self) -> bool:
        """Check if video is popular"""
        return (
            self.view_count > 100 and
            self.average_watch_percentage and
            self.average_watch_percentage > 70 and
            self.likes > self.dislikes
        )
    
    def increment_view_count(self):
        """Increment view counter"""
        self.view_count += 1
    
    def update_watch_percentage(self, user_percentage: float):
        """Update average watch percentage with new data"""
        if self.average_watch_percentage is None:
            self.average_watch_percentage = user_percentage
        else:
            # Simple moving average
            current_total = float(self.average_watch_percentage) * (self.view_count - 1)
            new_average = (current_total + user_percentage) / self.view_count
            self.average_watch_percentage = round(new_average, 2)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "device_id": self.device_id,
            "video_type": self.video_type,
            "title": self.title,
            "description": self.description,
            "duration_seconds": self.duration_seconds,
            "duration_formatted": self.duration_formatted,
            "thumbnail_url": self.thumbnail_url,
            "video_url": self.video_url,
            "hls_playlist_url": self.hls_playlist_url,
            "has_transcript": bool(self.transcript_url),
            "has_captions": bool(self.captions_url),
            "language_code": self.language_code,
            "instructor_name": self.instructor_name,
            "skill_level": self.skill_level,
            "ceu_credits": float(self.ceu_credits) if self.ceu_credits else None,
            "tags": self.tags or [],
            "view_count": self.view_count,
            "average_watch_percentage": float(self.average_watch_percentage) if self.average_watch_percentage else None,
            "likes": self.likes,
            "dislikes": self.dislikes,
            "engagement_score": self.engagement_score,
            "is_popular": self.is_popular,
            "is_active": self.is_active,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<DeviceVideo {self.id}: {self.title}>"
