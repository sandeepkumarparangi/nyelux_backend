"""
Lead schemas for API
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class LeadCreate(BaseModel):
    """Lead creation request"""
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    organization_name: Optional[str] = None
    organization_type: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    message: Optional[str] = None
    
    # UTM tracking
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    
    # Device of interest
    interested_device_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "john.doe@hospital.com",
                "first_name": "John",
                "last_name": "Doe",
                "organization_name": "City General Hospital",
                "role": "Clinical Engineer"
            }
        }


class LeadResponse(BaseModel):
    """Lead response"""
    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    organization_name: Optional[str] = None
    lead_status: str
    lead_score: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class LeadUpdate(BaseModel):
    """Lead update request"""
    lead_status: Optional[str] = None
    lead_score: Optional[int] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    contacted_at: Optional[datetime] = None
    qualified_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
