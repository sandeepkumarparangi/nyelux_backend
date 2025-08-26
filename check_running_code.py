#!/usr/bin/env python3
"""
Verify which code is actually running
"""
import requests
import subprocess
import time

print("="*60)
print("CHECKING WHICH CODE IS RUNNING")
print("="*60)

# 1. Check if server is running
print("\n1. Checking if server is running...")
try:
    response = requests.get("http://localhost:8000/health")
    print(f"   ✓ Server is running: {response.json()}")
except:
    print("   ✗ Server is NOT running")
    print("\n   Starting server...")
    subprocess.Popen(["python", "-m", "uvicorn", "src.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"])
    time.sleep(5)

# 2. Check the OpenAPI spec
print("\n2. Checking OpenAPI spec for track-search...")
try:
    response = requests.get("http://localhost:8000/openapi.json")
    if response.status_code == 200:
        spec = response.json()
        track_search = spec.get("paths", {}).get("/api/v1/public/track-search", {})
        if track_search:
            post = track_search.get("post", {})
            request_body = post.get("requestBody", {})
            
            # Check if it's using Pydantic or raw Request
            if "TrackSearchRequest" in str(request_body):
                print("   ✗ Still using Pydantic TrackSearchRequest schema")
                print("   The old code is still running!")
            elif "content" in request_body:
                schema = request_body.get("content", {}).get("application/json", {}).get("schema", {})
                print(f"   Schema type: {schema}")
            else:
                print("   ✓ Using raw Request object (no strict schema)")
        else:
            print("   ✗ track-search endpoint not found")
except Exception as e:
    print(f"   Error: {e}")

# 3. Test the actual endpoint
print("\n3. Testing the actual endpoint...")
test_data = {"query": "test", "extra_field": "should_not_cause_error"}
response = requests.post("http://localhost:8000/api/v1/public/track-search", json=test_data)
print(f"   Status: {response.status_code}")
if response.status_code == 200:
    print(f"   ✓ SUCCESS: {response.json()}")
else:
    print(f"   ✗ FAILED: {response.text[:200]}")

# 4. Check which file is being used
print("\n4. Checking which public.py is loaded...")
import sys
import os
sys.path.insert(0, '/Users/nehamchangappa/Downloads/Nyelux Beta/nyelux-backend-beta')

try:
    from src.api.v1.endpoints import public
    print(f"   Module location: {public.__file__}")
    
    # Check if the module has our fix
    import inspect
    source = inspect.getsource(public.track_search_event)
    if "request: Request" in source and "await request.body()" in source:
        print("   ✓ The FIXED version is loaded (uses raw Request)")
    else:
        print("   ✗ The OLD version is loaded (uses Pydantic)")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "="*60)
print("SOLUTION:")
print("="*60)
print("If the old code is still running:")
print("1. Kill all Python processes: pkill -f python")
print("2. Clear module cache: find . -name '*.pyc' -delete")
print("3. Restart with: python -m uvicorn src.main:app --reload")
