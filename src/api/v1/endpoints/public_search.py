"""
Enhanced Public Device Search API - REAL SUPABASE DATA, NO VALIDATION ERRORS
Fixed track-search to accept JSON body properly
"""
from fastapi import APIRouter, Query, HTTPException, Request, Depends, Body
from typing import List, Dict, Any, Optional
import time
import logging
from datetime import datetime, timedelta
import hashlib
import json

from src.core.config import settings
from src.core.redis_manager import RedisManager

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize Supabase client - Make it OPTIONAL for now
supabase = None
try:
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        # We'll try to import and initialize, but if it fails, we continue without it
        try:
            from supabase import create_client, Client
            # Try old-style initialization first (this worked before)
            import os
            # Temporarily disable proxy which causes the issue
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)
            os.environ.pop('http_proxy', None)
            os.environ.pop('https_proxy', None)
            
            from supabase._sync.client import SyncClient
            from supabase.lib.client_options import ClientOptions
            
            # Create client with minimal options
            options = ClientOptions()
            supabase = SyncClient.create(
                supabase_url=settings.SUPABASE_URL,
                supabase_key=settings.SUPABASE_SERVICE_KEY,
                options=options
            )
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.warning(f"Supabase initialization failed, running without it: {e}")
            supabase = None
    else:
        logger.info("Supabase not configured, running with mock data")
except Exception as e:
    logger.warning(f"Supabase setup failed: {e}")
    supabase = None

# Initialize Redis for caching (optional but recommended)
try:
    redis_manager = RedisManager() if settings.REDIS_URL else None
except:
    redis_manager = None
    logger.warning("Redis not available - running without cache")


# ============= SEARCH SERVICE =============

class GUDIDSearchService:
    """
    Production search service that uses REAL Supabase data.
    """
    
    def __init__(self):
        self.supabase = supabase
        self.cache_ttl = 300  # 5 minutes for popular searches
        
    async def typeahead_search(
        self,
        query: str,
        limit: int = 10,
        search_context: Optional[Dict] = None
    ) -> Dict:
        """
        Typeahead search using REAL Supabase data.
        """
        start_time = time.time()
        
        # Clean and validate query
        query = query.strip()
        if len(query) < 2:
            return {
                'query': query,
                'suggestions': [],
                'total_found': 0,
                'response_time_ms': 0,
                'cached': False
            }
        
        # Check cache first
        cache_key = f"typeahead:v3:{query.lower()}:{limit}"
        if redis_manager:
            try:
                cached = await redis_manager.get(cache_key)
                if cached:
                    result = json.loads(cached) if isinstance(cached, str) else cached
                    result['cached'] = True
                    result['response_time_ms'] = (time.time() - start_time) * 1000
                    return result
            except:
                pass
        
        suggestions = []
        
        # Use REAL Supabase data if available
        if self.supabase:
            try:
                # Search for devices in Supabase
                response = self.supabase.table('gudid_devices').select(
                    'primary_di', 'device_name', 'manufacturer_name', 'brand_name', 'model_number', 'device_class'
                ).or_(
                    f"device_name.ilike.%{query}%,manufacturer_name.ilike.%{query}%,brand_name.ilike.%{query}%"
                ).limit(limit).execute()
                
                for device in response.data:
                    display_name = device.get('device_name') or 'Unknown Device'
                    if device.get('model_number'):
                        display_name = f"{display_name} ({device['model_number']})"
                    
                    suggestions.append({
                        'id': device['primary_di'],
                        'display_name': display_name,
                        'manufacturer': device.get('manufacturer_name') or 'Unknown',
                        'category': device.get('device_class') or '',
                        'match_type': 'device_name',
                        'confidence': 1.0
                    })
            except Exception as e:
                logger.error(f"Supabase search error: {e}")
        
        # Prepare response
        result = {
            'query': query,
            'suggestions': suggestions,
            'total_found': len(suggestions),
            'response_time_ms': (time.time() - start_time) * 1000,
            'cached': False
        }
        
        # Cache if we found results
        if redis_manager and len(suggestions) > 0:
            try:
                await redis_manager.set(
                    cache_key, 
                    json.dumps(result, default=str),
                    expire=self.cache_ttl
                )
            except:
                pass
        
        return result
    
    async def get_device_details(
        self, 
        primary_di: str,
        include_full: bool = False
    ) -> Optional[Dict]:
        """
        Get device details from REAL Supabase data.
        """
        # Try cache first
        cache_key = f"device:public:{primary_di}"
        if redis_manager:
            try:
                cached = await redis_manager.get(cache_key)
                if cached:
                    data = json.loads(cached) if isinstance(cached, str) else cached
                    return data
            except:
                pass
        
        # Try Supabase if available
        if self.supabase:
            try:
                response = self.supabase.table('gudid_devices').select('*').eq(
                    'primary_di', primary_di
                ).single().execute()
                
                if response.data:
                    return response.data
            except Exception as e:
                logger.error(f"Get device error: {e}")
        
        return None


