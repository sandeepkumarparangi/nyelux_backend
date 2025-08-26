from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, ForeignKey, 
    Text, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, INET

from src.db.base_class import Base


class AuditLog(Base):
    """
    HIPAA-compliant audit trail for all system actions.
    Tracks who did what, when, and from where.
    """
    __tablename__ = "audit_logs"
    
    # Primary key - BigInteger for high volume
    id = Column(BigInteger, primary_key=True, index=True)
    
    # User and organization
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    
    # Action details
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(String(255), nullable=False)
    resource_name = Column(Text, nullable=True, comment="Human-readable resource identifier")
    
    # Change tracking
    changes = Column(JSONB, nullable=True, comment="Before/after values for updates")
    
    # Request context
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    session_id = Column(String(100), nullable=True)
    
    # Result
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamp (no auto-update needed for audit logs)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default='now()')
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    organization = relationship("Organization")
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "action IN ('view', 'create', 'update', 'delete', 'download', 'share', 'print', 'export', 'login', 'logout', 'access_denied')",
            name='check_audit_action'
        ),
        Index('idx_audit_user_created', 'user_id', 'created_at'),
        Index('idx_audit_resource', 'resource_type', 'resource_id', 'created_at'),
        Index('idx_audit_action_created', 'action', 'created_at'),
        Index('idx_audit_org_created', 'organization_id', 'created_at'),
        Index('idx_audit_session', 'session_id'),
    )
    
    @property
    def is_sensitive_action(self) -> bool:
        """Check if this is a sensitive action requiring extra scrutiny"""
        sensitive_actions = ['delete', 'export', 'download', 'share', 'print']
        sensitive_resources = ['user', 'patient_data', 'phi', 'financial']
        
        return (self.action in sensitive_actions or 
                self.resource_type in sensitive_resources)
    
    @property
    def is_failed_action(self) -> bool:
        """Check if action failed"""
        return not self.success or self.action == 'access_denied'
    
    @property
    def is_authentication_event(self) -> bool:
        """Check if this is an auth-related event"""
        return self.action in ['login', 'logout', 'access_denied']
    
    @property
    def change_summary(self) -> dict:
        """Get summary of changes made"""
        if not self.changes or self.action != 'update':
            return {}
        
        summary = {
            'fields_changed': [],
            'before': {},
            'after': {}
        }
        
        if 'before' in self.changes and 'after' in self.changes:
            before = self.changes['before']
            after = self.changes['after']
            
            for key in after:
                if key in before and before[key] != after[key]:
                    summary['fields_changed'].append(key)
                    summary['before'][key] = before[key]
                    summary['after'][key] = after[key]
        
        return summary
    
    @classmethod
    def log_action(
        cls,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: int = None,
        organization_id: int = None,
        resource_name: str = None,
        changes: dict = None,
        ip_address: str = None,
        user_agent: str = None,
        session_id: str = None,
        success: bool = True,
        error_message: str = None
    ) -> 'AuditLog':
        """Create an audit log entry"""
        return cls(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            user_id=user_id,
            organization_id=organization_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            success=success,
            error_message=error_message
        )
    
    def to_dict(self, include_changes: bool = True) -> dict:
        """Convert to dictionary for API responses"""
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.full_name if self.user else None,
            "organization_id": self.organization_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "ip_address": str(self.ip_address) if self.ip_address else None,
            "session_id": self.session_id,
            "success": self.success,
            "error_message": self.error_message,
            "is_sensitive": self.is_sensitive_action,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_changes and self.changes:
            result["changes"] = self.change_summary
        
        return result
    
    def to_compliance_format(self) -> dict:
        """Format for compliance reporting"""
        return {
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "user": {
                "id": self.user_id,
                "name": self.user.full_name if self.user else "System",
                "email": self.user.email if self.user else None,
            },
            "action": {
                "type": self.action,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
                "resource_name": self.resource_name,
                "success": self.success,
                "error": self.error_message,
            },
            "context": {
                "ip_address": str(self.ip_address) if self.ip_address else None,
                "user_agent": self.user_agent,
                "session_id": self.session_id,
                "organization_id": self.organization_id,
            },
            "changes": self.changes if self.changes else None,
        }
    
    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action} on {self.resource_type}/{self.resource_id}>"
