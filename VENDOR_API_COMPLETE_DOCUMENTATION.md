# COMPLETE VENDOR PUBLIC API DOCUMENTATION - DYNAMIC FROM FDA DATA

## User Flow & Implementation Guide

This is the COMPLETE implementation that creates vendor pages dynamically from FDA/Supabase data. No vendor_profiles table needed!

---

## 🎯 USER FLOW

1. **User searches for a manufacturer**
   - User types "Medtronic" in search
   - Gets list of manufacturers from FDA data
   - Clicks on "Medtronic Inc"

2. **User lands on dynamic vendor page**
   - URL: `/vendor/medtronic-inc`
   - Page generated from FDA data on-the-fly
   - Shows all FDA devices for that manufacturer

3. **User clicks on a device**
   - Opens device details with FDA information
   - AI chat available with device context

4. **User asks questions in AI chat**
   - Questions answered using real FDA data
   - OpenAI provides structured responses
   - No placeholders - real device information

---

## 📡 API ENDPOINTS - WORKING NOW

### 1. Search for Manufacturers
**Endpoint:** `GET /api/v1/vendor/search`

**Purpose:** Entry point - users search for medical device companies

**Parameters:**
- `q` (string, required): Search query (min 2 chars)
- `limit` (integer, optional): Max results (default 20)

**Example Request:**
```
GET http://localhost:8000/api/v1/vendor/search?q=medtronic&limit=10
```

**Response:**
```json
{
  "manufacturers": [
    {
      "name": "MEDTRONIC INC",
      "url_slug": "medtronic-inc",
      "url": "/vendor/medtronic-inc",
      "device_count": 1543
    },
    {
      "name": "MEDTRONIC MINIMED INC",
      "url_slug": "medtronic-minimed-inc",
      "url": "/vendor/medtronic-minimed-inc",
      "device_count": 287
    }
  ],
  "total": 2
}
```

---

### 2. Get Dynamic Vendor Page
**Endpoint:** `GET /api/v1/vendor/{manufacturer_slug}`

**Purpose:** Get dynamically generated vendor page from FDA data

**Example Request:**
```
GET http://localhost:8000/api/v1/vendor/medtronic-inc
```

**Response:**
```json
{
  "manufacturer_name": "MEDTRONIC INC",
  "url_slug": "medtronic-inc",
  "display_name": "MEDTRONIC INC",
  "tagline": "Medical Devices by MEDTRONIC INC",
  "description": "MEDTRONIC INC manufactures 1543 FDA-registered medical devices.",
  
  "statistics": {
    "total_devices": 1543,
    "device_classes": {
      "II": 892,
      "III": 451,
      "I": 200
    },
    "mri_safety_breakdown": {
      "MR Conditional": 623,
      "MR Unsafe": 412,
      "MR Safe": 108
    },
    "sterile_devices": 743,
    "life_supporting_devices": 234
  },
  
  "features": {
    "chat_enabled": true,
    "fda_data_available": true,
    "lead_capture_enabled": true
  },
  
  "featured_devices": [
    {
      "id": "00643169001234",
      "name": "MiniMed 780G System",
      "brand": "MiniMed",
      "model": "MMT-1780",
      "class": "III",
      "category": "Insulin infusion pump"
    }
  ]
}
```

---

### 3. Get Manufacturer Devices (Paginated)
**Endpoint:** `GET /api/v1/vendor/{manufacturer_slug}/devices`

**Purpose:** Get all devices for a manufacturer with pagination

**Parameters:**
- `page` (integer): Page number (default 1)
- `limit` (integer): Items per page (default 20, max 100)
- `search` (string, optional): Search within devices
- `device_class` (string, optional): Filter by FDA class (I, II, III)

**Example Request:**
```
GET http://localhost:8000/api/v1/vendor/medtronic-inc/devices?page=1&limit=20&device_class=III
```

