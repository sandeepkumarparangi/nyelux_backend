#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick test of authentication endpoints."""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

# Test health check first
print("Testing health check...")
try:
    response = requests.get(f"{BASE_URL}/health")
    print(f"Health check status: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
    print("Make sure the server is running!")
    exit(1)

# Test registration
print("\n" + "="*60)
print("Testing user registration...")
timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
test_data = {
    "email": f"test_{timestamp}@example.com",
    "password": "TestPass123!",
    "first_name": "Test",
    "last_name": "User",
    "role": "physician"
}

print(f"Request data: {json.dumps(test_data, indent=2)}")

try:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json=test_data,
        headers={"Content-Type": "application/json"}
    )
    print(f"\nStatus code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 201:
        print("\n✅ Registration successful!")
        
        # Test login
        print("\n" + "="*60)
        print("Testing login...")
        login_data = {
            "username": test_data["email"],
            "password": test_data["password"]
        }
        
        login_response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data=login_data
        )
        print(f"\nLogin status: {login_response.status_code}")
        print(f"Login response: {json.dumps(login_response.json(), indent=2)}")
        
        if login_response.status_code == 200:
            print("\n✅ Login successful!")
    else:
        print("\n❌ Registration failed!")
        
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
