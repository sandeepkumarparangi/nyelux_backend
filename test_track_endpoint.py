#!/usr/bin/env python3
"""
Test the track-search endpoint to ensure it's working
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_track_search():
    """Test the track-search endpoint with exact API documentation format"""
    
    print("="*60)
    print("TESTING /api/v1/public/track-search")
    print("="*60)
    
    # Test 1: Minimal required fields (based on your API documentation)
    print("\n1. Test with minimal fields (query + results_shown):")
    data1 = {
        "query": "infusion pump medtronic",
        "results_shown": 15
    }
    
    response1 = requests.post(
        f"{BASE_URL}/api/v1/public/track-search",
        json=data1,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"   Request: {json.dumps(data1, indent=2)}")
    print(f"   Status: {response1.status_code}")
    if response1.status_code == 200:
        print(f"   ✅ Response: {json.dumps(response1.json(), indent=2)}")
    else:
        print(f"   ❌ Error: {response1.text}")
    
    # Test 2: With the schema fields (what the backend expects)
    print("\n2. Test with backend schema fields:")
    data2 = {
        "query": "medical device companies",
        "results_count": 10,  # Note: backend expects results_count, not results_shown
        "session_id": "test-session-123",
        "source": "web"
    }
    
    response2 = requests.post(
        f"{BASE_URL}/api/v1/public/track-search",
        json=data2,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"   Request: {json.dumps(data2, indent=2)}")
    print(f"   Status: {response2.status_code}")
    if response2.status_code == 200:
        print(f"   ✅ Response: {json.dumps(response2.json(), indent=2)}")
    else:
        print(f"   ❌ Error: {response2.text}")
    
    # Test 3: Check what fields are actually required
    print("\n3. Test with only 'query' field:")
    data3 = {
        "query": "test search"
    }
    
    response3 = requests.post(
        f"{BASE_URL}/api/v1/public/track-search",
        json=data3,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"   Request: {json.dumps(data3, indent=2)}")
    print(f"   Status: {response3.status_code}")
    if response3.status_code == 200:
        print(f"   ✅ Response: {json.dumps(response3.json(), indent=2)}")
    else:
        print(f"   ❌ Error: {response3.text}")

if __name__ == "__main__":
    test_track_search()
    
    print("\n" + "="*60)
    print("DIAGNOSIS:")
    print("="*60)
    print("\nThe backend expects these fields:")
    print("- query: string (REQUIRED)")
    print("- results_count: integer (OPTIONAL, default 0)")
    print("- filters: object (OPTIONAL)")
    print("- session_id: string (OPTIONAL)")
    print("- source: string (OPTIONAL, default 'web')")
    print("\nBut your API documentation says:")
    print("- query: string")
    print("- results_shown: integer")
    print("\nThere's a mismatch: 'results_shown' vs 'results_count'")
