"""
Ultra-Fast Typeahead Search API for Keystroke-by-Keystroke Search
Optimized for <100ms response times with caching and smart strategies
"""
from fastapi import APIRouter, Query, HTTPException, Request, BackgroundTasks
from typing import List, Dict, Any, Optional
import time
import logging
from datetime import datetime
import hashlib
import json
import asyncio

from supabase import create_client, Client
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.redis_manager import RedisManager

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize Supabase client - Make it optional
supabase = None
try:
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        import os
        # Disable proxy to avoid the error
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        
        try:
            from supabase._sync.client import SyncClient
            from supabase.lib.client_options import ClientOptions
            
            options = ClientOptions()
            supabase = SyncClient.create(
                supabase_url=settings.SUPABASE_URL,
                supabase_key=settings.SUPABASE_SERVICE_KEY,
                options=options
            )
            logger.info("Fast typeahead: Supabase initialized")
        except Exception as e:
            logger.warning(f"Fast typeahead: Could not initialize Supabase: {e}")
    else:
        logger.warning("Fast typeahead: Supabase not configured")
except Exception as e:
    logger.warning(f"Fast typeahead: Supabase setup failed: {e}")

# Initialize Redis for caching
try:
    redis_manager = RedisManager() if settings.REDIS_URL else None
    logger.info("Redis caching enabled for typeahead")
except:
    redis_manager = None
    logger.warning("Redis not available - typeahead will be slower")


# ============= SCHEMAS =============

class TypeaheadSuggestion(BaseModel):
    """Lightweight suggestion for typeahead"""
    id: str
    text: str  # Display text
    subtitle: Optional[str] = None  # Manufacturer or category
    type: str = "device"  # device, manufacturer, category


class TypeaheadResponse(BaseModel):
    """Optimized typeahead response"""
    query: str
    suggestions: List[TypeaheadSuggestion]
    response_ms: float
    cached: bool = False
    has_more: bool = False


# ============= TYPEAHEAD SERVICE =============

class FastTypeaheadService:
    """
    Ultra-fast typeahead service optimized for keystroke search.
    Target: <100ms response time
    """
    
    def __init__(self):
        self.supabase = supabase
        self.min_query_length = 2
        self.max_suggestions = 8  # Limit for speed
        self.cache_ttl = 3600  # 1 hour cache for popular searches
        
        # Preload popular searches on startup
        self.popular_cache = {}
        asyncio.create_task(self._preload_popular())
    
    async def _preload_popular(self):
        """Preload popular search terms for instant response"""
        popular_terms = [
            "pump", "catheter", "syringe", "monitor", "implant",
            "stent", "valve", "sensor", "needle", "tube"
        ]
        
        for term in popular_terms:
            try:
                await self.search(term, use_cache=False)
                logger.info(f"Preloaded: {term}")
            except:
                pass
    
    async def search(
        self,
        query: str,
        limit: int = 8,
        use_cache: bool = True
    ) -> TypeaheadResponse:
        """
        Ultra-fast search optimized for keystroke-by-keystroke.
        
        Strategy:
        1. Check memory cache (0ms)
        2. Check Redis cache (<5ms)
        3. Use smart query strategy (<100ms)
        """
        start_time = time.time()
        
        # Clean query
        query = query.strip().lower()
        if len(query) < self.min_query_length:
            return TypeaheadResponse(
                query=query,
                suggestions=[],
                response_ms=0,
                cached=False
            )
        
        # Level 1: Memory cache (instant)
        if use_cache and query in self.popular_cache:
            result = self.popular_cache[query].copy()
            result['cached'] = True
            result['response_ms'] = (time.time() - start_time) * 1000
            return TypeaheadResponse(**result)
        
        # Level 2: Redis cache (very fast)
        if use_cache and redis_manager:
            cache_key = f"typeahead:fast:{query}"
            try:
                cached = await redis_manager.get(cache_key)
                if cached:
                    result = json.loads(cached)
                    result['cached'] = True
                    result['response_ms'] = (time.time() - start_time) * 1000
                    return TypeaheadResponse(**result)
            except:
                pass
        
        # Level 3: Smart database query
        suggestions = await self._smart_search(query, limit)
        
        # Build response
        result = {
            'query': query,
            'suggestions': suggestions,
            'response_ms': (time.time() - start_time) * 1000,
            'cached': False,
            'has_more': len(suggestions) == limit
        }
        
        # Cache result if successful
        if suggestions and redis_manager:
            try:
                cache_key = f"typeahead:fast:{query}"
                await redis_manager.set(
                    cache_key,
                    json.dumps(result, default=str),
                    expire=self.cache_ttl
                )
                
                # Also add to memory cache if popular
                if len(self.popular_cache) < 100:  # Limit memory usage
                    self.popular_cache[query] = result.copy()
            except:
                pass
        
        return TypeaheadResponse(**result)
    
    async def _smart_search(self, query: str, limit: int) -> List[Dict]:
        """
        Smart search strategy for fast results.
        Uses prefix matching which is faster than substring search.
        """
        suggestions = []
        
        # Return mock data if Supabase is not available
        if not self.supabase:
            mock_devices = [
                {'id': '1', 'text': 'Infusion Pump X200', 'subtitle': 'Medtronic', 'type': 'device'},
                {'id': '2', 'text': 'Cardiac Monitor Pro', 'subtitle': 'Abbott', 'type': 'device'},
                {'id': '3', 'text': 'Surgical Suture Kit', 'subtitle': 'Johnson & Johnson', 'type': 'device'}
            ]
            return [d for d in mock_devices if query in d['text'].lower()][:limit]
        
        try:
            # Strategy 1: Prefix match on device_name (fastest)
            response = supabase.table('gudid_devices').select(
                'primary_di, device_name, manufacturer_name'
            ).gte('device_name', query.upper()).lt('device_name', query.upper() + 'z').limit(limit).execute()
            
            for device in response.data[:limit]:
                suggestions.append({
                    'id': device['primary_di'],
                    'text': device['device_name'] or 'Unknown Device',
                    'subtitle': device['manufacturer_name'],
                    'type': 'device'
                })
            
            # If not enough results, try manufacturer prefix
            if len(suggestions) < limit // 2:
                response = supabase.table('gudid_devices').select(
                    'primary_di, device_name, manufacturer_name'
                ).gte('manufacturer_name', query.upper()).lt('manufacturer_name', query.upper() + 'z').limit(limit - len(suggestions)).execute()
                
                for device in response.data:
                    if device['primary_di'] not in [s['id'] for s in suggestions]:
                        suggestions.append({
                            'id': device['primary_di'],
                            'text': device['device_name'] or 'Unknown Device',
                            'subtitle': device['manufacturer_name'],
                            'type': 'device'
                        })
            
        except Exception as e:
            logger.error(f"Smart search error: {e}")
        
        return suggestions[:limit]


