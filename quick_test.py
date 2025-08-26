#!/usr/bin/env python3
"""
Quick test to verify the track-search endpoint is working
"""
import requests
import json

BASE_URL = "http://localhost:8000"

# Test 1: Simple request with just query
print("Test 1: Simple track-search request")
print("-" * 40)

response = requests.post(
    f"{BASE_URL}/api/v1/public/track-search",
    json={"query": "test device", "results_shown": 5},
    headers={"Content-Type": "application/json"}
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"✅ SUCCESS!")
    print(json.dumps(response.json(), indent=2))
else:
    print(f"❌ FAILED!")
    print(f"Error: {response.text}")

print("\n" + "=" * 40 + "\n")

# Test 2: Full request with all fields
print("Test 2: Full track-search request")
print("-" * 40)

response = requests.post(
    f"{BASE_URL}/api/v1/public/track-search",
    json={
        "query": "medtronic pump",
        "results_count": 10,
        "results_shown": 5,
        "filters": {"device_class": "II"},
        "session_id": "test-123",
        "source": "web"
    },
    headers={"Content-Type": "application/json"}
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    print(f"✅ SUCCESS!")
    print(json.dumps(response.json(), indent=2))
else:
    print(f"❌ FAILED!")
    print(f"Error: {response.text}")
