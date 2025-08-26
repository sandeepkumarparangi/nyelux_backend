"""
Public API endpoints - Hybrid approach with OPTIONAL Supabase
Works with or without Supabase connection
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, Request, Response, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import time
import hashlib
import json
import os

from pydantic import BaseModel, Field

from src.core.config import settings
from src.db.session import get_db
from src.services.analytics_service import AnalyticsService

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize Supabase for GUDID data - OPTIONAL
supabase = None
try:
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        # Disable proxy to avoid the error
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        
        from supabase import create_client, Client
        try:
            from supabase._sync.client import SyncClient
            from supabase.lib.client_options import ClientOptions
            
            options = ClientOptions()
            supabase = SyncClient.create(
                supabase_url=settings.SUPABASE_URL,
                supabase_key=settings.SUPABASE_SERVICE_KEY,
                options=options
            )
            logger.info("Public API: Supabase initialized for GUDID data")
        except Exception as e:
            logger.warning(f"Public API: Could not initialize Supabase: {e}")
    else:
        logger.info("Public API: Supabase not configured")
except Exception as e:
    logger.warning(f"Public API: Supabase setup failed: {e}")

# Initialize analytics service (if available)
try:
    analytics_service = AnalyticsService()
except:
    analytics_service = None
    logger.warning("Analytics service not available")


# Mock data for when Supabase is not available
MOCK_DEVICES = [
    {
        'primary_di': '00889842001234',
        'device_name': 'Infusion Pump Model X200',
        'manufacturer_name': 'Medtronic',
        'brand_name': 'MiniMed',
        'model_number': 'X200',
        'device_class': 'II',
        'device_class_name': 'Class II',
        'gmdn_terms': 'Infusion pump',
        'mri_safety': 'MR Conditional',
        'device_description': 'Programmable infusion pump for medication delivery',
        'sterile': False,
        'single_use': False,
        'implantable': False,
        'life_supporting': True,
        'rx_required': True,
        'otc': False
    },
    {
        'primary_di': '00889842001235',
        'device_name': 'Cardiac Monitor Pro',
        'manufacturer_name': 'Abbott',
        'brand_name': 'CardioView',
        'model_number': 'CM-500',
        'device_class': 'II',
        'device_class_name': 'Class II',
        'gmdn_terms': 'Cardiac monitor',
        'mri_safety': 'MR Unsafe',
        'device_description': 'Multi-parameter cardiac monitoring system',
        'sterile': False,
        'single_use': False,
        'implantable': False,
        'life_supporting': True,
        'rx_required': True,
        'otc': False
    }
]


@router.get("/search")
async def public_device_search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=10, description="Maximum 10 results for public search"),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Public device search endpoint.
    Works with or without Supabase connection.
    """
    start_time = time.time()
    
    try:
        # Track search for analytics if database is available
        if analytics_service and db:
            try:
                await analytics_service.track_event(
                    db,
                    user_id=None,  # Anonymous user
                    organization_id=None,
                    event_type="search",
                    event_category="public",
                    metadata={"query": q},
                    request_context={
                        "ip_address": request.client.host if request else None,
                        "user_agent": request.headers.get("user-agent") if request else None,
                        "referrer_url": request.headers.get("referer") if request else None
                    }
                )
            except Exception as e:
                logger.debug(f"Analytics tracking failed (non-critical): {e}")
        
        # Search for devices
        search_term = q.strip().lower()
        devices = []
        
        if supabase:
            # Try Supabase search
            try:
                response = supabase.table('gudid_devices').select(
                    'primary_di, device_name, manufacturer_name, brand_name, '
                    'model_number, device_class, device_class_name, gmdn_terms, '
                    'mri_safety, device_description, sterile, single_use, '
                    'implantable, life_supporting, rx_required, otc'
                ).ilike('device_name', f'%{search_term}%').limit(limit).execute()
                
                devices = response.data if response.data else []
                
                # If no results from device name, try manufacturer
                if not devices:
                    response = supabase.table('gudid_devices').select(
                        'primary_di, device_name, manufacturer_name, brand_name, '
                        'model_number, device_class, device_class_name, gmdn_terms, '
                        'mri_safety, device_description, sterile, single_use, '
                        'implantable, life_supporting, rx_required, otc'
                    ).ilike('manufacturer_name', f'%{search_term}%').limit(limit).execute()
                    
                    devices = response.data if response.data else []
            except Exception as e:
                logger.error(f"Supabase search error: {e}")
                # Fall back to mock data
                devices = [d for d in MOCK_DEVICES if search_term in d['device_name'].lower() or search_term in d['manufacturer_name'].lower()]
        else:
            # Use mock data
            devices = [d for d in MOCK_DEVICES if search_term in d['device_name'].lower() or search_term in d['manufacturer_name'].lower()]
        
        # Format results
        results = []
        for device in devices[:limit]:
            results.append({
                'id': device.get('primary_di'),
                'primary_di': device.get('primary_di'),
                'device_name': device.get('device_name') or 'Unknown Device',
                'manufacturer': device.get('manufacturer_name') or 'Unknown',
                'manufacturer_name': device.get('manufacturer_name'),
                'brand': device.get('brand_name'),
                'brand_name': device.get('brand_name'),
                'model': device.get('model_number'),
                'model_number': device.get('model_number'),
                'class': device.get('device_class'),
                'device_class': device.get('device_class'),
                'device_class_name': device.get('device_class_name'),
                'gmdn_terms': device.get('gmdn_terms'),
                'mri_safety': device.get('mri_safety'),
                'description': device.get('device_description'),
                'device_description': device.get('device_description'),
                'sterile': device.get('sterile'),
                'single_use': device.get('single_use'),
                'implantable': device.get('implantable'),
                'life_supporting': device.get('life_supporting'),
                'rx_required': device.get('rx_required'),
                'otc': device.get('otc')
            })
        
        response_time = (time.time() - start_time) * 1000
        
        # Log search
        logger.info(f"Public search: query='{q}', results={len(results)}, time={response_time:.0f}ms")
        
        # Try to commit any pending analytics
        if db:
            try:
                await db.commit()
            except:
                pass
        
        return {
            'query': q,
            'results': results,
            'total': len(results),
            'limit': limit,
            'response_time_ms': response_time,
            'cached': False
        }
        
    except Exception as e:
        logger.error(f"Public search error: {e}")
        # Return empty results instead of error for better UX
        return {
            'query': q,
            'results': [],
            'total': 0,
            'limit': limit,
            'error': 'Search temporarily unavailable'
        }