# Initialize service
typeahead_service = FastTypeaheadService()


# ============= FAST ENDPOINTS =============

@router.get("/fast", response_model=TypeaheadResponse)
async def fast_typeahead(
    q: str = Query(..., min_length=2, max_length=50, description="Search query"),
    background_tasks: BackgroundTasks = None
):
    """
    Ultra-fast typeahead endpoint for keystroke-by-keystroke search.
    
    Optimized for:
    - <100ms response time
    - Minimal payload size
    - Smart caching
    - Concurrent requests
    
    Frontend usage:
    ```javascript
    // Debounce at 150ms for optimal UX
    const searchDevices = debounce(async (query) => {
        const response = await fetch(`/api/v1/public/fast?q=${query}`);
        const data = await response.json();
        updateSuggestions(data.suggestions);
    }, 150);
    
    // On every keystroke
    input.addEventListener('input', (e) => {
        if (e.target.value.length >= 2) {
            searchDevices(e.target.value);
        }
    });
    ```
    """
    return await typeahead_service.search(q)


@router.get("/instant/{prefix}")
async def instant_search(
    prefix: str,
    limit: int = Query(5, ge=1, le=10)
):
    """
    Even faster endpoint using path parameter (better caching).
    
    Example: GET /api/v1/public/instant/pump
    
    This allows CDN/browser caching of common prefixes.
    """
    if len(prefix) < 2:
        return {"suggestions": []}
    
    result = await typeahead_service.search(prefix, limit)
    return result


@router.post("/preload")
async def preload_searches(
    terms: List[str] = Query(..., description="Terms to preload"),
    background_tasks: BackgroundTasks = None
):
    """
    Preload common searches for instant response.
    Call this on app start or when user is idle.
    """
    if not terms or len(terms) > 20:
        raise HTTPException(400, "Provide 1-20 terms to preload")
    
    # Preload in background
    async def _preload():
        for term in terms:
            try:
                await typeahead_service.search(term, use_cache=False)
            except:
                pass
    
    if background_tasks:
        background_tasks.add_task(_preload)
    else:
        await _preload()
    
    return {"status": "preloading", "terms": len(terms)}


@router.get("/popular")
async def get_popular_searches():
    """
    Get popular search suggestions for instant display.
    Show these when search box is focused but empty.
    """
    popular = [
        {"text": "Infusion Pumps", "icon": "💉"},
        {"text": "Catheters", "icon": "🏥"},
        {"text": "Surgical Instruments", "icon": "⚕️"},
        {"text": "Patient Monitors", "icon": "📊"},
        {"text": "Implants", "icon": "🦴"},
        {"text": "Diagnostic Equipment", "icon": "🔬"},
    ]
    
    return {
        "popular": popular,
        "trending": [
            "Medtronic devices",
            "Abbott products",
            "Boston Scientific"
        ]
    }


# ============= PERFORMANCE MONITORING =============

@router.get("/performance/stats")
async def get_performance_stats():
    """
    Get typeahead performance statistics.
    Useful for monitoring and optimization.
    """
    stats = {
        "cache_size": len(typeahead_service.popular_cache),
        "cached_queries": list(typeahead_service.popular_cache.keys())[:10],
        "redis_available": redis_manager is not None,
        "target_response_ms": 100,
        "recommendations": {
            "frontend_debounce_ms": 150,
            "min_query_length": 2,
            "max_suggestions": 8
        }
    }
    
    return stats
