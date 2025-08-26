#!/usr/bin/env python3
"""
Fix Supabase proxy issue and test connection
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Remove ALL proxy settings before any imports
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy']:
    if proxy_var in os.environ:
        print(f"Removing {proxy_var} from environment")
        del os.environ[proxy_var]

def check_supabase_version():
    """Check which version of supabase is installed"""
    print("Checking Supabase library version...")
    try:
        import supabase
        print(f"Supabase version: {supabase.__version__ if hasattr(supabase, '__version__') else 'Unknown'}")
        
        import gotrue
        print(f"GoTrue version: {gotrue.__version__ if hasattr(gotrue, '__version__') else 'Unknown'}")
        
        import httpx
        print(f"HTTPX version: {httpx.__version__}")
        
    except ImportError as e:
        print(f"Import error: {e}")

def monkey_patch_httpx():
    """Monkey patch httpx Client to remove proxy parameter"""
    print("\nApplying monkey patch to fix proxy issue...")
    
    import httpx
    
    # Store original init
    original_init = httpx.Client.__init__
    
    # Create wrapper that removes proxy parameter
    def patched_init(self, *args, **kwargs):
        # Remove proxy parameter if it exists
        kwargs.pop('proxy', None)
        kwargs.pop('proxies', None)
        # Call original with cleaned kwargs
        original_init(self, *args, **kwargs)
    
    # Apply patch
    httpx.Client.__init__ = patched_init
    print("✓ Monkey patch applied")

def test_supabase_with_patch():
    """Test Supabase connection with the patch"""
    print("\n" + "="*60)
    print("TESTING SUPABASE WITH PATCH")
    print("="*60)
    
    try:
        # Apply the patch BEFORE importing supabase
        monkey_patch_httpx()
        
        # Now import supabase
        from supabase import create_client
        
        print("\n1. Creating Supabase client (with patch)...")
        
        # Your Supabase credentials
        SUPABASE_URL = 'https://zjpdsedtsuypcovchyyj.supabase.co'
        SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpqcGRzZWR0c3V5cGNvdmNoeXlqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NDYyMDgwNywiZXhwIjoyMDcwMTk2ODA3fQ.qGkqWitjlLEONuh0nBqZVSKh3wn0Ij8YlTFmUTMDL-Y'
        
        # Create client
        supabase = create_client(
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_KEY
        )
        print("   ✅ Client created successfully!")
        
        print("\n2. Testing GUDID table...")
        # Try to get devices
        response = supabase.table('gudid_devices').select(
            'primary_di, device_name, manufacturer_name, device_class'
        ).limit(5).execute()
        
        if response.data:
            print(f"   ✅ SUCCESS! Found {len(response.data)} devices in Supabase!")
            print("\n   Sample FDA GUDID devices from your Supabase:")
            for i, device in enumerate(response.data[:3], 1):
                print(f"\n   Device {i}:")
                print(f"   Name: {device.get('device_name', 'N/A')}")
                print(f"   Manufacturer: {device.get('manufacturer_name', 'N/A')}")
                print(f"   FDA Class: {device.get('device_class', 'N/A')}")
        else:
            print("   ⚠️  Table exists but appears to be empty")
            print("   You need to populate gudid_devices with FDA data")
            
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_fixed_service_file():
    """Create a fixed version of the service that applies the patch"""
    print("\n" + "="*60)
    print("CREATING FIXED SERVICE FILE")
    print("="*60)
    
    fixed_code = '''"""
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
'''
    
    # Write the fixed file
    with open('src/services/gudid_cloud_service_fixed.py', 'w') as f:
        f.write(fixed_code)
    
    print("✓ Created gudid_cloud_service_fixed.py")
    
    # Also create a patch file that can be imported
    patch_code = '''"""
Monkey patch for httpx proxy issue in Supabase
Import this BEFORE importing supabase
"""
import os
import httpx

# Remove proxy environment variables
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY']:
    os.environ.pop(proxy_var, None)

# Patch httpx.Client to remove proxy parameter
original_init = httpx.Client.__init__

def patched_init(self, *args, **kwargs):
    kwargs.pop('proxy', None)
    kwargs.pop('proxies', None)
    original_init(self, *args, **kwargs)

httpx.Client.__init__ = patched_init

print("✓ Supabase proxy patch applied")
'''
    
    with open('src/core/supabase_patch.py', 'w') as f:
        f.write(patch_code)
    
    print("✓ Created supabase_patch.py")
    print("\nTo use the fix, add this to the top of src/main.py:")
    print("from src.core.supabase_patch import *  # Fix Supabase proxy issue")

def main():
    print("\n" + "="*60)
    print("SUPABASE PROXY FIX")
    print("="*60)
    
    # Check versions
    check_supabase_version()
    
    # Test with patch
    if test_supabase_with_patch():
        print("\n✅ PATCH WORKS! Supabase can connect!")
        
        # Create fixed files
        create_fixed_service_file()
        
        print("\n" + "="*60)
        print("NEXT STEPS:")
        print("="*60)
        print("1. The patch works! Your Supabase can connect.")
        print("2. Use the fixed service file: gudid_cloud_service_fixed.py")
        print("3. Or add the patch import to src/main.py")
        print("4. Restart the server to apply the fix")
    else:
        print("\n❌ Even with patch, connection failed")
        print("You may need to update the Supabase library:")
        print("pip install --upgrade supabase")

if __name__ == "__main__":
    main()
