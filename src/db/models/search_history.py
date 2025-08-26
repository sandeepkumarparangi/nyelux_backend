from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, ARRAY, Index, Boolean, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, INET

from src.db.base_class import Base


class SearchHistory(Base):
    """
    Track user searches for analytics and personalized suggestions.
    """
    __tablename__ = "search_history"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User and organization
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    
    # Search details
    search_query = Column(Text, nullable=False)
    search_type = Column(String(50), nullable=True, comment="device, document, video, etc.")
    filters_applied = Column(JSONB, nullable=True, comment="Applied search filters")
    
    # Results information
    results_count = Column(Integer, nullable=False, default=0)
    clicked_result_ids = Column(ARRAY(Integer), nullable=True, comment="IDs of clicked results")
    
    # Performance metrics
    search_duration_ms = Column(Integer, nullable=True, comment="Search execution time")
    
    # Session information
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    session_id = Column(String(100), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="search_history")
    organization = relationship("Organization")
    
    # Indexes
    __table_args__ = (
        Index('idx_search_user_created', 'user_id', 'created_at'),
        Index('idx_search_query_pattern', 'search_query'),
        Index('idx_search_type_created', 'search_type', 'created_at'),
        Index('idx_search_session', 'session_id', 'created_at'),
    )
    
    @property
    def was_successful(self) -> bool:
        """Check if search returned results"""
        return self.results_count > 0
    
    @property
    def click_through_rate(self) -> float:
        """Calculate click-through rate"""
        if self.results_count == 0:
            return 0.0
        clicked_count = len(self.clicked_result_ids) if self.clicked_result_ids else 0
        return (clicked_count / self.results_count) * 100
    
    @property
    def query_terms(self) -> list:
        """Extract individual terms from search query"""
        if not self.search_query:
            return []
        # Simple tokenization - can be enhanced with NLP
        return self.search_query.lower().split()
    
    def add_clicked_result(self, result_id: int):
        """Add a clicked result ID"""
        if self.clicked_result_ids is None:
            self.clicked_result_ids = []
        if result_id not in self.clicked_result_ids:
            self.clicked_result_ids.append(result_id)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "search_query": self.search_query,
            "search_type": self.search_type,
            "filters_applied": self.filters_applied or {},
            "results_count": self.results_count,
            "clicked_results_count": len(self.clicked_result_ids) if self.clicked_result_ids else 0,
            "click_through_rate": round(self.click_through_rate, 1),
            "search_duration_ms": self.search_duration_ms,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<SearchHistory {self.id}: '{self.search_query[:50]}...'>"


class SavedSearch(Base):
    """
    User-saved search queries with optional alerts.
    """
    __tablename__ = "saved_searches"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User association
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Search configuration
    name = Column(String(255), nullable=False)
    search_query = Column(Text, nullable=False)
    filters = Column(JSONB, nullable=True)
    
    # Alert settings
    alert_enabled = Column(Boolean, nullable=False, default=False)
    alert_frequency = Column(String(20), nullable=True, comment="daily, weekly, immediate")
    last_alerted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="saved_searches")
    
    # Indexes
    __table_args__ = (
        Index('idx_saved_search_user', 'user_id', 'created_at'),
        Index('idx_saved_search_alerts', 'alert_enabled', 'alert_frequency'),
    )
    
    @property
    def is_alert_due(self) -> bool:
        """Check if alert should be sent"""
        if not self.alert_enabled:
            return False
        
        from datetime import datetime, timedelta
        
        if not self.last_alerted_at:
            return True
        
        last_alert = datetime.fromisoformat(self.last_alerted_at)
        now = datetime.utcnow()
        
        if self.alert_frequency == 'daily':
            return (now - last_alert) >= timedelta(days=1)
        elif self.alert_frequency == 'weekly':
            return (now - last_alert) >= timedelta(weeks=1)
        elif self.alert_frequency == 'immediate':
            return True  # Always check for new results
        
        return False
    
    def mark_alerted(self):
        """Mark that alert was sent"""
        from datetime import datetime
        self.last_alerted_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "search_query": self.search_query,
            "filters": self.filters or {},
            "alert_enabled": self.alert_enabled,
            "alert_frequency": self.alert_frequency,
            "last_alerted_at": self.last_alerted_at.isoformat() if self.last_alerted_at else None,
            "is_alert_due": self.is_alert_due,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<SavedSearch {self.id}: {self.name}>"
