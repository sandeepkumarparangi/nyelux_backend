"""
Search API endpoints.
REAL implementation for device search functionality.
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from src.api.deps import get_db, get_current_user
from src.db.models.user import User
from src.services.search_service import search_service
from src.schemas.device import DeviceSearchRequest, DeviceSearchResponse, SearchFilters

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/devices", response_model=DeviceSearchResponse)
async def search_devices(
    request: DeviceSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Search medical devices with multi-strategy approach.
    
    Implements:
    - Exact DI/UDI matching
    - Full-text search
    - Fuzzy matching
    - Manufacturer + model search
    - GMDN category search
    
    Returns results in <200ms with facets and suggestions.
    """
    try:
        # Convert filters to dict
        filters_dict = None
        if request.filters:
            filters_dict = request.filters.dict(exclude_none=True)
        
        # Execute search
        results = await search_service.search_devices(
            db=db,
            query=request.query,
            filters=filters_dict,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            page=request.page,
            limit=request.limit,
            sort=request.sort
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search service temporarily unavailable"
        )


@router.get("/suggestions")
async def get_search_suggestions(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[str]:
    """
    Get search suggestions based on partial query.
    Used for autocomplete functionality.
    """
    try:
        # Get popular searches matching the query
        suggestions = await search_service.get_popular_searches(
            db=db,
            organization_id=current_user.organization_id,
            limit=limit
        )
        
        # Filter suggestions that start with the query
        filtered = [
            s["query"] for s in suggestions
            if s["query"].lower().startswith(q.lower())
        ]
        
        return filtered[:limit]
        
    except Exception as e:
        logger.error(f"Suggestions error: {e}")
        return []


@router.get("/popular")
async def get_popular_searches(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get popular searches for the organization.
    Shows trending searches to help users.
    """
    try:
        return await search_service.get_popular_searches(
            db=db,
            organization_id=current_user.organization_id,
            limit=limit
        )
    except Exception as e:
        logger.error(f"Popular searches error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve popular searches"
        )


@router.post("/saved")
async def save_search(
    name: str,
    query: str,
    filters: Optional[SearchFilters] = None,
    alert_enabled: bool = False,
    alert_frequency: Optional[str] = Query(None, pattern="^(daily|weekly|monthly)$"),  # Changed from regex to pattern
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Save a search for future use with optional alerts.
    """
    try:
        saved_search = await search_service.save_search(
            db=db,
            user_id=current_user.id,
            name=name,
            query=query,
            filters=filters.dict() if filters else None,
            alert_enabled=alert_enabled,
            alert_frequency=alert_frequency
        )
        
        return {
            "id": saved_search.id,
            "name": saved_search.name,
            "query": saved_search.search_query,
            "filters": saved_search.filters,
            "alert_enabled": saved_search.alert_enabled,
            "alert_frequency": saved_search.alert_frequency,
            "created_at": saved_search.created_at
        }
        
    except Exception as e:
        logger.error(f"Save search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save search"
        )


@router.get("/saved")
async def get_saved_searches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get user's saved searches.
    """
    from src.db.models.search_history import SavedSearch
    from sqlalchemy import select
    
    try:
        stmt = select(SavedSearch).where(
            SavedSearch.user_id == current_user.id
        ).order_by(SavedSearch.created_at.desc())
        
        result = await db.execute(stmt)
        saved_searches = result.scalars().all()
        
        return [
            {
                "id": s.id,
                "name": s.name,
                "query": s.search_query,
                "filters": s.filters,
                "alert_enabled": s.alert_enabled,
                "alert_frequency": s.alert_frequency,
                "created_at": s.created_at
            }
            for s in saved_searches
        ]
        
    except Exception as e:
        logger.error(f"Get saved searches error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve saved searches"
        )


@router.delete("/saved/{search_id}")
async def delete_saved_search(
    search_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Delete a saved search.
    """
    from src.db.models.search_history import SavedSearch
    
    try:
        saved_search = await db.get(SavedSearch, search_id)
        
        if not saved_search:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved search not found"
            )
        
        if saved_search.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this search"
            )
        
        await db.delete(saved_search)
        await db.commit()
        
        return {"message": "Search deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete saved search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete saved search"
        )