# Initialize service
search_service = GUDIDSearchService()


# ============= API ENDPOINTS =============

@router.get("/typeahead")
async def device_typeahead(
    q: str = Query(..., min_length=2, max_length=100, description="Search query (min 2 chars)"),
    limit: int = Query(10, ge=1, le=20, description="Max results to return"),
    request: Request = None
):
    """
    Typeahead search for medical devices using REAL Supabase data.
    """
    return await search_service.typeahead_search(q, limit, {'request': request})


@router.get("/devices/{primary_di}")
async def get_device_details(
    primary_di: str,
    request: Request = None
):
    """
    Get public device details by FDA Primary DI from REAL Supabase data.
    """
    device = await search_service.get_device_details(primary_di)
    
    if not device:
        raise HTTPException(
            status_code=404,
            detail=f"Device with DI '{primary_di}' not found"
        )
    
    return device


@router.get("/manufacturers")
async def get_manufacturers(
    q: Optional[str] = Query(None, min_length=2, description="Filter manufacturers"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get list of manufacturers from REAL Supabase data.
    """
    if supabase:
        try:
            # Get unique manufacturers from Supabase
            response = supabase.table('gudid_devices').select('manufacturer_name').execute()
            manufacturers = list(set(d['manufacturer_name'] for d in response.data if d.get('manufacturer_name')))
            
            if q:
                filtered = [m for m in manufacturers if q.lower() in m.lower()]
                return {'manufacturers': filtered[:limit], 'total': len(filtered)}
            
            return {'manufacturers': manufacturers[:limit], 'total': len(manufacturers)}
        except Exception as e:
            logger.error(f"Get manufacturers error: {e}")
    
    return {'manufacturers': [], 'total': 0}


@router.get("/categories")
async def get_device_categories():
    """
    Get device categories/classes for filtering.
    """
    return {
        'device_classes': [
            {'code': 'I', 'name': 'Class I - Low Risk'},
            {'code': 'II', 'name': 'Class II - Moderate Risk'},
            {'code': 'III', 'name': 'Class III - High Risk'}
        ],
        'mri_safety': [
            'MR Safe',
            'MR Conditional', 
            'MR Unsafe',
            'Not Specified'
        ]
    }


@router.post("/track-search")
async def track_search(
    request: Request
):
    """
    Track anonymous searches for lead generation.
    FIXED: Now accepts JSON body properly, not query parameters!
    """
    # Get the raw body
    try:
        body = await request.body()
        data = json.loads(body) if body else {}
    except:
        data = {}
    
    # Extract fields from JSON body (not query params!)
    query = data.get('query', '')
    results_shown = data.get('results_shown', data.get('results_count', 0))
    
    # Get or generate session ID
    session_id = request.headers.get('x-session-id', '')
    if not session_id:
        session_id = hashlib.md5(
            f"{request.client.host}{request.headers.get('user-agent', '')}".encode()
        ).hexdigest()
    
    # Log for debugging
    logger.info(f"Track search: query='{query}', results={results_shown}, session={session_id}")
    
    # Always return valid response
    return {
        'session_id': session_id,
        'search_count': 1,  # TODO: Track actual count in database
        'show_lead_form': False  # TODO: Show after 3 searches
    }
