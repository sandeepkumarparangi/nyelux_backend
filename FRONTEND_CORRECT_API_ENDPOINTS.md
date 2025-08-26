# 🚀 NYELUX VENDOR API - CORRECT ENDPOINTS ONLY

## ⚠️ IMPORTANT: Use These URLs, NOT the Old Ones!

The frontend is calling OLD endpoints that don't work. Here are the CORRECT endpoints to use:

---

## ✅ CORRECT ENDPOINTS (USE THESE!)

### 1. **Search for Manufacturers**
```
GET /api/v1/vendor/search?q=intuitive
```
✅ **CORRECT** - This works!
❌ **WRONG** - `/api/v1/vendor/intuitive-surgical-inc` (OLD endpoint, broken)

### 2. **Get Vendor Page by Name**
```
GET /api/v1/vendor/by-name/INTUITIVE%20SURGICAL%20INC
```
✅ **CORRECT** - Use exact name from search
❌ **WRONG** - `/api/v1/vendor/intuitive-surgical-inc` (OLD endpoint)

### 3. **Get Devices**
```
GET /api/v1/vendor/by-name/INTUITIVE%20SURGICAL%20INC/devices
```
✅ **CORRECT** - Works with manufacturer name
❌ **WRONG** - Any slug-based endpoint

### 4. **Get Device Info**
```
GET /api/v1/vendor/device/{device_id}/info
```
✅ **CORRECT** - Single endpoint for all device data

### 5. **Chat About Device**
```
POST /api/v1/vendor/device/{device_id}/chat
```
✅ **CORRECT** - AI chat with real FDA data

---

## 🔧 COMPLETE WORKING EXAMPLE

### Step 1: Search
```bash
curl "http://localhost:8000/api/v1/vendor/search?q=intuitive"
```

**Response:**
```json
{
  "manufacturers": [
    {
      "id": "abc123def456",
      "name": "INTUITIVE SURGICAL INC",
      "encoded_name": "SU5UVUlUSVZFIFNVUkdJQ0FMIElOQw==",
      "device_count": 245,
      "url": "/vendor/by-id/abc123def456"
    }
  ]
}
```

### Step 2: Load Vendor Page (USE THE NAME!)
```bash
# Use the exact name from search results
curl "http://localhost:8000/api/v1/vendor/by-name/INTUITIVE%20SURGICAL%20INC"
```

### Step 3: Get Devices
```bash
curl "http://localhost:8000/api/v1/vendor/by-name/INTUITIVE%20SURGICAL%20INC/devices?page=1&limit=20"
```

### Step 4: Device Info
```bash
curl "http://localhost:8000/api/v1/vendor/device/00888116002226/info"
```

### Step 5: Chat
```bash
curl -X POST "http://localhost:8000/api/v1/vendor/device/00888116002226/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is this device used for?"}'
```

---

## 🎨 FRONTEND IMPLEMENTATION

### CORRECT Implementation:
```javascript
// 1. Search for manufacturers
async function searchManufacturers(query) {
  const response = await fetch(
    `/api/v1/vendor/search?q=${encodeURIComponent(query)}`
  );
  return response.json();
}

// 2. Load vendor page - USE EXACT NAME
async function loadVendorPage(manufacturerName) {
  // DO NOT convert to slug!
  // USE the exact name from search results
  const encodedName = encodeURIComponent(manufacturerName);
  const response = await fetch(
    `/api/v1/vendor/by-name/${encodedName}`
  );
  return response.json();
}

// 3. Example usage
const results = await searchManufacturers("intuitive");
const firstManufacturer = results.manufacturers[0];

// USE THE NAME, NOT A SLUG!
const vendorPage = await loadVendorPage(firstManufacturer.name);
// This will call: /api/v1/vendor/by-name/INTUITIVE%20SURGICAL%20INC
```

### WRONG Implementation (Don't do this!):
```javascript
// ❌ WRONG - Don't create slugs
const slug = manufacturerName.toLowerCase().replace(/\s+/g, '-');
const vendorPage = await fetch(`/api/v1/vendor/${slug}`); // BROKEN!

// ❌ WRONG - Don't use old endpoints
const vendorPage = await fetch('/api/v1/vendor/intuitive-surgical-inc'); // ERROR 500!
```

---

## 📝 URL ENCODING REFERENCE

When the manufacturer name has spaces or special characters:

| Manufacturer Name | URL Encoded |
|------------------|-------------|
| INTUITIVE SURGICAL INC | INTUITIVE%20SURGICAL%20INC |
| STRYKER SUSTAINABILITY SOLUTIONS, INC. | STRYKER%20SUSTAINABILITY%20SOLUTIONS%2C%20INC. |
| BD (BECTON, DICKINSON AND COMPANY) | BD%20%28BECTON%2C%20DICKINSON%20AND%20COMPANY%29 |
| 3M COMPANY | 3M%20COMPANY |

---

## 🐛 DEBUGGING TIPS

### If you get a 500 error:
1. **Check the URL** - Are you using the OLD endpoint?
2. **Check the name** - Are you using the exact name from search?
3. **Check encoding** - Are spaces encoded as %20?

### If you get a 404:
1. **Search first** - Get the exact manufacturer name
2. **Don't guess** - Use the name exactly as returned

### Common Mistakes:
- ❌ Using slugs (intuitive-surgical-inc)
- ❌ Using old endpoints (/vendor/{slug})
- ❌ Lowercasing names
- ❌ Removing special characters

### Correct Approach:
- ✅ Use exact names from search
- ✅ Use new endpoints (/vendor/by-name/{name})
- ✅ Keep original case
- ✅ URL encode spaces and special chars

---

## 🔥 QUICK TEST

Test these RIGHT NOW to see the difference:

```bash
# ❌ WRONG - This gives 500 error
curl "http://localhost:8000/api/v1/vendor/intuitive-surgical-inc"

# ✅ CORRECT - This works!
curl "http://localhost:8000/api/v1/vendor/by-name/INTUITIVE%20SURGICAL%20INC"
```

---

## 📊 API RESPONSE TIMES

With the new endpoints:
- Search: <500ms
- Vendor Page: <1s
- Device List: <1s
- Device Info: <500ms
- Chat: <2s

---

## 🎯 SUMMARY

### The Problem:
- Frontend is calling OLD endpoints like `/api/v1/vendor/intuitive-surgical-inc`
- These try to access database tables that don't exist
- They have relationship errors with User/DeviceDocument models

### The Solution:
- Use NEW endpoints: `/api/v1/vendor/by-name/{manufacturer_name}`
- Use exact manufacturer names from search results
- Don't create slugs, use names directly
- Everything is generated from Supabase FDA data

### Key Points:
1. **NO SLUGS** - Use manufacturer names directly
2. **URL ENCODE** - Spaces become %20
3. **EXACT NAMES** - Use what search returns
4. **NEW ENDPOINTS** - /vendor/by-name/ not /vendor/

---

## 📱 FRONTEND CHANGES NEEDED

Replace all vendor URL generation:

### OLD (Broken):
```javascript
const vendorUrl = `/vendor/${company.name.toLowerCase().replace(/\s+/g, '-')}`;
```

### NEW (Working):
```javascript
const vendorUrl = `/vendor/by-name/${encodeURIComponent(company.name)}`;
```

That's it! Just change the URL pattern and everything will work!
