#!/usr/bin/env python3
"""
Test the AI chat functionality with REAL device IDs
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_chat_with_real_device():
    """Test chat with a real FDA device ID"""
    
    # First, get a real device ID from search
    print("1. Getting a real device ID from search...")
    search_response = requests.get(
        f"{BASE_URL}/api/v1/public/search",
        params={"q": "infusion pump", "limit": 1}
    )
    
    if search_response.status_code != 200:
        print(f"❌ Search failed: {search_response.status_code}")
        return
    
    search_data = search_response.json()
    if not search_data.get("results"):
        print("❌ No devices found in search")
        return
    
    # Get the real device ID
    real_device_id = search_data["results"][0]["primary_di"]
    device_name = search_data["results"][0]["device_name"]
    
    print(f"✅ Found device: {device_name}")
    print(f"   Device ID: {real_device_id}")
    
    # Now test chat with this real device
    print(f"\n2. Testing chat with real device ID: {real_device_id}")
    
    chat_data = {
        "message": "What are the key features of this device?",
        "session_id": "test-chat-123"
    }
    
    chat_response = requests.post(
        f"{BASE_URL}/api/v1/vendor/device/{real_device_id}/chat",
        json=chat_data,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"   Status: {chat_response.status_code}")
    
    if chat_response.status_code == 200:
        response_data = chat_response.json()
        print("✅ Chat successful!")
        print(f"   Device: {response_data.get('device_name', 'N/A')}")
        print(f"   AI Available: {response_data.get('ai_available', False)}")
        print(f"\n   Response: {response_data.get('ai_response', 'N/A')[:200]}...")
    else:
        print(f"❌ Chat failed: {chat_response.text}")
    
    # Test with invalid device ID to show error handling
    print("\n3. Testing with invalid device ID (should fail gracefully)...")
    invalid_response = requests.post(
        f"{BASE_URL}/api/v1/vendor/device/INVALID123/chat",
        json=chat_data,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"   Status: {invalid_response.status_code}")
    if invalid_response.status_code == 404:
        print("✅ Correctly returned 404 for invalid device")
    else:
        print(f"   Response: {invalid_response.text[:200]}...")

if __name__ == "__main__":
    print("="*60)
    print("TESTING AI CHAT WITH REAL FDA DEVICE IDs")
    print("="*60)
    
    test_chat_with_real_device()
    
    print("\n" + "="*60)
    print("FRONTEND USAGE:")
    print("="*60)
    print("""
Replace the hardcoded device ID in your frontend with a real one:

1. Run: python3 get_real_test_data.py
2. Copy any device ID from the output
3. In your frontend code, replace '6854KGDHR' with the real ID

Example API call from frontend:
  POST /api/v1/vendor/device/{REAL_DEVICE_ID}/chat
  Body: {
    "message": "Your question here",
    "session_id": "unique-session-id"
  }
""")
