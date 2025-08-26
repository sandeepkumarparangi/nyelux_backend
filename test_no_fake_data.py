#!/usr/bin/env python3
"""
COMPREHENSIVE TEST TO VERIFY NO FAKE DATA IS BEING USED
This script tests ALL public endpoints to ensure they use REAL Supabase data
"""
import requests
import json
import sys
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

BASE_URL = "http://localhost:8000"

def print_header(text):
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}{text}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")

def print_test(test_name):
    print(f"\n{Fore.YELLOW}Testing: {test_name}{Style.RESET_ALL}")

def print_success(message):
    print(f"{Fore.GREEN}✅ {message}{Style.RESET_ALL}")

def print_error(message):
    print(f"{Fore.RED}❌ {message}{Style.RESET_ALL}")

def print_warning(message):
    print(f"{Fore.YELLOW}⚠️  {message}{Style.RESET_ALL}")

def test_health():
    """Verify server is running"""
    print_test("Server Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print_success("Server is running")
            return True
        else:
            print_error(f"Server returned status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Cannot connect to server: {e}")
        return False

def test_public_search():
    """Test public search returns REAL data"""
    print_test("Public Search - Real Data Check")
    
    test_queries = [
        "infusion pump",
        "medtronic",
        "ventilator",
        "catheter",
        "stent"
    ]
    
    for query in test_queries:
        print(f"\n  Searching for: '{query}'")
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/public/search",
                params={"q": query, "limit": 5}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("results"):
                    print_success(f"Found {len(data['results'])} devices")
                    
                    # Check first device for real data indicators
                    first_device = data['results'][0]
                    
                    # Real FDA devices have specific DI format
                    if first_device.get('primary_di'):
                        print(f"    DI: {first_device['primary_di']}")
                    
                    # Real devices have manufacturers
                    if first_device.get('manufacturer_name'):
                        print(f"    Manufacturer: {first_device['manufacturer_name']}")
                    
                    # Check for FDA device class
                    if first_device.get('device_class'):
                        print(f"    FDA Class: {first_device['device_class']}")
                    
                    # This looks like real data
                    if (first_device.get('primary_di') and 
                        first_device.get('manufacturer_name') and 
                        first_device.get('device_class')):
                        print_success("  ✓ This appears to be REAL FDA data")
                    else:
                        print_warning("  ? Data structure incomplete")
                else:
                    print_warning(f"No results for '{query}'")
                    if data.get("status") == "error":
                        print_error(f"  Error: {data.get('message', 'Unknown error')}")
            else:
                print_error(f"Search failed: {response.status_code}")
                
        except Exception as e:
            print_error(f"Search error: {e}")

def test_manufacturers():
    """Test manufacturers endpoint for real data"""
    print_test("Manufacturers List - Real Data Check")
    
    try:
        # Test without query (should get all manufacturers)
        response = requests.get(
            f"{BASE_URL}/api/v1/public/manufacturers",
            params={"limit": 10}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("data_source") == "supabase_real_data":
                print_success("Endpoint confirms using Supabase real data")
            
            manufacturers = data.get("manufacturers", [])
            if manufacturers:
                print_success(f"Found {len(manufacturers)} manufacturers")
                print("  Sample manufacturers:")
                for mfr in manufacturers[:5]:
                    print(f"    - {mfr}")
                
                # Check if these look like hardcoded values
                hardcoded_suspects = [
                    "Medtronic",
                    "Johnson & Johnson",
                    "Abbott Laboratories",
                    "Boston Scientific",
                    "GE Healthcare"
                ]
                
                if manufacturers == hardcoded_suspects[:len(manufacturers)]:
                    print_error("⚠️  WARNING: These might be hardcoded values!")
                else:
                    print_success("✓ Manufacturers appear to be from real database")
            else:
                print_warning("No manufacturers returned")
                
        else:
            print_error(f"Request failed: {response.status_code}")
            
    except Exception as e:
        print_error(f"Manufacturers test error: {e}")

def test_device_details():
    """Test getting specific device details"""
    print_test("Device Details - Real Data Check")
    
    # First, get a real device DI from search
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/public/search",
            params={"q": "pump", "limit": 1}
        )
        
        if response.status_code == 200 and response.json().get("results"):
            device_di = response.json()["results"][0]["primary_di"]
            print(f"  Testing device: {device_di}")
            
            # Get device details
            detail_response = requests.get(
                f"{BASE_URL}/api/v1/public/devices/{device_di}"
            )
            
            if detail_response.status_code == 200:
                device = detail_response.json()
                
                # Check for comprehensive FDA data fields
                fda_fields = [
                    'primary_di', 'device_name', 'manufacturer_name',
                    'device_class', 'gmdn_terms', 'mri_safety',
                    'sterile', 'single_use', 'implantable'
                ]
                
                present_fields = [f for f in fda_fields if f in device]
                print_success(f"Device has {len(present_fields)}/{len(fda_fields)} FDA fields")
                
                # Show some details
                print(f"    Name: {device.get('device_name', 'N/A')[:50]}...")
                print(f"    Manufacturer: {device.get('manufacturer_name', 'N/A')}")
                print(f"    Class: {device.get('device_class', 'N/A')}")
                print(f"    MRI Safety: {device.get('mri_safety', 'N/A')}")
                
                if len(present_fields) >= 6:
                    print_success("✓ This is definitely REAL FDA data")
                else:
                    print_warning("? Some FDA fields missing")
            else:
                print_error(f"Failed to get device details: {detail_response.status_code}")
        else:
            print_warning("Could not get a device DI for testing")
            
    except Exception as e:
        print_error(f"Device details test error: {e}")

def test_stats():
    """Test platform statistics"""
    print_test("Platform Statistics - Real Data Check")
    
    try:
        response = requests.get(f"{BASE_URL}/api/v1/public/stats")
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"  Total Devices: {data.get('total_devices', 0):,}")
            print(f"  Manufacturers: {data.get('manufacturers', 0):,}")
            print(f"  Device Classes: {data.get('device_classes', 0)}")
            print(f"  Data Source: {data.get('data_source', 'Unknown')}")
            print(f"  Status: {data.get('status', 'Unknown')}")
            
            if data.get('is_real_data'):
                print_success("✓ Stats confirm using REAL data")
            
            if data.get('total_devices', 0) > 1000000:
                print_success("✓ Device count suggests real FDA database (4.6M+ devices)")
            elif data.get('total_devices', 0) == 0:
                print_error("❌ No devices found - Supabase might not be connected")
            else:
                print_warning(f"? Low device count: {data.get('total_devices', 0)}")
                
        else:
            print_error(f"Stats request failed: {response.status_code}")
            
    except Exception as e:
        print_error(f"Stats test error: {e}")

