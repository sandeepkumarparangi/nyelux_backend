"""
Ultra-fast device search endpoint for <50ms typeahead
"""
from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any
import time
import logging

from src.services.gudid_cloud_service import DeviceSearchService
from src.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize search service
try:
    search_service = DeviceSearchService() if settings.SUPABASE_URL else None
except Exception as e:
    logger.warning(f"Could not initialize search service: {e}")
    search_service = None


@router.get("/devices/typeahead")
async def device_typeahead(
    q: str = Query(..., min_length=2, max_length=100, description="Search query (min 2 chars)"),
    limit: int = Query(10, ge=1, le=20, description="Max results to return")
) -> Dict[str, Any]:
    """
    Ultra-fast typeahead search for medical devices.
    
    Searches across:
    - Device name
    - Manufacturer name  
    - Barcode number (FDA UDI)
    - Model number (if no barcode)
    
    Returns results in <50ms using Supabase's optimized indexes.
    
    Example:
    - GET /api/v1/public/devices/typeahead?q=inf
    - Returns: Infusion pumps, Infusion sets, etc.
    """
    start_time = time.time()
    
    if not search_service:
        raise HTTPException(
            status_code=503,
            detail="Search service not configured. Please set up Supabase."
        )
    
    try:
        # Get search results
        results = search_service.typeahead_search(q)
        
        # Calculate response time
        response_time_ms = (time.time() - start_time) * 1000
        
        # Log performance
        if response_time_ms > 50:
            logger.warning(f"Slow search: {response_time_ms:.1f}ms for query: {q}")
        
        return {
            "query": q,
            "suggestions": results['suggestions'][:limit],
            "response_time_ms": round(response_time_ms, 1),
            "cached": results.get('cached', False)
        }
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Search service temporarily unavailable"
        )


@router.get("/devices/{primary_di}")
async def get_device_details(primary_di: str) -> Dict[str, Any]:
    """
    Get full device details by primary DI.
    """
    if not search_service:
        raise HTTPException(
            status_code=503,
            detail="Search service not configured"
        )
    
    device = search_service.cloud_service.get_device_details(primary_di)
    
    if not device:
        raise HTTPException(
            status_code=404,
            detail="Device not found"
        )
    
    return device
