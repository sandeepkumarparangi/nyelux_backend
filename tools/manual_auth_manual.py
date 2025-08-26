#!/usr/bin/env python3
"""Test authentication endpoints to ensure they're working correctly."""

import requests
import json
import sys
from datetime import datetime

# API base URL
BASE_URL = "http://localhost:8000/api/v1"

def test_register():
    """Test user registration endpoint."""
    print("\n=== Testing User Registration ===")
    
    # Generate unique email for testing
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    test_user = {
        "email": f"test_{timestamp}@example.com",
        "password": "SecurePass123!",
        "first_name": "Test",
        "last_name": "User",
        "role": "physician"
    }
    
    print(f"Registering user: {test_user['email']}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json=test_user,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 201:
            print("✅ Registration successful!")
            return test_user, response.json()
        else:
            print("❌ Registration failed!")
            return None, None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None

def test_login(email, password):
    """Test user login endpoint."""
    print("\n=== Testing User Login ===")
    print(f"Logging in as: {email}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            data={
                "username": email,
                "password": password
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Login successful!")
            return response.json()
        else:
            print("❌ Login failed!")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_get_current_user(token):
    """Test get current user endpoint."""
    print("\n=== Testing Get Current User ===")
    
    try:
        response = requests.get(
            f"{BASE_URL}/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Get current user successful!")
            return response.json()
        else:
            print("❌ Get current user failed!")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    """Run all authentication tests."""
    print("=" * 60)
    print("NYELUX AUTHENTICATION TEST")
    print("=" * 60)
    
    # Check if API is running
    try:
        health = requests.get("http://localhost:8000/health")
        if health.status_code != 200:
            print("❌ API is not running. Please start the server first.")
            sys.exit(1)
    except:
        print("❌ Cannot connect to API. Please start the server first.")
        sys.exit(1)
    
    # Test registration
    test_user, registered_user = test_register()
    if not test_user:
        print("\n❌ Registration test failed. Stopping tests.")
        sys.exit(1)
    
    # Test login
    login_response = test_login(test_user["email"], test_user["password"])
    if not login_response:
        print("\n❌ Login test failed. Stopping tests.")
        sys.exit(1)
    
    # Test get current user
    token = login_response.get("access_token")
    if token:
        current_user = test_get_current_user(token)
        if not current_user:
            print("\n❌ Get current user test failed.")
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    main()