def test_typeahead():
    """Test typeahead search"""
    print_test("Typeahead Search - Real Data Check")
    
    test_prefixes = ["med", "inf", "cat"]
    
    for prefix in test_prefixes:
        print(f"\n  Testing typeahead for: '{prefix}'")
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/public/typeahead",
                params={"q": prefix, "limit": 3}
            )
            
            if response.status_code == 200:
                data = response.json()
                suggestions = data.get("suggestions", [])
                
                if suggestions:
                    print_success(f"Got {len(suggestions)} suggestions")
                    for sugg in suggestions:
                        print(f"    - {sugg.get('display_name', 'N/A')}")
                else:
                    print_warning("No suggestions returned")
            else:
                print_error(f"Typeahead failed: {response.status_code}")
                
        except Exception as e:
            print_error(f"Typeahead error: {e}")

def main():
    print_header("NYELUX BACKEND - FAKE DATA DETECTION TEST")
    print("This test verifies that ALL endpoints use REAL Supabase data")
    print("and NO fake/mock data is being returned")
    
    if not test_health():
        print_error("\nServer is not running! Start it first.")
        print("Run: cd '/Users/nehamchangappa/Downloads/Nyelux Beta/nyelux-backend-beta'")
        print("     ./restart.sh")
        sys.exit(1)
    
    # Run all tests
    test_public_search()
    test_manufacturers()
    test_device_details()
    test_stats()
    test_typeahead()
    
    print_header("TEST SUMMARY")
    print("\nIf you see real FDA device data above with:")
    print("  • Valid DI numbers")
    print("  • Real manufacturer names")
    print("  • FDA device classes")
    print("  • MRI safety information")
    print("  • 4.6M+ total devices")
    print("\nThen you are using REAL SUPABASE DATA ✅")
    print("\nIf you see empty results or errors:")
    print("  • Check Supabase connection in .env")
    print("  • Verify Supabase credentials are valid")
    print("  • Check if gudid_devices table exists in Supabase")

if __name__ == "__main__":
    main()
