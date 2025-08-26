from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, DECIMAL,
    UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from src.db.base_class import Base

class VendorDevice(Base):
    """
    Vendor-specific device information.
    Links to FDA GUDID data and adds vendor-specific details.
    """
    __tablename__ = "vendor_devices"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Link to FDA GUDID data
    gudid_device_di = Column(String(100), ForeignKey("gudid_devices.primary_di"), nullable=True)
    
    # Organization ownership
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    
    # Vendor-specific identifiers
    internal_sku = Column(String(100), nullable=True, index=True)
    custom_name = Column(String(500), nullable=True)
    
    # Pricing information
    list_price = Column(DECIMAL(10, 2), nullable=True)
    currency_code = Column(String(3), default='USD', nullable=False)
    
    # Product details
    warranty_months = Column(Integer, nullable=True)
    specifications = Column(JSONB, default=dict, nullable=True)
    features = Column(JSONB, default=dict, nullable=True)
    
    # Training and certification
    training_required = Column(Boolean, default=False, nullable=False)
    certification_required = Column(Boolean, default=False, nullable=False)
    
    # Access control
    access_level = Column(String(20), default='public', nullable=False)  # public, restricted, private
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    launch_date = Column(DateTime(timezone=True), nullable=True)
    discontinue_date = Column(DateTime(timezone=True), nullable=True)
    replacement_device_id = Column(Integer, ForeignKey("vendor_devices.id"), nullable=True)
    
    # Audit
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Simplified Relationships - using back_populates for organization
    gudid_device = relationship("GUDIDDevice", backref="vendor_devices")
    organization = relationship("Organization", back_populates="vendor_devices")
    replacement_device = relationship("VendorDevice", remote_side=[id])
    
    # Relationships defined in other models using back_populates
    incidents = relationship("DeviceIncident", back_populates="device", cascade="all, delete-orphan")
    support_conversations = relationship("SupportConversation", back_populates="device", cascade="all, delete-orphan")
    videos = relationship("DeviceVideo", back_populates="device", cascade="all, delete-orphan")
    chat_conversations = relationship("ChatConversation", back_populates="device", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="device", cascade="all, delete-orphan")
    training_records = relationship("TrainingRecord", back_populates="device", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('organization_id', 'gudid_device_di', name='uq_org_gudid_device'),
        UniqueConstraint('organization_id', 'internal_sku', name='uq_org_sku'),
        CheckConstraint("access_level IN ('public', 'restricted', 'private')", name='check_access_level'),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name='check_currency_code'),
        CheckConstraint("warranty_months >= 0", name='check_warranty_positive'),
        CheckConstraint("list_price >= 0", name='check_price_positive'),
        Index('idx_vendor_device_active', 'organization_id', 'is_active'),
        Index('idx_vendor_device_sku', 'internal_sku'),
    )
    
    @property
    def display_name(self) -> str:
        """Get display name (custom or FDA name)"""
        if self.custom_name:
            return self.custom_name
        if self.gudid_device:
            return self.gudid_device.device_name
        return f"Device {self.id}"
    
    @property
    def manufacturer_name(self) -> str:
        """Get manufacturer name from GUDID or organization"""
        if self.gudid_device and self.gudid_device.manufacturer_name:
            return self.gudid_device.manufacturer_name
        if self.organization:
            return self.organization.name
        return "Unknown"
    
    @property
    def is_available(self) -> bool:
        """Check if device is currently available"""
        from datetime import datetime
        now = datetime.utcnow()
        
        if not self.is_active:
            return False
        
        if self.discontinue_date and self.discontinue_date <= now:
            return False
        
        if self.launch_date and self.launch_date > now:
            return False
        
        return True
    
    @property
    def requires_authorization(self) -> bool:
        """Check if device requires special authorization"""
        if self.access_level != 'public':
            return True
        
        if self.gudid_device:
            # FDA Class III devices always require authorization
            if self.gudid_device.device_class == 'III':
                return True
            # Prescription required devices
            if self.gudid_device.rx_required:
                return True
        
        return self.certification_required
    
    def get_specifications_list(self) -> list:
        """Get specifications as a list of key-value pairs"""
        if not self.specifications:
            return []
        
        return [
            {"key": k, "value": v}
            for k, v in self.specifications.items()
        ]
    
    def get_features_list(self) -> list:
        """Get features as a list"""
        if not self.features:
            return []
        
        if isinstance(self.features, list):
            return self.features
        
        if isinstance(self.features, dict):
            return list(self.features.values())
        
        return []
    
    def can_user_access(self, user) -> bool:
        """Check if a user can access this device"""
        # Public devices are accessible to all
        if self.access_level == 'public':
            return True
        
        # Check organization membership
        if hasattr(user, 'organization_id') and user.organization_id == self.organization_id:
            return True
        
        # Super admins can access everything
        if hasattr(user, 'role') and user.role == 'super_admin':
            return True
        
        # Restricted devices require same organization or partnership
        if self.access_level == 'restricted':
            # TODO: Implement partnership logic
            return False
        
        # Private devices are organization-only
        return False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "gudid_device_di": self.gudid_device_di,
            "organization_id": self.organization_id,
            "display_name": self.display_name,
            "manufacturer_name": self.manufacturer_name,
            "internal_sku": self.internal_sku,
            "list_price": float(self.list_price) if self.list_price else None,
            "currency_code": self.currency_code,
            "warranty_months": self.warranty_months,
            "training_required": self.training_required,
            "certification_required": self.certification_required,
            "access_level": self.access_level,
            "is_active": self.is_active,
            "is_available": self.is_available,
            "requires_authorization": self.requires_authorization,
            "specifications": self.get_specifications_list(),
            "features": self.get_features_list(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f"<VendorDevice {self.id}: {self.display_name}>"
