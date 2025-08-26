"""
Super Admin API endpoints for vendor onboarding and system management.
Only accessible by super admins.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, and_
from sqlalchemy.orm import selectinload
import logging
import secrets
import re

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.vendor_profile import VendorProfile
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.vendor_device import VendorDevice
from src.schemas.vendor_portal import VendorProfileCreate, VendorProfileResponse
from src.api.deps import get_current_superuser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/super-admin", tags=["super-admin"])


def generate_url_slug(name: str) -> str:
    """Generate URL-safe slug from company name."""
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower())
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    # Limit length
    if len(slug) > 50:
        slug = slug[:50].rsplit('-', 1)[0]
    return slug


@router.post("/onboard-vendor", response_model=Dict[str, Any])
async def onboard_new_vendor(
    organization_name: str,
    organization_type: str = "vendor",
    admin_email: str = None,
    admin_first_name: str = None,
    admin_last_name: str = None,
    custom_url_slug: Optional[str] = None,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Complete vendor onboarding process:
    1. Create organization
    2. Create vendor profile with auto-generated page
    3. Create vendor admin user (optional)
    4. Initialize with FDA devices
    
    This is the main endpoint for super admin to onboard vendors.
    """
    
    # Validate organization doesn't exist
    existing_org = await db.execute(
        select(Organization).where(
            Organization.name == organization_name
        )
    )
    if existing_org.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization '{organization_name}' already exists"
        )
    
    # Generate or validate URL slug
    if custom_url_slug:
        # Validate custom slug
        if not re.match(r'^[a-z0-9-]+$', custom_url_slug):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL slug can only contain lowercase letters, numbers, and hyphens"
            )
        url_slug = custom_url_slug
    else:
        # Auto-generate slug
        url_slug = generate_url_slug(organization_name)
    
    # Check slug uniqueness
    existing_slug = await db.execute(
        select(VendorProfile).where(
            VendorProfile.url_slug == url_slug
        )
    )
    if existing_slug.scalar_one_or_none():
        # Add random suffix if slug exists
        url_slug = f"{url_slug}-{secrets.token_hex(3)}"
    
    # Step 1: Create organization
    organization = Organization(
        name=organization_name,
        type=organization_type,
        subdomain=url_slug,  # Use same as URL slug for consistency
        license_tier="free",  # Start with free tier
        trial_ends_at=datetime.utcnow() + timedelta(days=30),  # 30-day trial
        settings={
            "vendor_portal_enabled": True,
            "lead_notifications": True
        },
        created_at=datetime.utcnow()
    )
    db.add(organization)
    await db.flush()  # Get organization.id without committing
    
    # Step 2: Create vendor profile
    vendor_profile = VendorProfile(
        organization_id=organization.id,
        url_slug=url_slug,
        display_name=organization_name,
        tagline=f"Quality medical devices from {organization_name}",
        description=f"Welcome to {organization_name}'s device catalog. Browse our FDA-approved medical devices and solutions.",
        
        # Default settings
        public_content_settings={
            "show_pricing": False,
            "show_technical_specs": True,
            "show_training_materials": False,
            "show_support_docs": False,
            "require_registration_for_downloads": True
        },
        
        # Default access tiers
        access_tiers={
            "physician": ["pricing", "clinical_studies", "technical_specs"],
            "nurse": ["training_videos", "quick_guides"],
            "technician": ["service_manuals", "troubleshooting"],
            "clinical_admin": ["pricing", "bulk_ordering", "contracts"]
        },
        
        # Enable features
        lead_capture_enabled=True,
        analytics_enabled=True,
        chat_enabled=True,
        
        # Default messages
        chat_welcome_message=f"Welcome to {organization_name} support. How can I help you with our medical devices today?",
        chat_offline_message="Our support team is currently offline. Please leave a message and we'll get back to you within 24 hours.",
        
        # SEO defaults
        meta_title=f"{organization_name} Medical Devices | Nyelux",
        meta_description=f"Browse {organization_name}'s complete catalog of FDA-approved medical devices. Get product information, request demos, and connect with our team.",
        
        # Set as published immediately
        is_active=True,
        published_at=datetime.utcnow(),
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )
    db.add(vendor_profile)
    await db.flush()
    
    # Step 3: Find and associate FDA devices for this vendor
    # Search for devices by manufacturer name
    gudid_devices = await db.execute(
        select(GUDIDDevice).where(
            GUDIDDevice.manufacturer_name.ilike(f"%{organization_name}%")
        ).limit(1000)  # Limit for initial load
    )
    devices = gudid_devices.scalars().all()
    
    device_count = 0
    for gudid_device in devices:
        # Check if vendor device already exists
        existing = await db.execute(
            select(VendorDevice).where(
                and_(
                    VendorDevice.organization_id == organization.id,
                    VendorDevice.gudid_device_di == gudid_device.primary_di
                )
            )
        )
        if not existing.scalar_one_or_none():
            # Create vendor device entry
            vendor_device = VendorDevice(
                gudid_device_di=gudid_device.primary_di,
                organization_id=organization.id,
                access_level='public',  # Start with public access
                is_active=True,
                created_by=current_user.id,
                created_at=datetime.utcnow()
            )
            db.add(vendor_device)
            device_count += 1
    
    # Update device count in profile
    vendor_profile.total_devices = device_count
    
    # Step 4: Create vendor admin user if email provided
    vendor_admin = None
    temp_password = None
    
    if admin_email:
        # Check if user exists
        existing_user = await db.execute(
            select(User).where(User.email == admin_email)
        )
        if not existing_user.scalar_one_or_none():
            # Generate temporary password
            temp_password = secrets.token_urlsafe(12)
            
            # Create vendor admin user
            from src.services.auth_service import AuthService
            auth_service = AuthService()
            
            vendor_admin = User(
                email=admin_email,
                first_name=admin_first_name or "Admin",
                last_name=admin_last_name or organization_name,
                organization_id=organization.id,
                role="vendor_admin",
                password_hash=auth_service.get_password_hash(temp_password),
                email_verified=False,  # Require email verification
                onboarding_completed=False,
                created_at=datetime.utcnow()
            )
            db.add(vendor_admin)
    
    # Commit all changes
    await db.commit()
    
    # Prepare response
    response = {
        "success": True,
        "organization": {
            "id": organization.id,
            "name": organization.name,
            "type": organization.type
        },
        "vendor_profile": {
            "id": vendor_profile.id,
            "url_slug": vendor_profile.url_slug,
            "public_url": f"https://nyelux.com/vendor/{vendor_profile.url_slug}",
            "admin_url": f"https://nyelux.com/vendor-admin/dashboard",
            "devices_found": device_count
        }
    }
    
    if vendor_admin:
        response["vendor_admin"] = {
            "id": vendor_admin.id,
            "email": vendor_admin.email,
            "temporary_password": temp_password,
            "message": "Please share these credentials securely with the vendor"
        }
    
    logger.info(f"Vendor onboarded successfully: {organization_name} ({url_slug})")
    
    return response


