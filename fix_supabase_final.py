#!/usr/bin/env python3
"""
Fix Supabase proxy issue by patching httpx BEFORE any imports
"""
import sys
import os

# Remove ALL proxy environment variables FIRST
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy']:
    os.environ.pop(proxy_var, None)

print("Step 1: Checking installed packages...")
import subprocess
result = subprocess.run(['pip', 'list', '|', 'grep', '-E', 'supabase|httpx|gotrue'], 
                       shell=True, capture_output=True, text=True)
print(result.stdout)

print("\nStep 2: Trying to patch httpx BEFORE any imports...")

# Monkey patch httpx.Client BEFORE importing supabase
import httpx

# Save original Client class
OriginalClient = httpx.Client

# Create patched Client class
class PatchedClient(OriginalClient):
    def __init__(self, *args, **kwargs):
        # Remove proxy-related kwargs that cause issues
        kwargs.pop('proxy', None)
        kwargs.pop('proxies', None)
        kwargs.pop('mounts', None)
        # Call original with cleaned kwargs
        super().__init__(*args, **kwargs)

# Replace httpx.Client with our patched version
httpx.Client = PatchedClient
print("✓ httpx.Client patched")

# Also patch AsyncClient just in case
OriginalAsyncClient = httpx.AsyncClient

class PatchedAsyncClient(OriginalAsyncClient):
    def __init__(self, *args, **kwargs):
        kwargs.pop('proxy', None)
        kwargs.pop('proxies', None)
        kwargs.pop('mounts', None)
        super().__init__(*args, **kwargs)

httpx.AsyncClient = PatchedAsyncClient
print("✓ httpx.AsyncClient patched")

print("\nStep 3: NOW importing supabase (after patch)...")
try:
    from supabase import create_client
    print("✓ Supabase imported successfully")
    
    print("\nStep 4: Creating Supabase client...")
    SUPABASE_URL = 'https://zjpdsedtsuypcovchyyj.supabase.co'
    SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpqcGRzZWR0c3V5cGNvdmNoeXlqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NDYyMDgwNywiZXhwIjoyMDcwMTk2ODA3fQ.qGkqWitjlLEONuh0nBqZVSKh3wn0Ij8YlTFmUTMDL-Y'
    
    supabase = create_client(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY
    )
    print("✅ SUCCESS! Supabase client created!")
    
    print("\nStep 5: Testing GUDID table access...")
    response = supabase.table('gudid_devices').select('*').limit(5).execute()
    
    if response.data:
        print(f"✅ Found {len(response.data)} devices in Supabase!")
        for device in response.data[:2]:
            print(f"  - {device.get('device_name', 'N/A')} by {device.get('manufacturer_name', 'N/A')}")
    else:
        print("⚠️ Table exists but is empty - need to populate with FDA data")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("CREATING STARTUP PATCH FILE")
print("="*60)

# Create a patch file that can be imported at startup
patch_code = '''"""
Supabase httpx proxy patch - Import this FIRST in main.py
"""
import os
import httpx

# Remove proxy environment variables
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(proxy_var, None)

# Patch httpx.Client to remove proxy parameter
_OriginalClient = httpx.Client
class PatchedClient(_OriginalClient):
    def __init__(self, *args, **kwargs):
        kwargs.pop('proxy', None)
        kwargs.pop('proxies', None)
        kwargs.pop('mounts', None)
        super().__init__(*args, **kwargs)
httpx.Client = PatchedClient

_OriginalAsyncClient = httpx.AsyncClient
class PatchedAsyncClient(_OriginalAsyncClient):
    def __init__(self, *args, **kwargs):
        kwargs.pop('proxy', None)
        kwargs.pop('proxies', None)
        kwargs.pop('mounts', None)
        super().__init__(*args, **kwargs)
httpx.AsyncClient = PatchedAsyncClient

print("✓ Supabase proxy patch applied")
'''

with open('src/core/httpx_patch.py', 'w') as f:
    f.write(patch_code)
print("✓ Created src/core/httpx_patch.py")

print("\nTo fix Supabase permanently, add this to the TOP of src/main.py:")
print("from src.core.httpx_patch import *  # Must be FIRST import")
