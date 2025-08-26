#!/usr/bin/env python3
"""
Vendor Portal Verification Script
Run this to verify all vendor portal endpoints are working correctly.
"""

import asyncio
import httpx
from typing import Dict, Any
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
SUPER_ADMIN_TOKEN = None  # Will be set after login
VENDOR_ADMIN_TOKEN = None
HCP_TOKEN = None

# Test data
test_vendor = {
    "organization_name": "Test Medical Devices Inc",
    "admin_email": "admin@testmedical.com",
    "admin_first_name": "John",
    "admin_last_name": "Doe",
    "custom_url_slug": "test-medical"
}

test_lead = {
    "email": "doctor@hospital.com",
    "first_name": "Dr",
    "last_name": "Smith",
    "organization_name": "City Hospital",
    "job_title": "Chief of Surgery",
    "phone": "555-0100",
    "interested_devices": [],
    "message": "Interested in your surgical devices"
}


async def test_auth_endpoints():
    """Test authentication endpoints."""
    print("\n=== Testing Authentication ===")
    
    async with httpx.AsyncClient() as client:
        # Test super admin login (you need to create this user first)
        response = await client.post(
            f"{BASE_URL}/auth/login",
            data={
                "username": "admin@nyelux.com",
                "password": "SecurePassword123!"
            }
        )
        
        if response.status_code == 200:
            global SUPER_ADMIN_TOKEN
            SUPER_ADMIN_TOKEN = response.json()["access_token"]
            print("✅ Super admin login successful")
        else:
            print(f"❌ Super admin login failed: {response.status_code}")
            return False
    
    return True


