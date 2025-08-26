"""
GUDID Cloud Service - FIXED VERSION with proxy patch
"""
import os
import logging
from typing import Dict, List, Optional, Any

# Remove proxy environment variables
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY']:
    os.environ.pop(proxy_var, None)

# Apply monkey patch BEFORE importing supabase
import httpx
original_init = httpx.Client.__init__
def patched_init(self, *args, **kwargs):
    kwargs.pop('proxy', None)
    kwargs.pop('proxies', None)
    original_init(self, *args, **kwargs)
httpx.Client.__init__ = patched_init

# Now import supabase
from supabase import create_client
from src.core.config import settings

logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase_client = None
try:
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        supabase_client = create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_KEY
        )
        logger.info("✅ Supabase connected successfully!")
except Exception as e:
    logger.error(f"Failed to connect to Supabase: {e}")

class GUDIDCloudService:
    """GUDID service using Supabase"""
    
    def __init__(self):
        self.supabase = supabase_client
        if not self.supabase:
            logger.error("Supabase not connected - public search will not work")
    
    def smart_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search GUDID devices in Supabase"""
        if not self.supabase:
            return []
        
        try:
            response = self.supabase.table('gudid_devices').select(
                'primary_di, device_name, manufacturer_name, brand_name, device_class, gmdn_terms, mri_safety'
            ).or_(
                f"device_name.ilike.%{query}%,"
                f"manufacturer_name.ilike.%{query}%,"
                f"brand_name.ilike.%{query}%"
            ).limit(limit).execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def get_device_details(self, primary_di: str) -> Optional[Dict[str, Any]]:
        """Get device details from Supabase"""
        if not self.supabase:
            return None
        
        try:
            response = self.supabase.table('gudid_devices').select('*').eq(
                'primary_di', primary_di
            ).single().execute()
            
            return response.data if response.data else None
        except Exception as e:
            logger.error(f"Get device error: {e}")
            return None

class DeviceSearchService:
    """Search service using Supabase"""
    
    def __init__(self):
        self.cloud_service = GUDIDCloudService()
    
    def typeahead_search(self, query: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Typeahead search"""
        if len(query) < 2:
            return {'suggestions': [], 'query': query}
        
        try:
            suggestions = self.cloud_service.smart_search(query, limit=10)
            
            return {
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
        except Exception as e:
            logger.error(f"Typeahead error: {e}")
            return {'suggestions': [], 'query': query}
