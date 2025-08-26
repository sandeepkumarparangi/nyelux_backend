"""
GUDID Cloud Sync Service using Supabase
PRODUCTION VERSION - Real connection to Supabase for 4.8M+ FDA devices
NO PROXY SUPPORT - Direct connection only
"""
import asyncio
import aiohttp
import csv
import io
import os
import tempfile
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, AsyncGenerator
from pathlib import Path

import httpx

from src.core.config import settings
from src.core.redis_manager import RedisManager

logger = logging.getLogger(__name__)
redis_manager = RedisManager()

# Initialize Supabase client for GUDID data
supabase_client = None
try:
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        # Remove ALL proxy environment variables to avoid issues
        for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 
                         'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy']:
            os.environ.pop(proxy_var, None)
        
        from supabase import create_client, Client
        
        # Create client with ONLY the required parameters - NO proxy
        supabase_client = create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_KEY
        )
        logger.info("✅ Supabase client initialized successfully for GUDID service")
        
except ImportError as e:
    logger.error(f"Supabase library not installed: {e}")
    logger.error("Run: pip install supabase")
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    logger.error("Check SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")


class GUDIDCloudService:
    """
    Cloud-based GUDID service using Supabase.
    Provides access to 4.8M+ FDA medical devices.
    """
    
    def __init__(self):
        if not supabase_client:
            logger.error("❌ GUDIDCloudService failed - Supabase not connected!")
            logger.error("Public search will not work without Supabase connection")
        else:
            logger.info("✅ GUDIDCloudService ready with Supabase connection")
        
        self.supabase = supabase_client
        self.batch_size = 100
        
    def smart_search(
        self, 
        query: str, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Smart search across GUDID devices in Supabase.
        Searches device names, manufacturers, and brand names.
        """
        if not self.supabase:
            logger.error("Cannot search - Supabase not connected")
            # Return empty list instead of mock data for production
            return []
        
        try:
            # Search across multiple fields for best results
            response = self.supabase.table('gudid_devices').select(
                'primary_di, device_name, manufacturer_name, brand_name, device_class, '
                'device_class_name, gmdn_terms, mri_safety, model_number, catalog_number, '
                'device_description, sterile, single_use, implantable, life_supporting, '
                'rx_required, otc, device_size_text, product_code, regulation_number'
            ).or_(
                f"device_name.ilike.%{query}%,"
                f"manufacturer_name.ilike.%{query}%,"
                f"brand_name.ilike.%{query}%"
            ).limit(limit).execute()
            
            if response.data:
                logger.info(f"Found {len(response.data)} devices for query: {query}")
                return response.data
            else:
                logger.info(f"No devices found for query: {query}")
                return []
                
        except Exception as e:
            logger.error(f"Supabase search error: {e}")
            return []
    
    def get_device_details(self, primary_di: str) -> Optional[Dict[str, Any]]:
        """Get full device details from Supabase by primary DI."""
        if not self.supabase:
            logger.error("Cannot get device - Supabase not connected")
            return None
        
        try:
            response = self.supabase.table('gudid_devices').select('*').eq(
                'primary_di', primary_di
            ).single().execute()
            
            if response.data:
                logger.info(f"Found device details for DI: {primary_di}")
                return response.data
            else:
                logger.info(f"No device found for DI: {primary_di}")
                return None
                
        except Exception as e:
            logger.error(f"Get device details error: {e}")
            return None
    
    def search_by_manufacturer(
        self,
        manufacturer: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search devices by manufacturer name."""
        if not self.supabase:
            return []
        
        try:
            response = self.supabase.table('gudid_devices').select(
                'primary_di, device_name, manufacturer_name, brand_name, device_class'
            ).ilike(
                'manufacturer_name', f'%{manufacturer}%'
            ).limit(limit).execute()
            
            return response.data if response.data else []
            
        except Exception as e:
            logger.error(f"Manufacturer search error: {e}")
            return []
    
    def search_by_class(
        self,
        device_class: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search devices by FDA class (I, II, or III)."""
        if not self.supabase:
            return []
        
        try:
            response = self.supabase.table('gudid_devices').select(
                'primary_di, device_name, manufacturer_name, device_class'
            ).eq(
                'device_class', device_class
            ).limit(limit).execute()
            
            return response.data if response.data else []
            
        except Exception as e:
            logger.error(f"Class search error: {e}")
            return []
    
    def get_device_count(self) -> int:
        """Get total count of devices in Supabase."""
        if not self.supabase:
            return 0
        
        try:
            # Use count functionality - proper way to get count
            response = self.supabase.table('gudid_devices').select(
                '*', count='exact', head=True
            ).execute()
            
            # The count is in the response
            return response.count if hasattr(response, 'count') and response.count else 0
            
        except Exception as e:
            logger.error(f"Count error: {e}")
            return 0
    
    def get_distinct_manufacturers(self, limit: int = 100) -> List[str]:
        """Get list of distinct manufacturers from Supabase."""
        if not self.supabase:
            return []
        
        try:
            # Get a sample of devices to extract manufacturers
            response = self.supabase.table('gudid_devices').select(
                'manufacturer_name'
            ).limit(5000).execute()
            
            if response.data:
                # Extract unique manufacturer names
                manufacturers = list(set(
                    d.get('manufacturer_name', '') 
                    for d in response.data 
                    if d.get('manufacturer_name')
                ))
                return sorted(manufacturers)[:limit]
            else:
                return []
                
        except Exception as e:
            logger.error(f"Get manufacturers error: {e}")
            return []
    
    async def sync_to_cloud(self, sync_type: str = "weekly") -> Dict[str, Any]:
        """
        Sync FDA GUDID data to Supabase.
        This would be run periodically to update the database.
        """
        if not self.supabase:
            return {
                'sync_type': sync_type,
                'status': 'failed',
                'reason': 'Supabase not connected',
                'devices_processed': 0
            }
        
        # TODO: Implement actual FDA data download and sync
        # This would download from FDA and update Supabase
        return {
            'sync_type': sync_type,
            'status': 'not_implemented',
            'devices_processed': 0
        }


class DeviceSearchService:
    """
    Production search service with typeahead.
    Uses Supabase for real FDA GUDID data.
    """
    
    def __init__(self):
        self.cloud_service = GUDIDCloudService()
        self.cache_ttl = 300  # 5 minutes
        
        if not self.cloud_service.supabase:
            logger.error("❌ DeviceSearchService: No Supabase connection!")
    
    def typeahead_search(
        self,
        query: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Real-time typeahead search as user types.
        Returns suggestions from Supabase GUDID data.
        """
        # Minimum 2 characters for search
        if len(query) < 2:
            return {'suggestions': [], 'query': query}
        
        try:
            # Search in Supabase
            suggestions = self.cloud_service.smart_search(query, limit=10)
            
            # Format for frontend autocomplete
            result = {
                'query': query,
                'suggestions': [
                    {
                        'id': s.get('primary_di', ''),
                        'label': f"{s.get('device_name', '')} - {s.get('manufacturer_name', '')}",
                        'device_name': s.get('device_name', ''),
                        'manufacturer': s.get('manufacturer_name', ''),
                        'category': s.get('device_class', '')
                    }
                    for s in suggestions
                ],
                'cached': False
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Typeahead search error: {e}")
            return {'suggestions': [], 'query': query, 'error': str(e)}
    
    def full_search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Full search with filters and pagination.
        """
        try:
            # Get results from Supabase
            devices = self.cloud_service.smart_search(query, limit=limit)
            
            # Apply filters if provided
            if filters:
                # TODO: Implement filter logic
                pass
            
            return {
                'results': devices,
                'total': len(devices),
                'query': query,
                'limit': limit,
                'offset': offset
            }
            
        except Exception as e:
            logger.error(f"Full search error: {e}")
            return {
                'results': [],
                'total': 0,
                'query': query,
                'error': str(e)
            }


# Create singleton instances for use across the app
gudid_service = GUDIDCloudService()
search_service = DeviceSearchService()

# Log initialization status
if supabase_client:
    logger.info("="*60)
    logger.info("GUDID CLOUD SERVICE INITIALIZED SUCCESSFULLY")
    logger.info("Connected to Supabase for FDA GUDID data")
    logger.info("="*60)
else:
    logger.error("="*60)
    logger.error("GUDID CLOUD SERVICE FAILED TO INITIALIZE")
    logger.error("Public search will not work!")
    logger.error("Check your Supabase configuration")
    logger.error("="*60)
