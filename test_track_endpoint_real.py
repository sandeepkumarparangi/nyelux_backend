#!/usr/bin/env python3
"""
Test what the backend actually expects vs what frontend sends
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("="*60)
print("TESTING TRACK-SEARCH - WHAT IT ACTUALLY ACCEPTS")
print("="*60)

# Test 1: Absolutely minimal - just query
print("\n1. Just 'query' field:")
data = {"query": "test"}
response = requests.post(f"{BASE_URL}/api/v1/public/track-search", json=data)
print(f"   Status: {response.status_code}")
if response.status_code == 200:
    print(f"   ✅ WORKS")
else:
    print(f"   ❌ ERROR: {response.text}")

# Test 2: Check the actual OpenAPI spec to see what's required
print("\n2. Checking what the endpoint ACTUALLY expects:")
response = requests.get(f"{BASE_URL}/docs")
if response.status_code == 200:
    # Access the OpenAPI JSON directly
    openapi_response = requests.get(f"{BASE_URL}/openapi.json")
    if openapi_response.status_code == 200:
        spec = openapi_response.json()
        track_search = spec.get("paths", {}).get("/api/v1/public/track-search", {}).get("post", {})
        if track_search:
            body = track_search.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            print(f"   Schema: {json.dumps(body, indent=2)}")
            
            # Check required fields
            required = body.get("required", [])
            print(f"   REQUIRED FIELDS: {required}")
            
            # Check properties
            properties = body.get("properties", {})
            for prop, details in properties.items():
                print(f"   - {prop}: {details.get('type', 'unknown')} {'(REQUIRED)' if prop in required else '(optional)'}")

# Test 3: Try with empty body
print("\n3. Empty JSON body:")
response = requests.post(f"{BASE_URL}/api/v1/public/track-search", json={})
print(f"   Status: {response.status_code}")
if response.status_code != 200:
    print(f"   Error: {response.text[:200]}")

# Test 4: Try without Content-Type header
print("\n4. Without proper headers:")
response = requests.post(f"{BASE_URL}/api/v1/public/track-search", data='{"query": "test"}')
print(f"   Status: {response.status_code}")

print("\n" + "="*60)
print("DIAGNOSIS:")
print("="*60)
print("\nThe 422 error means the request body doesn't match the schema.")
print("Check if the frontend is sending the request with:")
print("1. Content-Type: application/json header")
print("2. Proper JSON body with 'query' field")
print("3. No extra unexpected fields")
