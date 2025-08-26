#!/usr/bin/env python3
"""
Test Supabase connection for public GUDID data - FIXED VERSION
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Remove ALL proxy settings that cause the error
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(proxy_var, None)

def test_supabase_direct():
    """Test Supabase connection directly - FIXED"""
    print("="*60)
    print("TESTING SUPABASE CONNECTION (FIXED)")
    print("="*60)
    
    try:
        from supabase import create_client
        
        print("\n1. Creating Supabase client (without proxy parameter)...")
        
        # Your Supabase credentials
        SUPABASE_URL = 'https://zjpdsedtsuypcovchyyj.supabase.co'
        SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpqcGRzZWR0c3V5cGNvdmNoeXlqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NDYyMDgwNywiZXhwIjoyMDcwMTk2ODA3fQ.qGkqWitjlLEONuh0nBqZVSKh3wn0Ij8YlTFmUTMDL-Y'
        
        # Create client WITHOUT proxy parameter
        supabase = create_client(
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_KEY
        )
        print("   ✅ Client created successfully!")
        
        print("\n2. Testing GUDID table access...")
        # Try to get a few devices
        response = supabase.table('gudid_devices').select(
            'primary_di, device_name, manufacturer_name, device_class'
        ).limit(5).execute()
        
        if response.data:
            print(f"   ✅ Found {len(response.data)} devices in Supabase!")
            print("\n   Sample FDA GUDID devices:")
            for i, device in enumerate(response.data, 1):
                print(f"   {i}. {device.get('device_name', 'N/A')}")
                print(f"      Manufacturer: {device.get('manufacturer_name', 'N/A')}")
                print(f"      FDA Class: {device.get('device_class', 'N/A')}")
                print(f"      DI: {device.get('primary_di', 'N/A')}")
                print()
        else:
            print("   ⚠️  No devices found. The gudid_devices table might be empty.")
            print("   You need to populate it with FDA GUDID data.")
            
        print("3. Testing search for 'pump' devices...")
        search_response = supabase.table('gudid_devices').select(
            'device_name, manufacturer_name'
        ).ilike('device_name', '%pump%').limit(3).execute()
        
        if search_response.data:
            print(f"   ✅ Found {len(search_response.data)} pump devices")
            for device in search_response.data:
                print(f"   - {device.get('device_name', 'N/A')}")
        else:
            print("   ⚠️  No pump devices found")
            
        print("\n4. Checking total device count...")
        # Get count
        count_response = supabase.table('gudid_devices').select(
            'primary_di', count='exact'
        ).limit(1).execute()
        
        if hasattr(count_response, 'count'):
            print(f"   ✅ Total devices in Supabase: {count_response.count:,}")
            if count_response.count > 1000000:
                print("   🎉 You have the full FDA GUDID database!")
        
        return True
        
    except ImportError as e:
        print(f"\n❌ Supabase library issue: {e}")
        print("   Run: pip install supabase")
        return False
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_service_with_fix():
    """Test the fixed GUDID service"""
    print("\n" + "="*60)
    print("TESTING FIXED GUDID SERVICE")
    print("="*60)
    
    # Force reload the module to get our fixes
    import importlib
    import sys
    
    # Remove old module if loaded
    if 'src.services.gudid_cloud_service' in sys.modules:
        del sys.modules['src.services.gudid_cloud_service']
    
    try:
        from src.services.gudid_cloud_service import GUDIDCloudService
        
        print("\n1. Initializing GUDID Service...")
        service = GUDIDCloudService()
        
        if service.supabase:
            print("   ✅ Service connected to Supabase!")
            
            print("\n2. Testing real search...")
            results = service.smart_search("medtronic", limit=3)
            
            if results:
                print(f"   ✅ Found {len(results)} Medtronic devices")
                for device in results:
                    print(f"   - {device.get('device_name', 'N/A')}")
            else:
                print("   ⚠️  No results. Check if Supabase has data.")
        else:
            print("   ❌ Service failed to connect to Supabase")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("\n" + "="*60)
    print("NYELUX - SUPABASE CONNECTION TEST (FIXED)")
    print("="*60)
    
    # Test direct connection
    if test_supabase_direct():
        print("\n✅ SUPABASE CONNECTION WORKS!")
        
        # Test service
        test_service_with_fix()
    else:
        print("\n❌ Could not connect to Supabase")
        print("\nTroubleshooting:")
        print("1. Check internet connection")
        print("2. Verify Supabase URL and key are correct")
        print("3. Make sure gudid_devices table exists in Supabase")

if __name__ == "__main__":
    main()
