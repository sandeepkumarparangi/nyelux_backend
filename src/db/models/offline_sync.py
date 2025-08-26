from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, DECIMAL, Enum, JSON
from sqlalchemy.orm import relationship
from src.db.base_class import Base
import enum


class SyncStatus(str, enum.Enum):
    """Sync status enum"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class SyncType(str, enum.Enum):
    """Sync type enum"""
    FULL = "full"
    DELTA = "delta"
    PROGRESSIVE = "progressive"


class OfflineSync(Base):
    """
    Offline sync package management. REAL implementation.
    Tracks generated sync packages for offline functionality.
    """
    __tablename__ = 'offline_syncs'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Sync details
    sync_id = Column(String(100), unique=True, nullable=False, index=True)
    sync_type = Column(Enum(SyncType), nullable=False, default=SyncType.FULL)
    status = Column(Enum(SyncStatus), nullable=False, default=SyncStatus.PENDING)
    
    # Content configuration
    sync_types = Column(JSON, nullable=False)  # ["devices", "documents", "bookmarks", etc]
    device_limit = Column(Integer, nullable=True)
    include_documents = Column(Boolean, default=True, nullable=False)
    include_attachments = Column(Boolean, default=False, nullable=False)
    max_package_size_mb = Column(Integer, nullable=True)
    
    # Package details
    package_url = Column(Text, nullable=True)
    package_size_bytes = Column(Integer, nullable=True)
    package_hash = Column(String(64), nullable=True)
    compression_ratio = Column(DECIMAL(3, 2), nullable=True)
    
    # Sync token for delta sync
    sync_token = Column(String(255), nullable=True)
    previous_sync_id = Column(String(100), nullable=True)
    
    # Encryption
    encrypted = Column(Boolean, default=False, nullable=False)
    encryption_algorithm = Column(String(50), nullable=True)
    key_derivation_salt = Column(String(255), nullable=True)
    
    # Metrics
    items_included = Column(JSON, nullable=True)  # {"devices": 100, "documents": 50}
    items_excluded = Column(JSON, nullable=True)  # Items excluded due to size limits
    generation_time_seconds = Column(Integer, nullable=True)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=True)
    requires_refresh_at = Column(DateTime(timezone=True), nullable=True)
    
    # Status tracking
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User")
    organization = relationship("Organization")
    queue_items = relationship("OfflineSyncQueue", back_populates="sync", cascade="all, delete-orphan")


class OfflineSyncQueue(Base):
    """
    Queue for offline changes waiting to be synced.
    Tracks changes made while offline.
    """
    __tablename__ = 'offline_sync_queue'
    
    id = Column(Integer, primary_key=True, index=True)
    sync_id = Column(Integer, ForeignKey("offline_syncs.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Change details
    action = Column(String(20), nullable=False)  # create, update, delete
    resource_type = Column(String(50), nullable=False)  # note, bookmark, incident, etc
    resource_id = Column(String(255), nullable=True)  # NULL for creates
    client_id = Column(String(255), nullable=True)  # Client-generated ID for creates
    
    # Change data
    data = Column(JSON, nullable=False)  # The actual change data
    client_timestamp = Column(DateTime(timezone=True), nullable=False)
    base_version = Column(Integer, nullable=True)  # For conflict detection
    
    # Processing status
    processed = Column(Boolean, default=False, nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    success = Column(Boolean, nullable=True)
    server_id = Column(String(255), nullable=True)  # Server ID after create
    error_message = Column(Text, nullable=True)
    conflict_detected = Column(Boolean, default=False, nullable=False)
    
    # Retry tracking
    retry_count = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    sync = relationship("OfflineSync", back_populates="queue_items")
    user = relationship("User")
    organization = relationship("Organization")
    
    # Indexes are defined in migration files
