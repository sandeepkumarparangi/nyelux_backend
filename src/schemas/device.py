"""
Device schemas for API responses
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class GUDIDDeviceBase(BaseModel):
    """Base GUDID device schema"""
    primary_di: str
    device_name: str
    manufacturer_name: Optional[str] = None
    manufacturer_di: Optional[str] = None
    brand_name: Optional[str] = None
    model_number: Optional[str] = None
    catalog_number: Optional[str] = None
    device_class: Optional[str] = None
    device_class_name: Optional[str] = None
    gmdn_terms: Optional[str] = None
    gmdn_codes: Optional[str] = None
    product_code: Optional[str] = None
    regulation_number: Optional[str] = None
    mri_safety: Optional[str] = None
    device_description: Optional[str] = None
    device_size_text: Optional[str] = None
    sterile: Optional[bool] = None
    single_use: Optional[bool] = None
    implantable: Optional[bool] = None
    life_supporting: Optional[bool] = None
    rx_required: Optional[bool] = None
    otc: Optional[bool] = None

    model_config = {
        "from_attributes": True,
        "protected_namespaces": ()  # Allow model_number field
    }


class GUDIDDeviceResponse(GUDIDDeviceBase):
    """GUDID device response with timestamps"""
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    sync_timestamp: Optional[datetime] = None


class VendorDeviceBase(BaseModel):
    """Base vendor device schema"""
    gudid_device_di: Optional[str] = None
    internal_sku: Optional[str] = None
    custom_name: Optional[str] = None
    list_price: Optional[float] = None
    currency_code: str = "USD"
    warranty_months: Optional[int] = None
    specifications: Optional[Dict[str, Any]] = None
    features: Optional[List[str]] = None
    training_required: bool = False
    certification_required: bool = False
    access_level: str = "public"


class VendorDeviceCreate(VendorDeviceBase):
    """Create vendor device schema"""
    gudid_device_di: str  # Required for creation


class VendorDeviceUpdate(BaseModel):
    """Update vendor device schema"""
    internal_sku: Optional[str] = None
    custom_name: Optional[str] = None
    list_price: Optional[float] = None
    currency_code: Optional[str] = None
    warranty_months: Optional[int] = None
    specifications: Optional[Dict[str, Any]] = None
    features: Optional[List[str]] = None
    training_required: Optional[bool] = None
    certification_required: Optional[bool] = None
    access_level: Optional[str] = None
    is_active: Optional[bool] = None


class VendorDeviceResponse(VendorDeviceBase):
    """Vendor device response"""
    id: int
    organization_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Include GUDID device info
    device: Optional[GUDIDDeviceResponse] = None
    
    model_config = {
        "from_attributes": True
    }


class DeviceList(BaseModel):
    """List of devices with pagination"""
    items: List[GUDIDDeviceResponse]
    total: int
    page: int
    limit: int
    pages: int


class DeviceSearchResult(BaseModel):
    """Individual search result"""
    device: GUDIDDeviceResponse
    score: float
    highlights: Optional[Dict[str, List[str]]] = None
    vendor_info: Optional[VendorDeviceResponse] = None


class DeviceComparisonRequest(BaseModel):
    """Request to compare devices"""
    device_ids: List[str] = Field(..., min_items=2, max_items=5)
    attributes: Optional[List[str]] = None


class DeviceComparisonResponse(BaseModel):
    """Device comparison response"""
    devices: List[GUDIDDeviceResponse]
    comparison_table: Dict[str, Dict[str, Any]]
    differences: Dict[str, List[str]]
    similarities: Dict[str, Any]


class DeviceAnalytics(BaseModel):
    """Device analytics data"""
    device_id: int
    view_count: int
    unique_viewers: int
    download_count: int
    chat_sessions: int
    average_engagement_time: float
    last_viewed: Optional[datetime] = None


class DeviceEngagement(BaseModel):
    """Device engagement metrics"""
    device_id: int
    period: str
    views: List[Dict[str, Any]]
    downloads: List[Dict[str, Any]]
    searches: List[Dict[str, Any]]
    user_segments: Dict[str, int]


class SearchFilters(BaseModel):
    """Search filter options"""
    device_class: Optional[List[str]] = None
    manufacturer: Optional[List[str]] = None
    mri_safety: Optional[str] = None
    sterile: Optional[bool] = None
    single_use: Optional[bool] = None
    implantable: Optional[bool] = None
    life_supporting: Optional[bool] = None
    rx_required: Optional[bool] = None
    organization_devices_only: Optional[bool] = False


class DevicePublicResponse(BaseModel):
    """Limited device info for public access"""
    primary_di: str
    device_name: str
    manufacturer_name: Optional[str] = None
    device_class: Optional[str] = None
    device_class_name: Optional[str] = None
    gmdn_terms: Optional[str] = None
    mri_safety: Optional[str] = None
    device_description: Optional[str] = None
    sterile: Optional[bool] = None
    single_use: Optional[bool] = None
    implantable: Optional[bool] = None
    life_supporting: Optional[bool] = None

    class Config:
        from_attributes = True


class DeviceSearchRequest(BaseModel):
    """Device search request"""
    query: str = Field(..., min_length=1, max_length=500)
    filters: Optional[SearchFilters] = None
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)
    sort_by: Optional[str] = "relevance"


class DeviceDetailResponse(BaseModel):
    """Full device details for authenticated users"""
    id: Optional[int] = None
    primary_di: str
    device_name: str
    manufacturer_name: Optional[str] = None
    manufacturer_di: Optional[str] = None
    brand_name: Optional[str] = None
    model_number: Optional[str] = None
    catalog_number: Optional[str] = None
    device_class: Optional[str] = None
    device_class_name: Optional[str] = None
    gmdn_terms: Optional[str] = None
    gmdn_codes: Optional[str] = None
    product_code: Optional[str] = None
    regulation_number: Optional[str] = None
    mri_safety: Optional[str] = None
    device_description: Optional[str] = None
    device_size_text: Optional[str] = None
    sterile: Optional[bool] = None
    single_use: Optional[bool] = None
    implantable: Optional[bool] = None
    life_supporting: Optional[bool] = None
    rx_required: Optional[bool] = None
    otc: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Vendor-specific fields
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    list_price: Optional[float] = None
    specifications: Optional[Dict[str, Any]] = None
    features: Optional[List[str]] = None
    
    # Related counts
    document_count: Optional[int] = None
    video_count: Optional[int] = None
    
    class Config:
        from_attributes = True


class DeviceSearchResponse(BaseModel):
    """Device search results"""
    results: List[DeviceDetailResponse]
    total_count: int
    page: int
    limit: int
    facets: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None
    execution_time_ms: Optional[float] = None
