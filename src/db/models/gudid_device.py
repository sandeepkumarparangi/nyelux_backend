from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, DECIMAL,
    Index, CheckConstraint, func
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from src.db.base_class import Base

class GUDIDDevice(Base):
    """
    FDA GUDID medical device data.
    This is READ-ONLY data synchronized from FDA.
    Contains 4.8M+ medical device records.
    """
    __tablename__ = "gudid_devices"
    
    # Primary identifier from FDA
    primary_di = Column(String(100), primary_key=True, comment="FDA Device Identifier")
    
    # Device identification
    device_name = Column(Text, nullable=False, index=True, comment="Commercial name")
    manufacturer_name = Column(String(500), nullable=True, index=True)
    manufacturer_di = Column(String(100), nullable=True)
    brand_name = Column(String(500), nullable=True, index=True)
    model_number = Column(String(500), nullable=True, index=True)
    catalog_number = Column(String(100), nullable=True)
    
    # Regulatory classification
    device_class = Column(String(3), nullable=True, index=True, comment="FDA Class: I, II, III")
    device_class_name = Column(String(100), nullable=True)
    product_code = Column(String(10), nullable=True, index=True)
    regulation_number = Column(String(50), nullable=True)
    
    # Medical device nomenclature
    gmdn_terms = Column(Text, nullable=True, comment="Global Medical Device Nomenclature terms")
    gmdn_codes = Column(String(500), nullable=True)
    
    # Device characteristics
    device_description = Column(Text, nullable=True)
    device_size_text = Column(Text, nullable=True)
    
    # Safety information
    mri_safety = Column(String(100), nullable=True, index=True)
    sterile = Column(Boolean, nullable=True, index=True)
    single_use = Column(Boolean, nullable=True)
    implantable = Column(Boolean, nullable=True, index=True)
    life_supporting = Column(Boolean, nullable=True, index=True)
    
    # Usage requirements
    rx_required = Column(Boolean, nullable=True, comment="Prescription required")
    otc = Column(Boolean, nullable=True, comment="Over the counter")
    
    # Search optimization
    search_vector = Column(TSVECTOR, nullable=True, comment="Full-text search vector")
    
    # Raw FDA data
    raw_json = Column(JSONB, nullable=True, comment="Original FDA JSON data")
    
    # Sync metadata
    sync_timestamp = Column(DateTime(timezone=True), nullable=True)
    gudid_version = Column(Integer, nullable=True)
    
    # Note: created_at and updated_at are inherited from Base with proper defaults
    
    # NOTE: Relationships to this model are defined in other models using backref
    # to avoid circular imports. VendorDevice.gudid_device uses backref="vendor_devices"
    
    # Indexes for performance
    __table_args__ = (
        # Full-text search index
        Index('idx_gudid_search_vector', 'search_vector', postgresql_using='gin'),
        
        # Composite indexes for common queries
        Index('idx_gudid_manufacturer_model', 'manufacturer_name', 'model_number'),
        Index('idx_gudid_class_mri', 'device_class', 'mri_safety'),
        
        # Partial indexes for boolean fields
        Index('idx_gudid_implantable', 'implantable', postgresql_where='implantable = true'),
        Index('idx_gudid_life_supporting', 'life_supporting', postgresql_where='life_supporting = true'),
        
        # Constraints
        CheckConstraint("device_class IN ('I', 'II', 'III')", name='check_device_class'),
        CheckConstraint("mri_safety IN ('MR Safe', 'MR Conditional', 'MR Unsafe', 'Not Evaluated')", 
                       name='check_mri_safety'),
    )
    
    @property
    def is_high_risk(self) -> bool:
        """Check if device is high risk (Class III or life supporting)"""
        return self.device_class == 'III' or self.life_supporting == True
    
    @property
    def requires_special_handling(self) -> bool:
        """Check if device requires special handling"""
        return any([
            self.implantable,
            self.life_supporting,
            self.sterile,
            self.device_class == 'III'
        ])
    
    def get_safety_warnings(self) -> list:
        """Get list of safety warnings for the device"""
        warnings = []
        
        if self.life_supporting:
            warnings.append("Life Supporting Device - Critical for patient survival")
        
        if self.implantable:
            warnings.append("Implantable Device - Requires surgical procedure")
        
        if self.mri_safety == 'MR Unsafe':
            warnings.append("MRI Unsafe - Do not use in MRI environment")
        elif self.mri_safety == 'MR Conditional':
            warnings.append("MRI Conditional - Check specific conditions before MRI")
        
        if self.single_use:
            warnings.append("Single Use Only - Do not reuse")
        
        if self.sterile:
            warnings.append("Sterile Device - Maintain sterility until use")
        
        return warnings
    
    def to_search_result(self) -> dict:
        """Convert to search result format"""
        return {
            "primary_di": self.primary_di,
            "device_name": self.device_name,
            "manufacturer_name": self.manufacturer_name,
            "brand_name": self.brand_name,
            "model_number": self.model_number,
            "device_class": self.device_class,
            "mri_safety": self.mri_safety,
            "is_high_risk": self.is_high_risk,
            "safety_warnings": self.get_safety_warnings()
        }
    
    def __repr__(self):
        return f"<GUDIDDevice {self.primary_di}: {self.device_name}>"
