"""
Enhanced Public Device Search API with Real GUDID Data - FIXED VERSION
Handles Supabase search limitations
"""
from fastapi import APIRouter, Query, HTTPException, Request, Depends
from typing import List, Dict, Any, Optional
import time
import logging
from datetime import datetime, timedelta
import hashlib
import json

from supabase import create_client, Client
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.redis_manager import RedisManager

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize Supabase client - REAL DATABASE CONNECTION
if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
    logger.error("Supabase configuration missing!")
    raise ValueError("Supabase configuration is required")

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_KEY  # Always use service key to bypass RLS
)
logger.info(f"Supabase client initialized")

# Initialize Redis for caching (optional but recommended)
try:
    redis_manager = RedisManager() if settings.REDIS_URL else None
except:
    redis_manager = None
    logger.warning("Redis not available - running without cache")


# ============= SCHEMAS =============

class DeviceSearchSuggestion(BaseModel):
    """Typeahead suggestion format"""
    id: str = Field(description="FDA Primary DI")
    display_name: str = Field(description="Device name for display")
    manufacturer: str = Field(description="Manufacturer name")
    category: Optional[str] = Field(description="Device class or category")
    match_type: str = Field(description="What matched: name, manufacturer, or barcode")
    confidence: float = Field(default=1.0, description="Match confidence score")


class DeviceSearchResponse(BaseModel):
    """Search response with metadata"""
    query: str
    suggestions: List[DeviceSearchSuggestion]
    total_found: int
    response_time_ms: float
    cached: bool = False
    search_id: Optional[str] = None


class DevicePublicDetail(BaseModel):
    """Public device details - limited fields to encourage signup"""
    primary_di: str
    device_name: str
    manufacturer_name: str
    brand_name: Optional[str]
    model_number: Optional[str]
    device_class: Optional[str]
    device_description: Optional[str]
    gmdn_terms: Optional[str]
    mri_safety: Optional[str]
    sterile: Optional[bool]
    single_use: Optional[bool]
    implantable: Optional[bool]
    life_supporting: Optional[bool]
    rx_required: Optional[bool]


# ============= SEARCH SERVICE =============

