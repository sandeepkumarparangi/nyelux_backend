#!/usr/bin/env python3
"""
Get REAL test data from Supabase for frontend testing
NO FAKE DATA - All device IDs and data from actual FDA database
"""
import os
import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Remove proxy settings that cause issues
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY']:
    os.environ.pop(proxy_var, None)

from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

print("="*70)
print("NYELUX REAL TEST DATA FROM SUPABASE")
print("Use these REAL device IDs and manufacturers for frontend testing")
print("="*70)

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ MISSING SUPABASE CREDENTIALS!")
    sys.exit(1)

# Connect to Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# 1. Get popular manufacturers with devices
print("\n📊 POPULAR MANUFACTURERS WITH REAL DEVICES:")
print("-" * 50)

manufacturers_to_test = [
    "Medtronic",
    "Abbott",
    "Johnson & Johnson",
    "Boston Scientific",
    "GE Healthcare",
    "Siemens",
    "Stryker",
    "Becton Dickinson",
    "3M",
    "Edwards Lifesciences"
]

test_data = {
    "manufacturers": [],
    "devices": [],
    "search_queries": [],
    "api_examples": []
}

for manufacturer in manufacturers_to_test:
    try:
        # Get devices for this manufacturer
        response = supabase.table('gudid_devices').select(
            'primary_di, device_name, device_class, mri_safety, device_description'
        ).ilike('manufacturer_name', f'%{manufacturer}%').limit(3).execute()
        
        if response.data:
            print(f"\n✅ {manufacturer}:")
            manufacturer_data = {
                "name": manufacturer,
                "devices": []
            }
            
            for device in response.data:
                device_info = {
                    "id": device['primary_di'],
                    "name": device['device_name'][:60] + "..." if len(device['device_name']) > 60 else device['device_name'],
                    "class": device.get('device_class', 'N/A'),
                    "mri_safety": device.get('mri_safety', 'N/A')
                }
                manufacturer_data["devices"].append(device_info)
                test_data["devices"].append(device_info)
                
                print(f"   Device ID: {device['primary_di']}")
                print(f"   Name: {device_info['name']}")
                print(f"   Class: {device_info['class']}, MRI: {device_info['mri_safety']}")
                print()
            
            test_data["manufacturers"].append(manufacturer_data)
    except Exception as e:
        print(f"   ⚠️  Error getting {manufacturer} devices: {e}")

# 2. Get devices by category for testing
print("\n🔍 DEVICES BY CATEGORY FOR TESTING:")
print("-" * 50)

categories = [
    ("infusion pump", "Infusion Pumps"),
    ("ventilator", "Ventilators"),
    ("catheter", "Catheters"),
    ("stent", "Stents"),
    ("pacemaker", "Pacemakers"),
    ("MRI", "MRI Equipment"),
    ("defibrillator", "Defibrillators"),
    ("surgical", "Surgical Instruments")
]

for search_term, category_name in categories:
    try:
        response = supabase.table('gudid_devices').select(
            'primary_di, device_name, manufacturer_name'
        ).ilike('device_name', f'%{search_term}%').limit(2).execute()
        
        if response.data:
            print(f"\n{category_name}:")
            test_data["search_queries"].append({
                "query": search_term,
                "category": category_name,
                "example_results": []
            })
            
            for device in response.data:
                print(f"  • ID: {device['primary_di']}")
                print(f"    Name: {device['device_name'][:50]}...")
                print(f"    Manufacturer: {device['manufacturer_name']}")
                
                test_data["search_queries"][-1]["example_results"].append({
                    "id": device['primary_di'],
                    "name": device['device_name'][:50],
                    "manufacturer": device['manufacturer_name']
                })
    except Exception as e:
        print(f"  ⚠️  Error: {e}")

# 3. Generate API test examples
print("\n🚀 API TEST EXAMPLES:")
print("-" * 50)

