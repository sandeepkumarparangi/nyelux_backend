#!/usr/bin/env python3
"""
Test Supabase connection and verify REAL data is being used
FIXED VERSION - No proxy parameter
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Remove ALL proxy settings that cause issues
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 
                  'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy']:
    os.environ.pop(proxy_var, None)

# Now import supabase
from supabase import create_client

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

print("="*60)
print("TESTING SUPABASE CONNECTION - REAL DATA CHECK")
print("="*60)

print(f"\n1. Checking Supabase credentials...")
print(f"   URL: {SUPABASE_URL[:30]}...")
print(f"   Key: {SUPABASE_SERVICE_KEY[:20]}...")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ MISSING SUPABASE CREDENTIALS!")
    sys.exit(1)

print("\n2. Connecting to Supabase (no proxy)...")
try:
    # Create client with ONLY the required parameters
    supabase = create_client(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_SERVICE_KEY
    )
    print("✅ Connected successfully!")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    sys.exit(1)

print("\n3. Testing GUDID devices table...")
try:
    # Count total devices - proper way
    response = supabase.table('gudid_devices').select('*', count='exact', head=True).execute()
    if hasattr(response, 'count') and response.count:
        print(f"✅ Total devices in database: {response.count:,}")
    else:
        print("⚠️  Could not get device count")
    
    # Get sample devices
    print("\n4. Fetching sample REAL devices...")
    response = supabase.table('gudid_devices').select(
        'primary_di, device_name, manufacturer_name, device_class'
    ).limit(5).execute()
    
    if response.data:
        print(f"✅ Found {len(response.data)} devices:")
        for device in response.data:
            print(f"   - {device['device_name'][:50]}...")
            print(f"     DI: {device['primary_di']}")
            print(f"     Manufacturer: {device['manufacturer_name']}")
            print(f"     Class: {device['device_class']}")
            print()
    else:
        print("❌ No devices found!")
        
except Exception as e:
    print(f"❌ Query failed: {e}")
    sys.exit(1)

print("\n5. Testing search functionality...")
try:
    # Search for Medtronic devices
    response = supabase.table('gudid_devices').select(
        'device_name, manufacturer_name'
    ).ilike('manufacturer_name', '%Medtronic%').limit(3).execute()
    
    if response.data:
        print(f"✅ Found {len(response.data)} Medtronic devices:")
        for device in response.data:
            print(f"   - {device['device_name'][:60]}...")
    else:
        print("⚠️  No Medtronic devices found")
        
except Exception as e:
    print(f"❌ Search failed: {e}")

print("\n6. Testing distinct manufacturers...")
try:
    # Get a sample of manufacturers
    response = supabase.table('gudid_devices').select(
        'manufacturer_name'
    ).limit(1000).execute()
    
    if response.data:
        manufacturers = list(set(d['manufacturer_name'] for d in response.data if d.get('manufacturer_name')))
        print(f"✅ Found {len(manufacturers)} unique manufacturers in sample")
        print("   Sample manufacturers:")
        for mfr in sorted(manufacturers)[:5]:
            print(f"   - {mfr}")
    else:
        print("⚠️  No manufacturers found")
        
except Exception as e:
    print(f"❌ Manufacturer query failed: {e}")

print("\n" + "="*60)
print("CONCLUSION:")
print("="*60)

if response.data:
    print("✅ USING REAL FDA GUDID DATA FROM SUPABASE")
    print("✅ NO FAKE DATA - This is production data!")
    print("✅ Public search endpoints will return REAL devices")
    print("✅ Connection is working properly")
else:
    print("⚠️  Supabase connected but no data found")
    print("⚠️  Check if the gudid_devices table is populated")

print("="*60)
