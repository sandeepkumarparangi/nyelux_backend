#!/usr/bin/env python3
"""
Test script for the public track-search endpoint - FIXED VERSION
"""
import requests
import json
from datetime import datetime

# Backend URL
BASE_URL = "http://localhost:8000"

def test_health():
    """Test if server is running"""
    print("1. Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"   ERROR: {e}")
        return False

def test_track_search_simple():
    """Test the track-search endpoint with simple data"""
    print("\n2. Testing track-search endpoint (simple)...")
    
    url = f"{BASE_URL}/api/v1/public/track-search"
    
    # Simple test data - matching the expected schema
    data = {
        "query": "infusion pump",
        "results_shown": 5
    }
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Test Script)"
    }
    
    print(f"   URL: {url}")
    print(f"   Data: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, json=data, headers=headers)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"   Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"   Error Response: {response.text}")
            
        return response.status_code == 200
    except Exception as e:
        print(f"   ERROR: {e}")
        return False

def test_track_search_full():
    """Test the track-search endpoint with all fields"""
    print("\n3. Testing track-search endpoint (full data)...")
    
    url = f"{BASE_URL}/api/v1/public/track-search"
    
    # Full test data - with all optional fields
    data = {
        "query": "medtronic ventilator",
        "results_count": 10,
        "results_shown": 5,
        "search_type": "public",
        "session_id": f"test-session-{datetime.now().timestamp()}",
        "filters": {
            "device_class": "II",
            "mri_safety": "Safe"
        },
        "source": "web"
    }
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Test Script)"
    }
    
    print(f"   URL: {url}")
    print(f"   Data: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, json=data, headers=headers)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"   Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"   Error Response: {response.text}")
            
        return response.status_code == 200
    except Exception as e:
        print(f"   ERROR: {e}")
        return False

def test_multiple_searches():
    """Test multiple searches to trigger lead capture"""
    print("\n4. Testing multiple searches (should trigger lead capture after 3)...")
    
    session_id = f"lead-test-{datetime.now().timestamp()}"
    url = f"{BASE_URL}/api/v1/public/track-search"
    
    search_queries = [
        "infusion pump",
        "ventilator",
        "surgical instruments",
        "MRI scanner"
    ]
    
    for i, query in enumerate(search_queries, 1):
        print(f"\n   Search #{i}: {query}")
        
        data = {
            "query": query,
            "results_count": 5,
            "session_id": session_id,
            "source": "web"
        }
        
        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                result = response.json()
                print(f"   ✓ Success: search_count={result.get('search_count', 0)}, "
                      f"show_lead_capture={result.get('show_lead_capture', False)}, "
                      f"show_lead_form={result.get('show_lead_form', False)}")
            else:
                print(f"   ✗ Failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

def test_public_search():
    """Test the main public search endpoint"""
    print("\n5. Testing public search endpoint (no API key)...")
    
    url = f"{BASE_URL}/api/v1/public/search"
    params = {
        "q": "infusion pump",
        "limit": 5
    }
    
    print(f"   URL: {url}")
    print(f"   Query: {params['q']}")
    
    try:
        # No API key for public search
        response = requests.get(url, params=params)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Results found: {len(data.get('results', []))}")
            if data.get('results'):
                print(f"   First result: {data['results'][0].get('device_name', 'N/A')}")
        else:
            print(f"   Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"   ERROR: {e}")

def test_typeahead():
    """Test typeahead endpoint"""
    print("\n6. Testing typeahead endpoint...")
    
    url = f"{BASE_URL}/api/v1/public/typeahead"
    params = {
        "q": "med",
        "limit": 5
    }
    
    print(f"   URL: {url}")
    print(f"   Query: {params['q']}")
    
    try:
        response = requests.get(url, params=params)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Suggestions found: {len(data.get('suggestions', []))}")
            if data.get('suggestions'):
                print(f"   First suggestion: {data['suggestions'][0].get('display_name', 'N/A')}")
        else:
            print(f"   Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"   ERROR: {e}")

def main():
    print("="*60)
    print("NYELUX BACKEND TEST - Public Search Tracking (FIXED)")
    print("="*60)
    
    # Run tests
    if not test_health():
        print("\n❌ Server is not running! Start it with: ./restart.sh")
        return
    
    test_track_search_simple()
    test_track_search_full()
    test_multiple_searches()
    test_public_search()
    test_typeahead()
    
    print("\n" + "="*60)
    print("Test completed!")
    print("="*60)

if __name__ == "__main__":
    main()