async def test_vendor_onboarding():
    """Test vendor onboarding by super admin."""
    print("\n=== Testing Vendor Onboarding ===")
    
    if not SUPER_ADMIN_TOKEN:
        print("❌ No super admin token available")
        return None
    
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        
        # Create vendor
        response = await client.post(
            f"{BASE_URL}/super-admin/onboard-vendor",
            headers=headers,
            json=test_vendor
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Vendor created: {result['vendor_profile']['url_slug']}")
            print(f"   Public URL: {result['vendor_profile']['public_url']}")
            print(f"   Devices found: {result['vendor_profile']['devices_found']}")
            
            if 'vendor_admin' in result:
                print(f"   Admin created: {result['vendor_admin']['email']}")
                print(f"   Temp password: {result['vendor_admin']['temporary_password']}")
            
            return result
        else:
            print(f"❌ Vendor onboarding failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return None


async def test_public_vendor_page(url_slug: str):
    """Test public vendor page access."""
    print(f"\n=== Testing Public Vendor Page: {url_slug} ===")
    
    async with httpx.AsyncClient() as client:
        # Test vendor profile page
        response = await client.get(f"{BASE_URL}/vendor/{url_slug}")
        
        if response.status_code == 200:
            profile = response.json()
            print(f"✅ Public page accessible")
            print(f"   Name: {profile['display_name']}")
            print(f"   Chat enabled: {profile['chat_enabled']}")
            print(f"   Lead capture: {profile['lead_capture_enabled']}")
        else:
            print(f"❌ Public page failed: {response.status_code}")
            return False
        
        # Test device listing
        response = await client.get(f"{BASE_URL}/vendor/{url_slug}/devices")
        
        if response.status_code == 200:
            devices = response.json()
            print(f"✅ Device listing: {devices['total']} devices")
        else:
            print(f"❌ Device listing failed: {response.status_code}")
        
        # Test vendor directory
        response = await client.get(f"{BASE_URL}/vendor/directory")
        
        if response.status_code == 200:
            directory = response.json()
            print(f"✅ Vendor directory: {len(directory['vendors'])} vendors")
        else:
            print(f"❌ Vendor directory failed: {response.status_code}")
    
    return True


async def test_lead_capture(url_slug: str):
    """Test lead capture on vendor page."""
    print(f"\n=== Testing Lead Capture for {url_slug} ===")
    
    async with httpx.AsyncClient() as client:
        # Submit lead
        response = await client.post(
            f"{BASE_URL}/vendor/{url_slug}/lead",
            json=test_lead
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"✅ Lead captured successfully")
            print(f"   Lead ID: {result.get('lead_id', 'N/A')}")
            print(f"   Score: {result.get('lead_score', 'N/A')}")
            return result
        else:
            print(f"❌ Lead capture failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return None


async def test_vendor_chat(url_slug: str):
    """Test vendor chat functionality."""
    print(f"\n=== Testing Vendor Chat for {url_slug} ===")
    
    async with httpx.AsyncClient() as client:
        # Start chat session
        response = await client.post(
            f"{BASE_URL}/vendor-chat/{url_slug}/start",
            json={
                "device_id": None,
                "visitor_info": {"email": "visitor@example.com"}
            }
        )
        
        if response.status_code == 200:
            session = response.json()
            session_id = session["session_id"]
            print(f"✅ Chat session started: {session_id}")
            print(f"   Welcome: {session['vendor']['welcome_message'][:50]}...")
            
            # Send message
            response = await client.post(
                f"{BASE_URL}/vendor-chat/{url_slug}/message",
                json={
                    "session_id": session_id,
                    "message": "What support options do you offer?",
                    "visitor_email": "visitor@example.com"
                }
            )
            
            if response.status_code == 200:
                reply = response.json()
                print(f"✅ Chat message processed")
                print(f"   Response: {reply['response'][:100]}...")
                print(f"   Lead trigger: {reply.get('lead_capture_suggested', False)}")
            else:
                print(f"❌ Chat message failed: {response.status_code}")
        else:
            print(f"❌ Chat start failed: {response.status_code}")


async def test_hcp_interactions():
    """Test HCP vendor interaction endpoints."""
    print("\n=== Testing HCP Vendor Interactions ===")
    
    # First need to login as HCP (assuming one exists)
    # This is a placeholder - you'd need actual HCP credentials
    
    async with httpx.AsyncClient() as client:
        # Test access request (would need auth)
        print("⚠️  HCP endpoints require authenticated HCP user")
        print("   Would test:")
        print("   - Access requests")
        print("   - Service requests")
        print("   - Following vendors")


async def test_vendor_management():
    """Test vendor management endpoints."""
    print("\n=== Testing Vendor Management ===")
    
    # Would need vendor admin token
    print("⚠️  Vendor management requires vendor admin authentication")
    print("   Would test:")
    print("   - Lead management")
    print("   - Service request handling")
    print("   - Analytics dashboard")
    print("   - Profile updates")


async def test_super_admin_features():
    """Test super admin management features."""
    print("\n=== Testing Super Admin Features ===")
    
    if not SUPER_ADMIN_TOKEN:
        print("❌ No super admin token available")
        return
    
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        
        # List all vendors
        response = await client.get(
            f"{BASE_URL}/super-admin/vendors",
            headers=headers
        )
        
        if response.status_code == 200:
            vendors = response.json()
            print(f"✅ Vendor list: {len(vendors)} vendors")
            for vendor in vendors[:3]:  # Show first 3
                print(f"   - {vendor['display_name']} ({vendor['url_slug']})")
                print(f"     Devices: {vendor['total_devices']}, Leads: {vendor['total_leads']}")
        else:
            print(f"❌ Vendor list failed: {response.status_code}")
        
        # Get system stats
        response = await client.get(
            f"{BASE_URL}/super-admin/system-stats",
            headers=headers
        )
        
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ System Statistics:")
            print(f"   Total vendors: {stats['total_vendors']}")
            print(f"   Total leads: {stats['total_leads']}")
            print(f"   Total service requests: {stats['total_service_requests']}")
        else:
            print(f"❌ System stats failed: {response.status_code}")


async def run_verification():
    """Run complete verification suite."""
    print("=" * 60)
    print("VENDOR PORTAL VERIFICATION SUITE")
    print("=" * 60)
    
    # Test authentication
    auth_success = await test_auth_endpoints()
    if not auth_success:
        print("\n❌ Authentication failed - cannot continue")
        return
    
    # Test vendor onboarding
    vendor_result = await test_vendor_onboarding()
    
    if vendor_result:
        url_slug = vendor_result['vendor_profile']['url_slug']
        
        # Test public pages
        await test_public_vendor_page(url_slug)
        
        # Test lead capture
        await test_lead_capture(url_slug)
        
        # Test chat
        await test_vendor_chat(url_slug)
    
    # Test other features
    await test_hcp_interactions()
    await test_vendor_management()
    await test_super_admin_features()
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_verification())