@router.get("/vendors", response_model=List[Dict[str, Any]])
async def list_all_vendors(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    List all vendor profiles in the system.
    Super admin only.
    """
    query = select(VendorProfile).options(
        selectinload(VendorProfile.organization)
    )
    
    if not include_inactive:
        query = query.where(VendorProfile.is_active == True)
    
    query = query.order_by(VendorProfile.created_at.desc())
    
    result = await db.execute(query)
    profiles = result.scalars().all()
    
    vendors = []
    for profile in profiles:
        # Get stats
        lead_count = await db.execute(
            select(func.count()).select_from(VendorLead).where(
                VendorLead.vendor_profile_id == profile.id
            )
        )
        
        vendors.append({
            "id": profile.id,
            "organization_name": profile.organization.name,
            "display_name": profile.display_name,
            "url_slug": profile.url_slug,
            "public_url": f"https://nyelux.com/vendor/{profile.url_slug}",
            "is_active": profile.is_active,
            "is_featured": profile.is_featured,
            "published_at": profile.published_at,
            "total_devices": profile.total_devices,
            "total_leads": lead_count.scalar(),
            "created_at": profile.created_at
        })
    
    return vendors


@router.put("/vendors/{vendor_id}/toggle-featured")
async def toggle_vendor_featured(
    vendor_id: int,
    is_featured: bool,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Toggle featured status for vendor (appears at top of directory).
    Super admin only.
    """
    result = await db.execute(
        select(VendorProfile).where(VendorProfile.id == vendor_id)
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    vendor_profile.is_featured = is_featured
    vendor_profile.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {
        "success": True,
        "vendor_id": vendor_id,
        "is_featured": is_featured
    }


@router.put("/vendors/{vendor_id}/toggle-active")
async def toggle_vendor_active(
    vendor_id: int,
    is_active: bool,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Activate or deactivate a vendor profile.
    Super admin only.
    """
    result = await db.execute(
        select(VendorProfile).where(VendorProfile.id == vendor_id)
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )
    
    vendor_profile.is_active = is_active
    if not is_active:
        vendor_profile.deleted_at = datetime.utcnow()
    else:
        vendor_profile.deleted_at = None
    
    vendor_profile.updated_at = datetime.utcnow()
    
    # Log the action
    logger.info(
        f"Vendor {vendor_id} {'activated' if is_active else 'deactivated'} "
        f"by {current_user.email}. Reason: {reason}"
    )
    
    await db.commit()
    
    return {
        "success": True,
        "vendor_id": vendor_id,
        "is_active": is_active,
        "reason": reason
    }


@router.post("/initialize-vendor-pages")
async def initialize_all_vendor_pages(
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Initialize vendor pages for all existing vendor organizations.
    This creates a page for each vendor based on FDA GUDID data.
    Super admin only - run once for initial setup.
    """
    
    # Get all vendor organizations without profiles
    result = await db.execute(
        select(Organization).where(
            and_(
                Organization.type == 'vendor',
                Organization.deleted_at.is_(None)
            )
        ).outerjoin(
            VendorProfile,
            VendorProfile.organization_id == Organization.id
        ).where(
            VendorProfile.id.is_(None)
        )
    )
    organizations = result.scalars().all()
    
    created_profiles = []
    
    for org in organizations:
        # Generate URL slug
        url_slug = generate_url_slug(org.name)
        
        # Check uniqueness
        existing = await db.execute(
            select(VendorProfile).where(
                VendorProfile.url_slug == url_slug
            )
        )
        if existing.scalar_one_or_none():
            url_slug = f"{url_slug}-{org.id}"
        
        # Create vendor profile
        profile = VendorProfile(
            organization_id=org.id,
            url_slug=url_slug,
            display_name=org.name,
            tagline=f"Medical devices from {org.name}",
            description=f"Browse {org.name}'s catalog of FDA-approved medical devices.",
            is_active=True,
            published_at=datetime.utcnow(),
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.add(profile)
        
        # Count devices for this vendor
        device_count = await db.execute(
            select(func.count()).select_from(VendorDevice).where(
                VendorDevice.organization_id == org.id
            )
        )
        profile.total_devices = device_count.scalar()
        
        created_profiles.append({
            "organization": org.name,
            "url_slug": url_slug,
            "devices": profile.total_devices
        })
    
    await db.commit()
    
    return {
        "success": True,
        "profiles_created": len(created_profiles),
        "details": created_profiles
    }


@router.get("/system-stats")
async def get_system_statistics(
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get overall system statistics for vendor portal.
    Super admin only.
    """
    
    # Count vendors
    vendor_count = await db.execute(
        select(func.count()).select_from(VendorProfile).where(
            VendorProfile.is_active == True
        )
    )
    
    # Count total leads
    from src.db.models.vendor_lead import VendorLead
    lead_count = await db.execute(
        select(func.count()).select_from(VendorLead)
    )
    
    # Count service requests
    from src.db.models.vendor_service import VendorServiceRequest
    service_count = await db.execute(
        select(func.count()).select_from(VendorServiceRequest)
    )
    
    # Get top vendors by leads
    top_vendors = await db.execute(
        select(
            VendorProfile.display_name,
            func.count(VendorLead.id).label('lead_count')
        ).join(
            VendorLead,
            VendorLead.vendor_profile_id == VendorProfile.id
        ).group_by(
            VendorProfile.id
        ).order_by(
            func.count(VendorLead.id).desc()
        ).limit(5)
    )
    
    return {
        "total_vendors": vendor_count.scalar(),
        "total_leads": lead_count.scalar(),
        "total_service_requests": service_count.scalar(),
        "top_vendors_by_leads": [
            {"vendor": row[0], "leads": row[1]}
            for row in top_vendors
        ]
    }
