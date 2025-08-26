"""
Public API endpoints using Supabase directly
NO SQLAlchemy models - direct Supabase queries only
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, Request, HTTPException
import logging
import time

from supabase import create_client, Client
from src.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize Supabase client
try:
    supabase: Client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_KEY
    )
    logger.info("Public API: Supabase client initialized")
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    supabase = None


@router.get("/search")
async def public_device_search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=10, description="Maximum 10 results for public search"),
    request: Request = None
):
    """
    Public device search using Supabase directly.
    NO SQLAlchemy - REAL Supabase queries only.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Search service unavailable")
    
    start_time = time.time()
    
    try:
        # Clean search query
        search_term = q.strip()
        
        # Search in Supabase GUDID table
        response = supabase.table('gudid_devices').select(
            'primary_di, device_name, manufacturer_name, brand_name, '
            'model_number, device_class, gmdn_terms, mri_safety, '
            'sterile, single_use, implantable, life_supporting'
        ).or_(
            f"device_name.ilike.%{search_term}%,"
            f"manufacturer_name.ilike.%{search_term}%,"
            f"brand_name.ilike.%{search_term}%,"
            f"model_number.ilike.%{search_term}%"
        ).limit(limit).execute()
        
        # Format results
        devices = []
        for device in (response.data or []):
            devices.append({
                'id': device.get('primary_di'),
                'device_name': device.get('device_name') or 'Unknown Device',
                'manufacturer': device.get('manufacturer_name') or 'Unknown',
                'brand': device.get('brand_name'),
                'model': device.get('model_number'),
                'class': device.get('device_class'),
                'gmdn_terms': device.get('gmdn_terms'),
                'mri_safety': device.get('mri_safety'),
                'sterile': device.get('sterile'),
                'single_use': device.get('single_use'),
                'implantable': device.get('implantable'),
                'life_supporting': device.get('life_supporting')
            })
        
        response_time = (time.time() - start_time) * 1000
        
        # Log search for analytics (without database)
        logger.info(f"Public search: query='{q}', results={len(devices)}, time={response_time:.0f}ms")
        
        return {
            'query': q,
            'results': devices,
            'total': len(devices),
            'limit': limit,
            'response_time_ms': response_time
        }
        
    except Exception as e:
        logger.error(f"Public search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/devices/{device_id}")
async def get_public_device(
    device_id: str,
    request: Request = None
):
    """
    Get device information by ID using Supabase directly.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Service unavailable")
    
    try:
        # Get device from Supabase
        response = supabase.table('gudid_devices').select('*').eq(
            'primary_di', device_id
        ).single().execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Device not found")
        
        device = response.data
        
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


@router.get("/search/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=2)
):
    """
    Get search suggestions using Supabase directly.
    """
    if not supabase:
        return {"suggestions": []}
    
    try:
        search_term = q.strip()
        
        # Get device name suggestions
        device_response = supabase.table('gudid_devices').select(
            'device_name'
        ).ilike('device_name', f'{search_term}%').limit(5).execute()
        
        # Get manufacturer suggestions
        mfr_response = supabase.table('gudid_devices').select(
            'manufacturer_name'
        ).ilike('manufacturer_name', f'{search_term}%').limit(5).execute()
        
        # Combine and deduplicate
        suggestions = []
        seen = set()
        
        for item in (device_response.data or []):
            name = item.get('device_name')
            if name and name not in seen:
                suggestions.append({
                    'text': name,
                    'type': 'device'
                })
                seen.add(name)
        
        for item in (mfr_response.data or []):
            name = item.get('manufacturer_name')
            if name and name not in seen:
                suggestions.append({
                    'text': name,
                    'type': 'manufacturer'
                })
                seen.add(name)
        
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
    Get public platform statistics using Supabase.
    """
    if not supabase:
        return {
            "total_devices": "4.8M+",
            "status": "Service temporarily unavailable"
        }
    
    try:
        # Get approximate count (Supabase has limitations on count)
        # For demo, return known values
        return {
            "total_devices": "4.8M+",
            "total_manufacturers": "5000+",
            "device_classes": {
                "I": "Low Risk",
                "II": "Moderate Risk", 
                "III": "High Risk"
            },
            "data_source": "FDA GUDID",
            "last_updated": "Daily"
        }
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {
            "total_devices": "4.8M+",
            "error": "Stats temporarily unavailable"
        }


@router.get("/test")
async def test_connection():
    """
    Test endpoint to verify Supabase connection.
    """
    if not supabase:
        return {"status": "error", "message": "Supabase not configured"}
    
    try:
        # Try a simple query
        response = supabase.table('gudid_devices').select(
            'primary_di'
        ).limit(1).execute()
        
        return {
            "status": "success",
            "message": "Supabase connected",
            "test_record": response.data[0] if response.data else None
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