**Response:**
```json
{
  "manufacturer": "MEDTRONIC INC",
  "devices": [
    {
      "id": "00643169001234",
      "name": "MiniMed 780G System",
      "brand": "MiniMed",
      "model": "MMT-1780",
      "catalog": "MMT-1780-WWW",
      "class": "III",
      "description": "The MiniMed 780G system consists of...",
      "category": "Insulin infusion pump, programmable",
      "mri_safety": "MR Unsafe",
      "sterile": false,
      "single_use": false,
      "implantable": false,
      "life_supporting": true,
      "prescription_required": true
    }
  ],
  "total_count": 451,
  "page": 1,
  "limit": 20,
  "total_pages": 23
}
```

---

### 4. Get Device Context for AI Chat
**Endpoint:** `GET /api/v1/vendor/{manufacturer_slug}/device/{device_id}/chat-context`

**Purpose:** Get device information formatted for AI chat

**Example Request:**
```
GET http://localhost:8000/api/v1/vendor/medtronic-inc/device/00643169001234/chat-context
```

**Response:**
```json
{
  "device_identifier": "00643169001234",
  "device_name": "MiniMed 780G System",
  "manufacturer": "MEDTRONIC INC",
  "brand": "MiniMed",
  "model": "MMT-1780",
  "fda_class": "III",
  "description": "The MiniMed 780G system consists of the following devices...",
  "mri_safety": "MR Unsafe",
  "sterile": false,
  "single_use": false,
  "implantable": false,
  "life_supporting": true,
  "prescription_required": true,
  "system_prompt": "You are a medical device expert assistant..."
}
```

---

### 5. Chat About Device (AI-Powered)
**Endpoint:** `POST /api/v1/vendor/{manufacturer_slug}/device/{device_id}/chat`

**Purpose:** Ask questions about a device, get AI responses with real FDA data

**Request Body:**
```json
{
  "message": "What are the key features of this insulin pump?",
  "session_id": "optional-session-id"
}
```

**Example Request:**
```
POST http://localhost:8000/api/v1/vendor/medtronic-inc/device/00643169001234/chat
Content-Type: application/json

{
  "message": "Is this device safe for MRI scans?"
}
```

**Response:**
```json
{
  "session_id": "chat-00643169001234-1704326400.123",
  "device_id": "00643169001234",
  "device_name": "MiniMed 780G System",
  "user_message": "Is this device safe for MRI scans?",
  "ai_response": "No, the MiniMed 780G System is classified as 'MR Unsafe' according to FDA records. This means the device is NOT safe for MRI scans. Patients must remove the insulin pump system before entering an MRI environment as the strong magnetic fields can damage the device and potentially harm the patient. The pump contains metallic components and electronic circuits that are incompatible with MRI machines. Before any MRI procedure, patients should consult with their healthcare provider about safely disconnecting and managing their insulin delivery during the scan.",
  "sources": ["FDA GUDID Database"],
  "timestamp": "2024-01-10T15:30:00Z"
}
```

---

### 6. Capture Lead
**Endpoint:** `POST /api/v1/vendor/{manufacturer_slug}/lead`

**Purpose:** Capture lead information when users want more info

**Request Body:**
```json
{
  "email": "doctor@hospital.com",
  "name": "Dr. Smith",
  "organization": "City Hospital",
  "message": "Interested in bulk pricing for insulin pumps",
  "interested_device": "00643169001234"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Thank you for your interest! We will contact you soon.",
  "lead_id": "lead-medtronic-inc-1704326400.123"
}
```

---

## 🚀 FRONTEND IMPLEMENTATION GUIDE

### Step 1: Implement Manufacturer Search
```javascript
// Search for manufacturers
const searchManufacturers = async (query) => {
  const response = await fetch(
    `http://localhost:8000/api/v1/vendor/search?q=${encodeURIComponent(query)}&limit=20`
  );
  return response.json();
};

// Usage
const results = await searchManufacturers("medtronic");
// Display results.manufacturers with links to /vendor/{url_slug}
```

### Step 2: Load Vendor Page
```javascript
// Load dynamic vendor page
const loadVendorPage = async (manufacturerSlug) => {
  const response = await fetch(
    `http://localhost:8000/api/v1/vendor/${manufacturerSlug}`
  );
  return response.json();
};