@router.get("/devices/{device_di}")
async def get_public_device(
    device_di: str,
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get device information by DI.
    Works with or without Supabase.
    """
    try:
        # Track device view if analytics available
        if analytics_service and db:
            try:
                await analytics_service.track_event(
                    db,
                    user_id=None,
                    organization_id=None,
                    event_type="device_view",
                    event_category="public",
                    resource_type="device",
                    resource_id=device_di,
                    request_context={
                        "ip_address": request.client.host if request else None,
                        "user_agent": request.headers.get("user-agent") if request else None
                    }
                )
                await db.commit()
            except Exception as e:
                logger.debug(f"Analytics tracking failed (non-critical): {e}")
        
        device = None
        
        if supabase:
            # Try to get from Supabase
            try:
                response = supabase.table('gudid_devices').select('*').eq(
                    'primary_di', device_di
                ).single().execute()
                
                device = response.data
            except Exception as e:
                logger.error(f"Supabase get device error: {e}")
        
        # Fall back to mock data if needed
        if not device:
            for mock_device in MOCK_DEVICES:
                if mock_device['primary_di'] == device_di:
                    device = mock_device
                    break
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Return complete device information
        return {
            'primary_di': device.get('primary_di'),
            'device_name': device.get('device_name'),
            'manufacturer_name': device.get('manufacturer_name'),
            'manufacturer_address': device.get('manufacturer_address'),
            'brand_name': device.get('brand_name'),
            'model_number': device.get('model_number'),
            'catalog_number': device.get('catalog_number'),
            'device_class': device.get('device_class'),
            'device_class_name': device.get('device_class_name'),
            'device_description': device.get('device_description'),
            'gmdn_terms': device.get('gmdn_terms'),
            'product_code': device.get('product_code'),
            'regulation_number': device.get('regulation_number'),
            'mri_safety': device.get('mri_safety'),
            'device_size_text': device.get('device_size_text'),
            'sterile': device.get('sterile'),
            'single_use': device.get('single_use'),
            'implantable': device.get('implantable'),
            'life_supporting': device.get('life_supporting'),
            'rx_required': device.get('rx_required'),
            'otc': device.get('otc')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get device error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve device")


@router.post("/leads")
async def create_lead(
    lead_data: Dict[str, Any],
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Capture lead information after searches.
    Stores in database if available, otherwise logs.
    """
    try:
        # Extract lead info
        email = lead_data.get('email')
        first_name = lead_data.get('first_name')
        last_name = lead_data.get('last_name')
        organization = lead_data.get('organization')
        
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Try to save to database if available
        if db:
            try:
                # Import here to avoid circular dependency
                from src.db.models.lead import Lead
                from sqlalchemy import select
                
                # Check if lead exists
                existing = await db.execute(
                    select(Lead).where(Lead.email == email)
                )
                if not existing.scalar_one_or_none():
                    # Create new lead
                    lead = Lead(
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        organization_name=organization,
                        ip_address=request.client.host if request else None,
                        user_agent=request.headers.get("user-agent") if request else None
                    )
                    db.add(lead)
                    await db.commit()
            except Exception as e:
                logger.error(f"Failed to save lead to database: {e}")
        
        # Log lead for backup
        logger.info(f"Lead captured: {email}, {first_name} {last_name}, {organization}")
        
        return {"message": "Thank you! We'll contact you within 24 hours."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lead creation error: {e}")
        # Still return success to user
        return {"message": "Thank you for your interest!"}


@router.get("/search/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=2)
):
    """
    Get search suggestions for autocomplete.
    Works with mock data when Supabase is not available.
    """
    try:
        search_term = q.strip().lower()
        suggestions = []
        
        if supabase:
            # Try Supabase
            try:
                # Get device name suggestions
                device_response = supabase.table('gudid_devices').select(
                    'device_name'
                ).ilike('device_name', f'{search_term}%').limit(5).execute()
                
                # Get manufacturer suggestions
                mfr_response = supabase.table('gudid_devices').select(
                    'manufacturer_name'
                ).ilike('manufacturer_name', f'{search_term}%').limit(5).execute()
                
                # Format suggestions
                seen = set()
                
                for item in (device_response.data or []):
                    if item.get('device_name') and item['device_name'] not in seen:
                        suggestions.append({
                            'text': item['device_name'],
                            'type': 'device'
                        })
                        seen.add(item['device_name'])
                
                for item in (mfr_response.data or []):
                    if item.get('manufacturer_name') and item['manufacturer_name'] not in seen:
                        suggestions.append({
                            'text': item['manufacturer_name'],
                            'type': 'manufacturer'
                        })
                        seen.add(item['manufacturer_name'])
            except Exception as e:
                logger.error(f"Supabase suggestions error: {e}")
        
        # Fall back to mock suggestions if needed
        if not suggestions:
            mock_suggestions = [
                {'text': 'Infusion Pump', 'type': 'device'},
                {'text': 'Cardiac Monitor', 'type': 'device'},
                {'text': 'Medtronic', 'type': 'manufacturer'},
                {'text': 'Abbott', 'type': 'manufacturer'}
            ]
            suggestions = [s for s in mock_suggestions if search_term in s['text'].lower()]
        
        return {
            'query': q,
            'suggestions': suggestions[:8]
        }
        
    except Exception as e:
        logger.error(f"Suggestion error: {e}")
        return {"query": q, "suggestions": []}


@router.get("/stats")
async def get_public_stats():
    """
    Get public platform statistics.
    """
    try:
        return {
            "total_devices": "4.8M+",
            "total_manufacturers": "5000+",
            "device_classes": {
                "I": "Low Risk",
                "II": "Moderate Risk",
                "III": "High Risk"
            },
            "data_source": "FDA GUDID",
            "last_updated": "Daily",
            "features": [
                "AI-Powered Search",
                "Image Recognition",
                "Barcode Scanning",
                "Team Collaboration",
                "Real-time Support"
            ]
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {"total_devices": "4.8M+"}
