#!/usr/bin/env python3
"""
Debug what's actually being sent to track-search endpoint
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_track_search_detailed():
    """Test with different payload formats to find what works"""
    
    print("="*60)
    print("DEBUGGING TRACK-SEARCH ENDPOINT - FIND THE REAL ISSUE")
    print("="*60)
    
    # Test 1: Empty body
    print("\n1. Test with EMPTY body:")
    response = requests.post(f"{BASE_URL}/api/v1/public/track-search", json={})
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:200]}")
    
    # Test 2: Just query (minimal)
    print("\n2. Test with just 'query':")
    response = requests.post(
        f"{BASE_URL}/api/v1/public/track-search",
        json={"query": "test"}
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ THIS WORKS: {response.json()}")
    else:
        print(f"   ❌ ERROR: {response.text}")
    
    # Test 3: With results_shown (from API docs)
    print("\n3. Test with 'query' and 'results_shown':")
    response = requests.post(
        f"{BASE_URL}/api/v1/public/track-search",
        json={"query": "test", "results_shown": 5}
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ THIS WORKS: {response.json()}")
    else:
        print(f"   ❌ ERROR: {response.text}")
    
    # Test 4: Check what the actual error says
    print("\n4. Send malformed data to see validation error:")
    response = requests.post(
        f"{BASE_URL}/api/v1/public/track-search",
        data="not json",  # Send non-JSON
        headers={"Content-Type": "application/json"}
    )
    print(f"   Status: {response.status_code}")
    print(f"   Error details: {response.text}")
    
    # Test 5: Check the OpenAPI spec
    print("\n5. Checking OpenAPI documentation:")
    response = requests.get(f"{BASE_URL}/openapi.json")
    if response.status_code == 200:
        spec = response.json()
        # Find track-search endpoint
        track_search_path = spec.get("paths", {}).get("/api/v1/public/track-search", {})
        if track_search_path:
            post_spec = track_search_path.get("post", {})
            request_body = post_spec.get("requestBody", {})
            print(f"   Request body spec: {json.dumps(request_body, indent=2)}")

if __name__ == "__main__":
    test_track_search_detailed()
