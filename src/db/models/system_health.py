"""
System Health model for monitoring deployment and system status.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Float, Text
from sqlalchemy.sql import func

from src.db.base_class import Base


class SystemHealth(Base):
    """
    System health tracking for monitoring and deployment operations.
    Records health check results and system metrics.
    """
    __tablename__ = "system_health"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Component identification
    component = Column(String(100), nullable=False, index=True)  # database, redis, elasticsearch, etc.
    service_name = Column(String(100), nullable=True)  # Specific service instance
    environment = Column(String(50), nullable=False, default="production")  # production, staging, etc.
    
    # Health status
    status = Column(String(20), nullable=False)  # healthy, degraded, unhealthy
    is_healthy = Column(Boolean, nullable=False)
    
    # Response metrics
    response_time_ms = Column(Float, nullable=True)
    last_check_at = Column(DateTime(timezone=True), nullable=False)
    next_check_at = Column(DateTime(timezone=True), nullable=True)
    
    # Detailed health information
    details = Column(JSON, nullable=True)  # Component-specific details
    error_message = Column(Text, nullable=True)
    
    # Resource metrics (if applicable)
    cpu_usage_percent = Column(Float, nullable=True)
    memory_usage_percent = Column(Float, nullable=True)
    disk_usage_percent = Column(Float, nullable=True)
    connection_count = Column(Integer, nullable=True)
    
    # Version information
    version = Column(String(50), nullable=True)
    deployment_id = Column(String(100), nullable=True)
    
    # Alerting
    alert_triggered = Column(Boolean, default=False, nullable=False)
    alert_sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
