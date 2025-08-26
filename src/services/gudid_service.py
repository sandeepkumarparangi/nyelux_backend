"""
Production-ready GUDID Cloud Service using Supabase
Handles FDA medical device data with proper error handling and connection management
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import os

from supabase import create_client, Client
from postgrest.exceptions import APIError
import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class GUDIDCloudService:
    """
    Production cloud-based GUDID service using Supabase.
    Provides real-time search of FDA medical devices.
    """
    
    def __init__(self):
        """Initialize Supabase client with production configuration."""
        if not settings.SUPABASE_URL:
            raise ValueError("SUPABASE_URL not configured")
        
        if not settings.SUPABASE_SERVICE_KEY:
            raise ValueError("SUPABASE_SERVICE_KEY not configured")
        
        # Create Supabase client with production settings
        self.supabase: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY
        )
        
        self.table_name = "gudid_devices"
        self.batch_size = 100
        
        logger.info(f"GUDID Cloud Service initialized with Supabase: {settings.SUPABASE_URL[:30]}...")
    
    def search_devices(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Search FDA devices with filters and pagination.
        
        Args:
            query: Search query string
            limit: Number of results to return
            offset: Pagination offset
            filters: Additional filters (device_class, manufacturer, etc.)
            
        Returns:
            Search results with total count
        """
        try:
            # Start with base query
            request = self.supabase.table(self.table_name).select(
                "primary_di, device_name, manufacturer_name, brand_name, "
                "device_class, gmdn_terms, mri_safety, model_number, "
                "sterile, single_use, implantable, life_supporting, rx_required"
            )
            
            # Apply search filter
            if query:
                # Search across multiple fields
                search_filter = (
                    f"device_name.ilike.%{query}%,"
                    f"manufacturer_name.ilike.%{query}%,"
                    f"brand_name.ilike.%{query}%,"
                    f"gmdn_terms.ilike.%{query}%"
                )
                request = request.or_(search_filter)
            
            # Apply additional filters
            if filters:
                if filters.get('device_class'):
                    request = request.eq('device_class', filters['device_class'])
                if filters.get('manufacturer'):
                    request = request.ilike('manufacturer_name', f"%{filters['manufacturer']}%")
                if filters.get('mri_safety'):
                    request = request.eq('mri_safety', filters['mri_safety'])
                if filters.get('sterile') is not None:
                    request = request.eq('sterile', filters['sterile'])
                if filters.get('implantable') is not None:
                    request = request.eq('implantable', filters['implantable'])
            
            # Apply pagination
            request = request.range(offset, offset + limit - 1)
            
            # Execute query
            response = request.execute()
            
            # Get total count (separate query for accurate count)
            count_request = self.supabase.table(self.table_name).select('*', count='exact')
            if query:
                count_request = count_request.or_(search_filter)
            if filters:
                # Apply same filters for count
                if filters.get('device_class'):
                    count_request = count_request.eq('device_class', filters['device_class'])
                if filters.get('manufacturer'):
                    count_request = count_request.ilike('manufacturer_name', f"%{filters['manufacturer']}%")
            
            count_response = count_request.execute()
            total_count = count_response.count if hasattr(count_response, 'count') else len(response.data)
            
            return {
                "results": response.data if response.data else [],
                "total_count": total_count,
                "query": query,
                "limit": limit,
                "offset": offset,
                "filters": filters
            }
            
        except APIError as e:
            logger.error(f"Supabase API error: {str(e)}")
            return {
                "results": [],
                "total_count": 0,
                "query": query,
                "error": "Search service temporarily unavailable"
            }
        except Exception as e:
            logger.error(f"Search error: {str(e)}", exc_info=True)
            return {
                "results": [],
                "total_count": 0,
                "query": query,
                "error": "An error occurred during search"
            }
    
    def typeahead_search(
        self,
        query: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Fast typeahead search for autocomplete.
        
        Args:
            query: Partial search query
            limit: Maximum suggestions to return
            
        Returns:
            Typeahead suggestions
        """
        if len(query) < 2:
            return {"query": query, "suggestions": []}
        
        try:
            # Quick search on device names and manufacturers
            response = self.supabase.table(self.table_name).select(
                "primary_di, device_name, manufacturer_name, device_class"
            ).or_(
                f"device_name.ilike.{query}%,"
                f"manufacturer_name.ilike.{query}%"
            ).limit(limit).execute()
            
            suggestions = []
            seen = set()
            
            for device in response.data if response.data else []:
                # Create suggestion label
                label = f"{device['device_name']} - {device['manufacturer_name']}"
                
                # Avoid duplicates
                if label not in seen:
                    suggestions.append({
                        "id": device['primary_di'],
                        "label": label,
                        "device_name": device['device_name'],
                        "manufacturer": device['manufacturer_name'],
                        "category": device.get('device_class', '')
                    })
                    seen.add(label)
            
            return {
                "query": query,
                "suggestions": suggestions,
                "cached": False
            }
            
        except Exception as e:
            logger.error(f"Typeahead error: {str(e)}")
            return {"query": query, "suggestions": [], "error": str(e)}
    
    def get_device_by_di(self, primary_di: str) -> Optional[Dict[str, Any]]:
        """
        Get complete device details by Device Identifier.
        
        Args:
            primary_di: FDA Device Identifier
            
        Returns:
            Device details or None if not found
        """
        try:
            response = self.supabase.table(self.table_name).select('*').eq(
                'primary_di', primary_di
            ).single().execute()
            
            return response.data if response.data else None
            
        except APIError as e:
            if "0 rows" in str(e):
                logger.info(f"Device not found: {primary_di}")
                return None
            logger.error(f"Get device error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Get device error: {str(e)}", exc_info=True)
            return None
    
    def get_featured_devices(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get featured/popular devices for homepage.
        
        Args:
            limit: Number of devices to return
            
        Returns:
            List of featured devices
        """
        try:
            # Get common device types
            response = self.supabase.table(self.table_name).select(
                "primary_di, device_name, manufacturer_name, device_class, gmdn_terms"
            ).in_(
                'gmdn_terms', 
                ['Infusion pump', 'Ventilator', 'Monitor', 'Defibrillator', 'Scanner']
            ).limit(limit).execute()
            
            return response.data if response.data else []
            
        except Exception as e:
            logger.error(f"Featured devices error: {str(e)}")
            return []
    
    def get_manufacturers(self) -> List[str]:
        """
        Get list of unique manufacturers for filters.
        
        Returns:
            List of manufacturer names
        """
        try:
            # This would be better as a materialized view in Supabase
            response = self.supabase.table(self.table_name).select(
                'manufacturer_name'
            ).limit(1000).execute()
            
            if response.data:
                manufacturers = list(set(
                    d['manufacturer_name'] 
                    for d in response.data 
                    if d.get('manufacturer_name')
                ))
                return sorted(manufacturers)[:100]  # Return top 100
            
            return []
            
        except Exception as e:
            logger.error(f"Get manufacturers error: {str(e)}")
            return []
    
    def health_check(self) -> bool:
        """
        Check if Supabase connection is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Try a simple query
            response = self.supabase.table(self.table_name).select(
                'primary_di'
            ).limit(1).execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False


# Singleton instance
_gudid_service_instance = None


def get_gudid_service() -> GUDIDCloudService:
    """
    Get GUDID service singleton instance.
    
    Returns:
        GUDIDCloudService instance
        
    Raises:
        ValueError: If service cannot be initialized
    """
    global _gudid_service_instance
    
    if _gudid_service_instance is None:
        _gudid_service_instance = GUDIDCloudService()
    
    return _gudid_service_instance
