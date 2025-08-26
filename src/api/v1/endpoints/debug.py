"""
Debug endpoint to test Supabase connection
"""
from fastapi import APIRouter, HTTPException
from supabase import create_client, Client
from src.core.config import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/test-supabase")
async def test_supabase_connection():
    """
    Test Supabase connection and return diagnostic info
    """
    result = {
        "url_configured": bool(settings.SUPABASE_URL),
        "anon_key_configured": bool(settings.SUPABASE_ANON_KEY),
        "service_key_configured": bool(settings.SUPABASE_SERVICE_KEY),
        "connection_test": "not_tested",
        "device_count": 0,
        "sample_device": None,
        "error": None
    }
    
    try:
        # Try with service key first
        if settings.SUPABASE_SERVICE_KEY:
            logger.info("Testing with service key...")
            supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        else:
            logger.info("Testing with anon key...")
            supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        
        # Try to get a device
        response = supabase.table('gudid_devices').select('*').limit(1).execute()
        
        if response.data:
            result["connection_test"] = "success"
            result["sample_device"] = response.data[0]
            
            # Try to count
            count_response = supabase.table('gudid_devices').select('*', count='exact', head=True).execute()
            result["device_count"] = count_response.count
        else:
            result["connection_test"] = "no_data"
            
    except Exception as e:
        result["connection_test"] = "failed"
        result["error"] = str(e)
        logger.error(f"Supabase test failed: {e}")
    
    return result

@router.get("/test-search")
async def test_search():
    """
    Test search functionality
    """
    try:
        # Use service key
        supabase = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_ANON_KEY
        )
        
        # Search for "pump"
        response = supabase.table('gudid_devices').select(
            'primary_di, device_name, manufacturer_name'
        ).ilike('device_name', '%pump%').limit(5).execute()
        
        return {
            "success": True,
            "results_count": len(response.data) if response.data else 0,
            "results": response.data if response.data else []
        }
        
    except Exception as e:
        logger.error(f"Search test failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