if test_data["devices"]:
    first_device = test_data["devices"][0]
    
    api_examples = [
        {
            "description": "Search for devices",
            "method": "GET",
            "endpoint": "/api/v1/public/search",
            "params": {"q": "infusion pump", "limit": 5},
            "curl": f'curl "http://localhost:8000/api/v1/public/search?q=infusion%20pump&limit=5"'
        },
        {
            "description": "Get device details",
            "method": "GET",
            "endpoint": f"/api/v1/public/devices/{first_device['id']}",
            "curl": f'curl "http://localhost:8000/api/v1/public/devices/{first_device["id"]}"'
        },
        {
            "description": "Typeahead search",
            "method": "GET",
            "endpoint": "/api/v1/public/typeahead",
            "params": {"q": "med", "limit": 5},
            "curl": f'curl "http://localhost:8000/api/v1/public/typeahead?q=med&limit=5"'
        },
        {
            "description": "Track search (for lead generation)",
            "method": "POST",
            "endpoint": "/api/v1/public/track-search",
            "body": {
                "query": "ventilator",
                "results_count": 10,
                "session_id": "test-session-123"
            },
            "curl": '''curl -X POST http://localhost:8000/api/v1/public/track-search \\
  -H "Content-Type: application/json" \\
  -d '{"query": "ventilator", "results_count": 10, "session_id": "test-123"}'"""
        },
        {
            "description": "Chat about device (AI)",
            "method": "POST",
            "endpoint": f"/api/v1/vendor/device/{first_device['id']}/chat",
            "body": {
                "message": "What are the key features of this device?",
                "session_id": "chat-session-123"
            },
            "curl": f'''curl -X POST http://localhost:8000/api/v1/vendor/device/{first_device["id"]}/chat \\
  -H "Content-Type: application/json" \\
  -d '{{"message": "What are the key features?", "session_id": "chat-123"}}'"""
        }
    ]
    
    test_data["api_examples"] = api_examples
    
    for example in api_examples:
        print(f"\n{example['description']}:")
        print(f"  {example['method']} {example['endpoint']}")
        if example.get('params'):
            print(f"  Params: {json.dumps(example['params'])}")
        if example.get('body'):
            print(f"  Body: {json.dumps(example['body'], indent=2)}")
        print(f"\n  Test with curl:")
        print(f"  {example['curl']}")

# 4. Save test data to file
output_file = "test_data_real.json"
with open(output_file, 'w') as f:
    json.dump(test_data, f, indent=2)

print("\n" + "="*70)
print("✅ TEST DATA SAVED TO: test_data_real.json")
print("="*70)

# 5. Frontend test scenarios
print("\n📱 FRONTEND TEST SCENARIOS:")
print("-" * 50)

print("""
1. PUBLIC SEARCH TEST:
   - Search for "infusion pump"
   - Search for "Medtronic"
   - Search for "MRI safe devices"

2. DEVICE DETAILS TEST:
   - Use any device ID from above
   - Example: {device_id}

3. AI CHAT TEST:
   - Click on any device
   - Ask: "What is this device used for?"
   - Ask: "Is this MRI safe?"
   - Ask: "What training is required?"

4. LEAD GENERATION TEST:
   - Perform 3 searches as anonymous user
   - Should trigger lead capture form

5. MANUFACTURER PAGE TEST:
   - Go to: /vendor/by-name/Medtronic
   - Go to: /vendor/by-name/Abbott
   - Browse devices by manufacturer
""".format(device_id=test_data["devices"][0]["id"] if test_data["devices"] else "N/A"))

print("\n⚠️  IMPORTANT NOTES:")
print("-" * 50)
print("1. All device IDs above are REAL FDA GUDID identifiers")
print("2. Use these exact IDs in your frontend for testing")
print("3. The chat endpoint needs a valid device ID from this list")
print("4. Replace '6854KGDHR' with a real device ID from above")
print("")
print("Example device IDs to use in frontend:")
for i, device in enumerate(test_data["devices"][:5], 1):
    print(f"  {i}. {device['id']} - {device['name']}")

print("\n" + "="*70)
print("END OF REAL TEST DATA")
print("="*70)