class GUDIDSearchService:
    """
    Production search service using REAL Supabase data.
    Fixed to handle Supabase search limitations.
    """
    
    def __init__(self):
        self.supabase = supabase
        self.cache_ttl = 300  # 5 minutes for popular searches
        
    async def typeahead_search(
        self,
        query: str,
        limit: int = 10,
        search_context: Optional[Dict] = None
    ) -> DeviceSearchResponse:
        """
        Typeahead search with workaround for Supabase limitations.
        Uses multiple strategies to find devices.
        """
        start_time = time.time()
        
        # Clean and validate query
        query = query.strip()
        if len(query) < 2:
            return DeviceSearchResponse(
                query=query,
                suggestions=[],
                total_found=0,
                response_time_ms=0,
                cached=False
            )
        
        # Check cache first
        cache_key = f"typeahead:v3:{query.lower()}:{limit}"
        if redis_manager:
            try:
                cached = await redis_manager.get(cache_key)
                if cached:
                    result = json.loads(cached)
                    result['cached'] = True
                    result['response_time_ms'] = (time.time() - start_time) * 1000
                    return DeviceSearchResponse(**result)
            except:
                pass
        
        try:
            # Strategy 1: Try exact prefix match first
            suggestions = []
            query_lower = query.lower()
            
            # Get a larger set of devices and filter client-side
            # This is a workaround for Supabase search limitations
            logger.info(f"Searching for: '{query}'")
            
            # First, try to get devices by common patterns
            all_results = []
            
            # Get devices starting with the query (using range query)
            try:
                # For device names starting with query
                response = supabase.table('gudid_devices').select(
                    'primary_di, device_name, manufacturer_name, brand_name, model_number, device_class, gmdn_terms'
                ).gte('device_name', query).lt('device_name', query + 'z').limit(limit * 3).execute()
                
                if response.data:
                    all_results.extend(response.data)
                    logger.info(f"Found {len(response.data)} devices by name prefix")
            except Exception as e:
                logger.warning(f"Name prefix search failed: {e}")
            
            # Get devices by manufacturer starting with query
            try:
                response = supabase.table('gudid_devices').select(
                    'primary_di, device_name, manufacturer_name, brand_name, model_number, device_class, gmdn_terms'
                ).gte('manufacturer_name', query).lt('manufacturer_name', query + 'z').limit(limit * 2).execute()
                
                if response.data:
                    all_results.extend(response.data)
                    logger.info(f"Found {len(response.data)} devices by manufacturer prefix")
            except Exception as e:
                logger.warning(f"Manufacturer prefix search failed: {e}")
            
            # If still not enough results, get a sample and filter
            if len(all_results) < limit:
                try:
                    # Get a sample of devices to search through
                    response = supabase.table('gudid_devices').select(
                        'primary_di, device_name, manufacturer_name, brand_name, model_number, device_class, gmdn_terms'
                    ).limit(2000).execute()  # Get more devices to search through
                    
                    if response.data:
                        # Filter client-side for matches
                        for device in response.data:
                            device_name = (device.get('device_name') or '').lower()
                            manufacturer = (device.get('manufacturer_name') or '').lower()
                            brand = (device.get('brand_name') or '').lower()
                            
                            if (query_lower in device_name or 
                                query_lower in manufacturer or 
                                query_lower in brand):
                                if device not in all_results:
                                    all_results.append(device)
                        
                        logger.info(f"Found {len(all_results)} total matches after client-side filter")
                except Exception as e:
                    logger.warning(f"Sample search failed: {e}")
            
            # Process and rank results
            suggestions = self._process_search_results(all_results, query, limit)
            
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
            
            return DeviceSearchResponse(**result)
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            
            # Return empty results instead of error
            return DeviceSearchResponse(
                query=query,
                suggestions=[],
                total_found=0,
                response_time_ms=(time.time() - start_time) * 1000,
                cached=False
            )
    
    def _process_search_results(
        self, 
        raw_results: List[Dict], 
        query: str, 
        limit: int
    ) -> List[Dict]:
        """
        Process and rank search results intelligently.
        """
        query_lower = query.lower()
        processed = []
        seen_devices = set()
        
        for device in raw_results:
            if not device.get('primary_di'):
                continue
                
            # Skip duplicates
            if device['primary_di'] in seen_devices:
                continue
            seen_devices.add(device['primary_di'])
            
            # Determine match type and confidence
            device_name = (device.get('device_name') or '').lower()
            manufacturer = (device.get('manufacturer_name') or '').lower()
            brand = (device.get('brand_name') or '').lower()
            model = (device.get('model_number') or '').lower()
            
            match_type = 'other'
            confidence = 0.5
            
            # Check what matched and assign confidence
            if device_name.startswith(query_lower):
                match_type = 'device_name'
                confidence = 1.0
            elif query_lower in device_name:
                match_type = 'device_name'
                confidence = 0.9
            elif manufacturer.startswith(query_lower):
                match_type = 'manufacturer'
                confidence = 0.95
            elif query_lower in manufacturer:
                match_type = 'manufacturer'
                confidence = 0.85
            elif brand.startswith(query_lower):
                match_type = 'brand'
                confidence = 0.9
            elif query_lower in brand:
                match_type = 'brand'
                confidence = 0.8
            elif query_lower in model:
                match_type = 'model'
                confidence = 0.85
            
            # Create display name
            display_name = device.get('device_name') or device.get('brand_name') or 'Unknown Device'
            if device.get('model_number'):
                display_name = f"{display_name} ({device['model_number']})"
            
            processed.append({
                'id': device['primary_di'],
                'display_name': display_name,
                'manufacturer': device.get('manufacturer_name') or 'Unknown',
                'category': device.get('device_class') or device.get('gmdn_terms') or '',
                'match_type': match_type,
                'confidence': confidence
            })
        
        # Sort by confidence and return top results
        processed.sort(key=lambda x: x['confidence'], reverse=True)
        return processed[:limit]
    
    async def get_device_details(
        self, 
        primary_di: str,
        include_full: bool = False
    ) -> Optional[DevicePublicDetail]:
        """
        Get device details from REAL FDA database.
        """
        try:
            # Try cache first
            cache_key = f"device:public:{primary_di}"
            if redis_manager:
                try:
                    cached = await redis_manager.get(cache_key)
                    if cached:
                        return DevicePublicDetail(**json.loads(cached))
                except:
                    pass
            
            # Query Supabase for device
            response = self.supabase.table('gudid_devices').select(
                '*' if include_full else 
                'primary_di, device_name, manufacturer_name, brand_name, model_number, '
                'device_class, device_description, gmdn_terms, mri_safety, '
                'sterile, single_use, implantable, life_supporting, rx_required'
            ).eq('primary_di', primary_di).single().execute()
            
            if not response.data:
                return None
            
            device_data = response.data
            
            # Cache result
            if redis_manager:
                try:
                    await redis_manager.set(
                        cache_key,
                        json.dumps(device_data, default=str),
                        expire=3600  # 1 hour cache
                    )
                except:
                    pass
            
            return DevicePublicDetail(**device_data)
            
        except Exception as e:
            logger.error(f"Get device error: {e}")
            return None


