#!/usr/bin/env python3
"""
Test Supabase connection for public GUDID data
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Set environment variables before importing anything
os.environ['SUPABASE_URL'] = 'https://zjpdsedtsuypcovchyyj.supabase.co'
os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpqcGRzZWR0c3V5cGNvdmNoeXlqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NDYyMDgwNywiZXhwIjoyMDcwMTk2ODA3fQ.qGkqWitjlLEONuh0nBqZVSKh3wn0Ij8YlTFmUTMDL-Y'

# Remove any proxy settings that might interfere
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(proxy_var, None)

def test_supabase_direct():
    """Test Supabase connection directly"""
    print("="*60)
    print("TESTING SUPABASE CONNECTION FOR GUDID DATA")
    print("="*60)
    
    try:
        from supabase import create_client, Client
        
        print("\n1. Creating Supabase client...")
        supabase = create_client(
            os.environ['SUPABASE_URL'],
            os.environ['SUPABASE_SERVICE_KEY']
        )
        print("   ✓ Client created successfully")
        
        print("\n2. Testing GUDID table access...")
        # Try to get a few devices
        response = supabase.table('gudid_devices').select(
            'primary_di, device_name, manufacturer_name, device_class'
        ).limit(5).execute()
        
        if response.data:
            print(f"   ✓ Found {len(response.data)} devices in Supabase")
            print("\n   Sample devices:")
            for device in response.data[:3]:
                print(f"   - {device.get('device_name', 'N/A')} by {device.get('manufacturer_name', 'N/A')}")
        else:
            print("   ⚠️  No devices found in Supabase GUDID table")
            print("   This might mean the table is empty or not accessible")
            
        print("\n3. Testing search functionality...")
        # Search for common medical device terms
        search_response = supabase.table('gudid_devices').select(
            'primary_di, device_name, manufacturer_name'
        ).ilike('device_name', '%pump%').limit(3).execute()
        
        if search_response.data:
            print(f"   ✓ Search found {len(search_response.data)} devices with 'pump'")
        else:
            print("   ⚠️  No devices found with search term 'pump'")
            
        print("\n4. Checking table structure...")
        # Get one record to see all fields
        structure_response = supabase.table('gudid_devices').select('*').limit(1).execute()
        
        if structure_response.data and len(structure_response.data) > 0:
            fields = list(structure_response.data[0].keys())
            print(f"   ✓ Table has {len(fields)} fields:")
            for field in fields[:10]:  # Show first 10 fields
                print(f"     - {field}")
            if len(fields) > 10:
                print(f"     ... and {len(fields) - 10} more fields")
        
        return True
        
    except ImportError as e:
        print(f"\n❌ Supabase library not installed properly: {e}")
        print("   Run: pip install supabase")
        return False
        
    except Exception as e:
        print(f"\n❌ Error connecting to Supabase: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False

def test_gudid_service():
    """Test the GUDID service that the app uses"""
    print("\n" + "="*60)
    print("TESTING GUDID SERVICE INTEGRATION")
    print("="*60)
    
    try:
        from src.services.gudid_cloud_service import GUDIDCloudService
        
        print("\n1. Initializing GUDID Cloud Service...")
        service = GUDIDCloudService()
        
        if service.supabase:
            print("   ✓ Service connected to Supabase")
        else:
            print("   ❌ Service NOT connected to Supabase (using mock data)")
            
        print("\n2. Testing smart_search...")
        results = service.smart_search("infusion", limit=5)
        
        if results:
            print(f"   ✓ Search returned {len(results)} results")
            if results and len(results) > 0:
                first = results[0]
                if first.get('primary_di') == '00889842001234':
                    print("   ⚠️  WARNING: Returning MOCK data, not real Supabase data!")
                else:
                    print(f"   ✓ Returning REAL data from Supabase")
                    print(f"   First result: {first.get('device_name', 'N/A')}")
        else:
            print("   ❌ No results returned")
            
        print("\n3. Testing get_device_details...")
        # Try with mock DI first
        device = service.get_device_details('00889842001234')
        if device:
            if device.get('device_name') == 'Infusion Pump Model X200':
                print("   ⚠️  Returning MOCK device data")
            else:
                print("   ✓ Returning REAL device data")
                
    except Exception as e:
        print(f"\n❌ Error testing GUDID service: {e}")

def main():
    print("\n" + "="*60)
    print("NYELUX - SUPABASE GUDID CONNECTION TEST")
    print("="*60)
    print("\nYour architecture:")
    print("- Supabase: 4.8M+ FDA GUDID devices (PUBLIC data)")
    print("- Local PostgreSQL: Users, auth, analytics (PRIVATE data)")
    print("- Link: gudid_primary_di field")
    
    # Test direct connection
    if test_supabase_direct():
        print("\n✅ SUPABASE CONNECTION SUCCESSFUL!")
    else:
        print("\n❌ SUPABASE CONNECTION FAILED!")
        
    # Test service integration
    test_gudid_service()
    
    print("\n" + "="*60)
    print("DIAGNOSIS COMPLETE")
    print("="*60)
    
    print("\nIf Supabase is not connecting:")
    print("1. Check your SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
    print("2. Make sure the 'gudid_devices' table exists in Supabase")
    print("3. Verify network connectivity to Supabase")
    print("4. Check if the table has data: SELECT COUNT(*) FROM gudid_devices;")

if __name__ == "__main__":
    main()
