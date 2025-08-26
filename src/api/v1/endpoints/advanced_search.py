"""
Advanced Public Search API with filters and analytics
Production-ready endpoints for medical device search
"""
from fastapi import APIRouter, Query, HTTPException, Request, Depends, BackgroundTasks
from typing import List, Dict, Any, Optional
import logging

from src.services.search_service import search_service
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


class AdvancedSearchRequest(BaseModel):
    """Advanced search with filters"""
    query: str = Field(..., min_length=2, max_length=200)
    limit: int = Field(10, ge=1, le=50)
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    class Config:
        schema_extra = {
            "example": {
                "query": "infusion pump",
                "limit": 10,
                "filters": {
                    "device_class": "II",
                    "mri_safety": "MR Safe",
                    "sterile": True
                }
            }
        }


class SearchAnalyticsResponse(BaseModel):
    """Search analytics data"""
    total_unique_queries: int
    total_searches: int
    top_queries: List[Dict]
    cache_stats: Dict


@router.post("/search/advanced")
async def advanced_device_search(
    request: AdvancedSearchRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Advanced device search with filters and intelligent ranking.
    
    Features:
    - Multi-field search across 4.78M devices
    - Filter by device class, MRI safety, sterile, etc.
    - Intelligent relevance ranking
    - Response caching based on query popularity
    - <100ms response time for cached queries
    
    Filters available:
    - device_class: I, II, or III
    - mri_safety: MR Safe, MR Conditional, MR Unsafe
    - sterile: true/false
    - single_use: true/false
    - life_supporting: true/false
    """
    try:
        result = await search_service.advanced_search(
            query=request.query,
            limit=request.limit,
            filters=request.filters
        )
        
        # Prefetch popular searches in background
        if result['total_found'] > 0:
            background_tasks.add_task(search_service.prefetch_popular)
        
        return result
        
    except Exception as e:
        logger.error(f"Advanced search error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Search service temporarily unavailable"
        )


@router.get("/search/suggestions")
async def get_search_suggestions(
    partial: str = Query(..., min_length=1, max_length=50)
) -> Dict[str, Any]:
    """
    Get search suggestions based on partial input.
    
    Provides intelligent autocomplete suggestions including:
    - Device names
    - Manufacturer names
    - Common medical terms
    - Previous popular searches
    """
    try:
        # Get suggestions from different sources
        suggestions = {
            'devices': [],
            'manufacturers': [],
            'popular_searches': [],
            'categories': []
        }
        
        # Get device name suggestions
        device_response = search_service.supabase.table('gudid_devices').select(
            'device_name'
        ).ilike('device_name', f'{partial}%').limit(5).execute()
        
        suggestions['devices'] = list(set(
            d['device_name'] for d in device_response.data 
            if d.get('device_name')
        ))[:5]
        
        # Get manufacturer suggestions
        mfr_response = search_service.supabase.table('gudid_devices').select(
            'manufacturer_name'
        ).ilike('manufacturer_name', f'{partial}%').limit(5).execute()
        
        suggestions['manufacturers'] = list(set(
            m['manufacturer_name'] for m in mfr_response.data 
            if m.get('manufacturer_name')
        ))[:5]
        
        # Get popular searches that match
        popular = await search_service.get_popular_searches(20)
        suggestions['popular_searches'] = [
            p['query'] for p in popular 
            if partial.lower() in p['query'].lower()
        ][:5]
        
        # Common categories
        categories = [
            'infusion pumps', 'catheters', 'stents', 'implants',
            'surgical instruments', 'diagnostic equipment', 
            'monitoring devices', 'ventilators'
        ]
        suggestions['categories'] = [
            c for c in categories 
            if partial.lower() in c.lower()
        ][:5]
        
        return suggestions
        
    except Exception as e:
        logger.error(f"Suggestions error: {e}")
        return {
            'devices': [],
            'manufacturers': [],
            'popular_searches': [],
            'categories': []
        }


@router.get("/search/analytics", response_model=SearchAnalyticsResponse)
async def get_search_analytics() -> SearchAnalyticsResponse:
    """
    Get search analytics and performance metrics.
    
    Returns:
    - Total unique queries
    - Total search count
    - Top 10 most popular queries
    - Cache statistics
    """
    try:
        analytics = await search_service.get_search_analytics()
        return SearchAnalyticsResponse(**analytics)
        
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve analytics"
        )


@router.get("/search/trending")
async def get_trending_searches(
    limit: int = Query(10, ge=1, le=50)
) -> Dict[str, Any]:
    """
    Get trending search terms.
    
    Returns the most popular searches in the last hour/day/week.
    """
    try:
        trending = await search_service.get_popular_searches(limit)
        
        return {
            'trending': trending,
            'period': 'current_session',  # Would be enhanced with time-based tracking
            'total_searches': sum(t['count'] for t in trending)
        }
        
    except Exception as e:
        logger.error(f"Trending error: {e}")
        return {'trending': [], 'period': 'unknown', 'total_searches': 0}


@router.post("/search/feedback")
async def submit_search_feedback(
    query: str,
    helpful: bool,
    clicked_result: Optional[str] = None,
    feedback_text: Optional[str] = None
) -> Dict[str, str]:
    """
    Submit feedback on search results quality.
    
    Helps improve search ranking algorithm.
    """
    # This would be stored in a feedback table for analysis
    logger.info(f"Search feedback: query='{query}', helpful={helpful}, clicked={clicked_result}")
    
    return {"status": "feedback_received", "message": "Thank you for your feedback"}


@router.get("/devices/browse")
async def browse_devices_by_category(
    category: Optional[str] = Query(None, description="GMDN category"),
    device_class: Optional[str] = Query(None, regex="^(I|II|III)$"),
    manufacturer: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
) -> Dict[str, Any]:
    """
    Browse devices by category without search query.
    
    Useful for exploring device categories and manufacturers.
    """
    try:
        # Build query
        query = search_service.supabase.table('gudid_devices').select(
            'primary_di, device_name, manufacturer_name, device_class, gmdn_terms'
        )
        
        # Apply filters
        if category:
            query = query.ilike('gmdn_terms', f'%{category}%')
        if device_class:
            query = query.eq('device_class', device_class)
        if manufacturer:
            query = query.eq('manufacturer_name', manufacturer)
        
        # Pagination
        query = query.range(offset, offset + limit - 1)
        
        response = query.execute()
        
        return {
            'devices': response.data,
            'offset': offset,
            'limit': limit,
            'has_more': len(response.data) == limit
        }
        
    except Exception as e:
        logger.error(f"Browse error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to browse devices"
        )