# Initialize service
search_service = GUDIDSearchService()


# ============= API ENDPOINTS =============

@router.get("/typeahead", response_model=DeviceSearchResponse)
async def device_typeahead(
    q: str = Query(..., min_length=2, max_length=100, description="Search query (min 2 chars)"),
    limit: int = Query(10, ge=1, le=20, description="Max results to return"),
    request: Request = None
):
    """
    Typeahead search for medical devices.
    
    Searches across 4.6M FDA devices using multiple strategies.
    Works around Supabase search limitations.
    
    Example:
    - GET /api/v1/public/typeahead?q=inf
    - Returns: Infusion pumps, Infusion sets, etc.
    """
    return await search_service.typeahead_search(q, limit, {'request': request})


@router.get("/devices/{primary_di}", response_model=DevicePublicDetail)
async def get_device_details(
    primary_di: str,
    request: Request = None
):
    """
    Get public device details by FDA Primary DI.
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
    Get list of manufacturers.
    """
    try:
        if q:
            # Get manufacturers starting with query
            response = supabase.table('gudid_devices').select(
                'manufacturer_name'
            ).gte('manufacturer_name', q).lt('manufacturer_name', q + 'z').limit(limit * 2).execute()
        else:
            # Get sample of manufacturers
            response = supabase.table('gudid_devices').select(
                'manufacturer_name'
            ).limit(limit * 5).execute()
        
        # Deduplicate
        manufacturers = list(set(
            row.get('manufacturer_name') 
            for row in response.data 
            if row.get('manufacturer_name')
        ))
        
        return {
            'manufacturers': sorted(manufacturers)[:limit],
            'total': len(manufacturers)
        }
        
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
    query: str,
    results_shown: int = 0,
    request: Request = None
):
    """
    Track anonymous searches for lead generation.
    """
    session_id = request.headers.get('x-session-id', '') if request else ''
    
    if not session_id and request:
        session_id = hashlib.md5(
            f"{request.client.host}{request.headers.get('user-agent', '')}".encode()
        ).hexdigest()
    
    # Track in Redis if available
    if redis_manager and session_id:
        try:
            search_key = f"searches:{session_id}"
            search_data = {
                'query': query,
                'timestamp': datetime.utcnow().isoformat(),
                'results': results_shown
            }
            
            await redis_manager.client.lpush(search_key, json.dumps(search_data))
            await redis_manager.client.expire(search_key, 3600)
            
            search_count = await redis_manager.client.llen(search_key)
            
            return {
                'session_id': session_id,
                'search_count': search_count,
                'show_lead_form': search_count >= 3
            }
        except Exception as e:
            logger.error(f"Track search error: {e}")
    
    return {'session_id': session_id, 'search_count': 0, 'show_lead_form': False}
