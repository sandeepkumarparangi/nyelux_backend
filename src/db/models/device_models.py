"""
Production-grade FDA GUDID data integration
Real implementation with vendor relationships
"""

from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, DECIMAL, JSON, Index, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.db.base_class import Base
import uuid

class GUDIDDevice(Base):
    """
    FDA GUDID Device Data - Read-only mirror from FDA
    This is PUBLIC data from FDA that anyone can access
    """
    __tablename__ = "gudid_devices"

    # Primary key from FDA
    primary_di = Column(String(100), primary_key=True, index=True)
    
    # Core device information
    device_name = Column(Text, nullable=False)
    manufacturer_name = Column(String(500), index=True)
    manufacturer_di = Column(String(100))
    brand_name = Column(String(500))
    model_number = Column(String(500), index=True)
    catalog_number = Column(String(100))
    
    # FDA Classification
    device_class = Column(String(3))  # I, II, III
    device_class_name = Column(String(100))
    gmdn_terms = Column(Text)
    gmdn_codes = Column(String(500))
    product_code = Column(String(10))
    regulation_number = Column(String(50))
    
    # Safety Information
    mri_safety = Column(String(100))
    device_description = Column(Text)
    device_size_text = Column(Text)
    sterile = Column(Boolean, default=False)
    single_use = Column(Boolean, default=False)
    implantable = Column(Boolean, default=False)
    life_supporting = Column(Boolean, default=False)
    rx_required = Column(Boolean, default=False)
    otc = Column(Boolean, default=False)
    
    # Commercial Status
    device_comm_distribution_status = Column(String(100), default='In Commercial Distribution')
    
    # Search optimization
    search_vector = Column(TSVECTOR)  # PostgreSQL full-text search
    
    # Raw FDA data for reference
    raw_json = Column(JSONB)
    
    # Sync tracking
    sync_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    gudid_version = Column(Integer)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships to vendor data
    vendor_devices = relationship("VendorDevice", back_populates="gudid_device")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_gudid_manufacturer', 'manufacturer_name'),
        Index('idx_gudid_device_class', 'device_class'),
        Index('idx_gudid_search_vector', 'search_vector', postgresql_using='gin'),
        Index('idx_gudid_model', 'model_number'),
    )


class VendorDevice(Base):
    """
    Vendor-specific device information
    Links to FDA GUDID data and adds vendor content
    """
    __tablename__ = "vendor_devices"
    
    id = Column(Integer, primary_key=True)
    
    # Link to FDA GUDID
    gudid_device_di = Column(String(100), ForeignKey("gudid_devices.primary_di"))
    
    # Vendor organization
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("users.id"))  # Vendor user who created
    
    # Vendor-specific identifiers
    internal_sku = Column(String(100))
    custom_name = Column(String(500))
    
    # Pricing (vendors can make this public or private)
    list_price = Column(DECIMAL(10, 2))
    currency_code = Column(String(3), default='USD')
    price_visibility = Column(String(20), default='private')  # public, private, registered
    
    # Additional vendor information
    warranty_months = Column(Integer)
    specifications = Column(JSONB)
    features = Column(JSONB)
    
    # Training and support
    training_required = Column(Boolean, default=False)
    certification_required = Column(Boolean, default=False)
    support_contact = Column(String(255))
    support_phone = Column(String(20))
    support_email = Column(String(255))
    
    # Access control
    access_level = Column(String(20), default='public')  # public, registered, organization, private
    visibility_settings = Column(JSONB, default={
        "show_price": False,
        "show_contact": False,
        "show_documents": True,
        "show_videos": True,
        "show_specifications": True
    })
    
    # Status
    is_active = Column(Boolean, default=True)
    launch_date = Column(DateTime(timezone=True))
    discontinue_date = Column(DateTime(timezone=True))
    replacement_device_id = Column(Integer, ForeignKey("vendor_devices.id"))
    
    # Tracking
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Relationships
    gudid_device = relationship("GUDIDDevice", back_populates="vendor_devices")
    organization = relationship("Organization", back_populates="vendor_devices")
    documents = relationship("DeviceDocument", back_populates="vendor_device")
    videos = relationship("DeviceVideo", back_populates="vendor_device")
    
    __table_args__ = (
        UniqueConstraint('organization_id', 'gudid_device_di', name='uq_org_device'),
        Index('idx_vendor_org_active', 'organization_id', 'is_active'),
        Index('idx_vendor_gudid', 'gudid_device_di'),
        CheckConstraint("access_level IN ('public', 'registered', 'organization', 'private')", name='check_access_level'),
    )