// Usage
const vendorData = await loadVendorPage("medtronic-inc");
// Display vendor info, statistics, and featured devices
```

### Step 3: Load Device List
```javascript
// Load paginated devices
const loadDevices = async (manufacturerSlug, page = 1, filters = {}) => {
  const params = new URLSearchParams({
    page,
    limit: 20,
    ...filters
  });
  
  const response = await fetch(
    `http://localhost:8000/api/v1/vendor/${manufacturerSlug}/devices?${params}`
  );
  return response.json();
};

// Usage
const devices = await loadDevices("medtronic-inc", 1, { device_class: "III" });
```

### Step 4: Implement Device Chat
```javascript
// Initialize chat for a device
const startDeviceChat = async (manufacturerSlug, deviceId) => {
  // Get device context first
  const contextResponse = await fetch(
    `http://localhost:8000/api/v1/vendor/${manufacturerSlug}/device/${deviceId}/chat-context`
  );
  const context = await contextResponse.json();
  
  return {
    deviceInfo: context,
    sessionId: `chat-${deviceId}-${Date.now()}`
  };
};

// Send chat message
const sendChatMessage = async (manufacturerSlug, deviceId, message, sessionId) => {
  const response = await fetch(
    `http://localhost:8000/api/v1/vendor/${manufacturerSlug}/device/${deviceId}/chat`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId })
    }
  );
  return response.json();
};

// Usage
const chat = await startDeviceChat("medtronic-inc", "00643169001234");
const response = await sendChatMessage(
  "medtronic-inc",
  "00643169001234",
  "What are the battery requirements?",
  chat.sessionId
);
```

---

## ✅ WHAT'S WORKING NOW

1. **Manufacturer Search** - Search FDA database for companies
2. **Dynamic Vendor Pages** - Generated from FDA data, no database needed
3. **Device Listings** - All FDA devices for each manufacturer
4. **Device Details** - Complete FDA information
5. **AI Chat** - Real responses using FDA data (if OpenAI key configured)
6. **Lead Capture** - Basic lead collection

---

## 🎨 FRONTEND UI SUGGESTIONS

### Vendor Page Layout
```
[Header]
- Manufacturer Name
- Tagline
- Total Devices Count

[Statistics Cards]
- Device Classes (I, II, III breakdown)
- MRI Safety Stats
- Sterile Devices Count
- Life Supporting Devices

[Device Grid]
- Card view with device name, model, class
- Click to expand details
- Chat button on each device

[Sidebar]
- Filters (Class, MRI Safety, etc)
- Search within devices
- Lead capture form
```

### Device Detail Modal
```
[Device Header]
- Name, Model, Brand
- FDA Class Badge
- MRI Safety Badge

[Tabs]
- Overview (Description, specs)
- Safety (Sterile, single-use, etc)
- Chat (AI assistant)

[Chat Interface]
- Pre-populated questions
- Message input
- Real-time responses
```

---

## 🔧 TESTING COMMANDS

```bash
# Test manufacturer search
curl "http://localhost:8000/api/v1/vendor/search?q=medtronic"

# Test vendor page (use actual slug from search)
curl "http://localhost:8000/api/v1/vendor/medtronic-inc"

# Test device list
curl "http://localhost:8000/api/v1/vendor/medtronic-inc/devices?page=1&limit=5"

# Test device context
curl "http://localhost:8000/api/v1/vendor/medtronic-inc/device/00643169001234/chat-context"

# Test chat (POST)
curl -X POST "http://localhost:8000/api/v1/vendor/medtronic-inc/device/00643169001234/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Is this device waterproof?"}'
```

---

## 📝 IMPORTANT NOTES

1. **No Database Required** - Everything generated from Supabase FDA data
2. **Real FDA Data** - 4.6M devices, all manufacturers
3. **AI Chat** - Requires OpenAI API key in .env file
4. **URL Slugs** - Generated from manufacturer names (spaces to hyphens, lowercase)
5. **Case Sensitivity** - Manufacturer search is case-insensitive

---

## 🚨 CURRENT STATUS

- ✅ All endpoints implemented and working
- ✅ Connected to real Supabase FDA data
- ✅ Dynamic page generation
- ✅ AI chat with fallback
- ✅ No vendor_profiles table needed
- ✅ Organization model SSO issue fixed

The system is FULLY FUNCTIONAL and ready for frontend integration!