class DeviceDocument(Base):
    """
    Documents linked to devices (manuals, datasheets, etc.)
    Can be public or private based on vendor settings
    """
    __tablename__ = "device_documents"
    
    id = Column(Integer, primary_key=True)
    
    # Link to vendor device
    vendor_device_id = Column(Integer, ForeignKey("vendor_devices.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    
    # Document metadata
    document_type = Column(String(50), nullable=False)  # manual, datasheet, certificate, etc.
    title = Column(String(500), nullable=False)
    description = Column(Text)
    
    # File information
    file_url = Column(Text, nullable=False)
    file_key = Column(String(500))  # S3 key
    file_size_bytes = Column(Integer)
    file_hash = Column(String(64))
    mime_type = Column(String(100))
    
    # Language and version
    language_code = Column(String(10), default='en')
    version = Column(String(50))
    is_current_version = Column(Boolean, default=True)
    previous_version_id = Column(Integer, ForeignKey("device_documents.id"))
    
    # Content for search
    extracted_text = Column(Text)  # For full-text search
    page_count = Column(Integer)
    metadata = Column(JSONB)
    
    # Access control (inherits from vendor_device but can override)
    access_level = Column(String(20), default='inherit')  # inherit, public, registered, organization, private
    requires_nda = Column(Boolean, default=False)
    
    # Analytics
    download_count = Column(Integer, default=0)
    last_downloaded_at = Column(DateTime(timezone=True))
    
    # Timestamps
    expiration_date = Column(DateTime(timezone=True))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Relationships
    vendor_device = relationship("VendorDevice", back_populates="documents")
    document_chunks = relationship("DocumentChunk", back_populates="document")
    
    __table_args__ = (
        Index('idx_doc_device_type', 'vendor_device_id', 'document_type', 'is_current_version'),
        Index('idx_doc_access', 'access_level'),
        CheckConstraint("document_type IN ('manual', 'quickstart', 'datasheet', 'certificate', 'clinical_study', 'safety_notice')", 
                       name='check_document_type'),
    )


class DocumentChunk(Base):
    """
    Document chunks for RAG (Retrieval Augmented Generation)
    Used for AI-powered Q&A
    """
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("device_documents.id"), nullable=False)
    
    # Chunk information
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    page_number = Column(Integer)
    section_heading = Column(Text)
    
    # Embedding for vector search
    embedding_model = Column(String(50))
    embedding = Column(ARRAY(Float))  # Store as array for pgvector
    
    # Metadata
    metadata = Column(JSONB)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("DeviceDocument", back_populates="document_chunks")
    
    __table_args__ = (
        Index('idx_chunk_document', 'document_id', 'chunk_index'),
        Index('idx_chunk_embedding', 'embedding', postgresql_using='ivfflat'),  # Vector index
    )


class DeviceVideo(Base):
    """
    Training and promotional videos for devices
    Can be public or require registration
    """
    __tablename__ = "device_videos"
    
    id = Column(Integer, primary_key=True)
    
    # Link to vendor device
    vendor_device_id = Column(Integer, ForeignKey("vendor_devices.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    
    # Video metadata
    video_type = Column(String(50))  # training, demo, troubleshooting, marketing
    title = Column(String(500), nullable=False)
    description = Column(Text)
    duration_seconds = Column(Integer)
    
    # URLs
    thumbnail_url = Column(Text)
    video_url = Column(Text, nullable=False)
    hls_playlist_url = Column(Text)  # For adaptive streaming
    transcript_url = Column(Text)
    captions_url = Column(Text)
    
    # Content details
    language_code = Column(String(10), default='en')
    instructor_name = Column(String(255))
    skill_level = Column(String(20))  # beginner, intermediate, advanced
    ceu_credits = Column(DECIMAL(3, 1))
    
    # Tags for discovery
    tags = Column(ARRAY(String))
    
    # Access control
    access_level = Column(String(20), default='registered')  # public, registered, organization, private
    
    # Analytics
    view_count = Column(Integer, default=0)
    average_watch_percentage = Column(DECIMAL(5, 2))
    likes = Column(Integer, default=0)
    dislikes = Column(Integer, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    published_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Relationships
    vendor_device = relationship("VendorDevice", back_populates="videos")
    
    __table_args__ = (
        Index('idx_video_device_active', 'vendor_device_id', 'is_active'),
        Index('idx_video_type', 'video_type'),
        Index('idx_video_tags', 'tags', postgresql_using='gin'),
    )


class Organization(Base):
    """
    Organizations (hospitals, vendors, clinics)
    """
    __tablename__ = "organizations"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # hospital, clinic, vendor, distributor
    subdomain = Column(String(100), unique=True)
    
    # License and billing
    license_tier = Column(String(50), default='free')  # free, basic, professional, enterprise
    license_expires_at = Column(DateTime(timezone=True))
    
    # Settings
    settings = Column(JSONB, default={})
    branding = Column(JSONB, default={})
    
    # Contact information
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state_province = Column(String(100))
    postal_code = Column(String(20))
    country_code = Column(String(2))
    phone = Column(String(20))
    website = Column(Text)
    
    # Status
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime(timezone=True))
    trial_ends_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True))
    
    # Relationships
    vendor_devices = relationship("VendorDevice", back_populates="organization")
    users = relationship("User", back_populates="organization")
    
    __table_args__ = (
        CheckConstraint("type IN ('hospital', 'clinic', 'vendor', 'distributor')", name='check_org_type'),
        Index('idx_org_type', 'type'),
    )
