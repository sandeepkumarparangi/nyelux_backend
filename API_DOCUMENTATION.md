# Nyelux Public API Documentation

## Base URL
```
Production: https://api.nyelux.com
Development: http://localhost:8000
```

## Public Search & Q&A APIs

### Version 2 - Basic Typeahead (`/api/v1/public/v2`)

#### 1. Typeahead Search
Fast device search for autocomplete functionality.

**Endpoint:** `GET /api/v1/public/v2/typeahead`

**Parameters:**
- `q` (string, required): Search query (min 2 chars)
- `limit` (integer, optional): Max results (1-20, default 10)

**Response:**
```json
{
  "query": "infusion",
  "suggestions": [
    {
      "id": "00889842001234",
      "display_name": "Infusion Pump Model X200",
      "manufacturer": "Medtronic",
      "category": "II",
      "match_type": "device_name",
      "confidence": 0.95
    }
  ],
  "total_found": 150,
  "response_time_ms": 45.2,
  "cached": false
}
```

**Performance:** <50ms response time

---

### Q&A API (`/api/v1/public/qa`)

#### 1. Ask Device Question
Ask questions about FDA medical devices. Limited to 5 questions for anonymous users.

**Endpoint:** `POST /api/v1/public/qa/devices/{device_id}/ask`

**Request Body:**
```json
{
  "device_id": "00889842001234",
  "question": "Is this device MRI safe?",
  "session_id": "optional-session-id"
}
```

**Response:**
```json
{
  "device_id": "00889842001234",
  "device_name": "Infusion Pump Model X200",
  "question": "Is this device MRI safe?",
  "answer": "MRI Safety Status: MR Conditional. This device is safe under specific MR conditions. Check device labeling for details.",
  "sources": ["FDA MRI Safety Information"],
  "questions_remaining": 4,
  "requires_signup": false,
  "confidence": 1.0
}
```

**Question Limit:** 5 free questions per session

---

#### 2. Get Device Information
Get device information with different levels based on authentication.

**Endpoint:** `GET /api/v1/public/qa/devices/{device_id}/info`

**Parameters:**
- `authenticated` (boolean): Whether user is authenticated

**Anonymous Response (limited fields):**
```json
{
  "primary_di": "00889842001234",
  "device_name": "Infusion Pump Model X200",
  "manufacturer_name": "Medtronic",
  "device_class": "II",
  "mri_safety": "MR Conditional",
  "company_contact_info": "Sign up to view manufacturer contact information and support details"
}
```

**Authenticated Response (full info):**
```json
{
  "primary_di": "00889842001234",
  "device_name": "Infusion Pump Model X200",
  "manufacturer_name": "Medtronic",
  "company_contact_info": {
    "support": "Vendor support channels",
    "website": "Company website and resources",
    "phone": "+1-800-XXX-XXXX",
    "email": "support@medtronic.com"
  },
  // ... all 70+ FDA fields
}
```

---

#### 3. Check Session Status
Check how many questions have been asked in current session.

**Endpoint:** `GET /api/v1/public/qa/session/status`

**Response:**
```json
{
  "session_id": "abc123def456",
  "questions_asked": 3,
  "questions_remaining": 2,
  "limit": 5,
  "requires_signup": false
}
```

---

#### 4. Record Signup Prompt
Track when users are prompted to sign up.

**Endpoint:** `POST /api/v1/public/qa/signup-prompt`

**Parameters:**
- `reason` (string): Reason for prompt (e.g., "question_limit_reached")
- `device_id` (string, optional): Device being viewed
- `session_id` (string, optional): Session ID

**Response:**
```json
{
  "message": "Signup prompt recorded",
  "signup_url": "/auth/register",
  "benefits": [
    "Unlimited device questions",
    "Full manufacturer contact information",
    "Technical documentation access",
    "Support ticket creation",
    "Device comparison tools",
    "Export capabilities"
  ]
}
```

---

#### 2. Device Details
Get public device information.

**Endpoint:** `GET /api/v1/public/v2/devices/{primary_di}`

**Response:**
```json
{
  "primary_di": "00889842001234",
  "device_name": "Infusion Pump Model X200",
  "manufacturer_name": "Medtronic",
  "brand_name": "Medtronic",
  "model_number": "X200",
  "device_class": "II",
  "device_description": "Programmable infusion pump...",
  "gmdn_terms": "Infusion pump, programmable",
  "mri_safety": "MR Conditional",
  "sterile": false,
  "single_use": false,
  "implantable": false,
  "life_supporting": true,
  "rx_required": true
}
```

---

### Version 3 - Advanced Search (`/api/v1/public/v3`)

#### 1. Advanced Search with Filters
Powerful search with filtering and intelligent ranking.

**Endpoint:** `POST /api/v1/public/v3/search/advanced`

**Request Body:**
```json
{
  "query": "infusion pump",
  "limit": 10,
  "filters": {
    "device_class": "II",
    "mri_safety": "MR Safe",
    "sterile": true,
    "life_supporting": true
  }
}
```

**Response:**
```json
{
  "query": "infusion pump",
  "results": [
    {
      "id": "00889842001234",
      "device_name": "Smart Infusion System",
      "manufacturer": "B. Braun",
      "brand": "Space",
      "model": "Plus",
      "class": "II",
      "description": "Advanced volumetric infusion pump...",
      "gmdn_terms": "Infusion pump, volumetric",
      "mri_safety": "MR Safe",
      "sterile": false,
      "single_use": false,
      "life_supporting": true,
      "match_field": "device_name",
      "relevance_score": 0.98
    }
  ],
  "total_found": 25,
  "filters_applied": {
    "device_class": "II",
    "mri_safety": "MR Safe"
  },
  "response_time_ms": 67.3,
  "cached": false,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Available Filters:**
- `device_class`: I, II, or III
- `mri_safety`: MR Safe, MR Conditional, MR Unsafe
- `sterile`: true/false
- `single_use`: true/false
- `implantable`: true/false
- `life_supporting`: true/false
- `rx_required`: true/false

---

#### 2. Search Suggestions
Get autocomplete suggestions from multiple sources.

**Endpoint:** `GET /api/v1/public/v3/search/suggestions`

**Parameters:**
- `partial` (string, required): Partial search term (min 1 char)

**Response:**
```json
{
  "devices": [
    "Infusion Pump Model X200",
    "Infusion Set Sterile"
  ],
  "manufacturers": [
    "Infusion Technologies Inc",
    "InfuSystem Holdings"
  ],
  "popular_searches": [
    "infusion pump programming",
    "infusion catheter"
  ],
  "categories": [
    "infusion pumps"
  ]
}
```

---

#### 3. Search Analytics
Get search performance metrics and popular queries.

**Endpoint:** `GET /api/v1/public/v3/search/analytics`

**Response:**
```json
{
  "total_unique_queries": 1543,
  "total_searches": 8921,
  "top_queries": [
    {
      "query": "infusion pump",
      "count": 234,
      "cache_tier": "hot"
    },
    {
      "query": "catheter",
      "count": 189,
      "cache_tier": "hot"
    }
  ],
  "cache_stats": {
    "redis_available": true,
    "hot_cache_ttl": 300,
    "warm_cache_ttl": 1800,
    "cold_cache_ttl": 3600
  }
}
```

---

#### 4. Trending Searches
Get currently trending search terms.

**Endpoint:** `GET /api/v1/public/v3/search/trending`

**Parameters:**
- `limit` (integer, optional): Number of results (1-50, default 10)

**Response:**
```json
{
  "trending": [
    {
      "query": "covid ventilator",
      "count": 450,
      "cache_tier": "hot"
    }
  ],
  "period": "current_session",
  "total_searches": 3421
}
```

---

#### 5. Browse by Category
Browse devices without search query.

**Endpoint:** `GET /api/v1/public/v3/devices/browse`

**Parameters:**
- `category` (string, optional): GMDN category
- `device_class` (string, optional): I, II, or III
- `manufacturer` (string, optional): Manufacturer name
- `offset` (integer, optional): Pagination offset (default 0)
- `limit` (integer, optional): Results per page (1-100, default 20)

**Response:**
```json
{
  "devices": [
    {
      "primary_di": "00889842001234",
      "device_name": "Surgical Instrument Set",
      "manufacturer_name": "Stryker",
      "device_class": "II",
      "gmdn_terms": "Surgical instruments"
    }
  ],
  "offset": 0,
  "limit": 20,
  "has_more": true
}
```

---

## Performance Metrics

| Endpoint | Target | P95 | P99 |
|----------|--------|-----|-----|
| Typeahead Search | <50ms | 45ms | 68ms |
| Device Details | <100ms | 85ms | 120ms |
| Advanced Search | <100ms | 92ms | 145ms |
| Suggestions | <30ms | 25ms | 40ms |
| Browse | <150ms | 130ms | 180ms |

## Rate Limits

| Tier | Requests/Hour | Burst |
|------|---------------|-------|
| Anonymous | 1000 | 20/sec |
| Authenticated | 10000 | 100/sec |
| Premium | Unlimited | 500/sec |

## Caching Strategy

1. **Hot Cache** (5 min): Queries with >10 searches
2. **Warm Cache** (30 min): Queries with 3-10 searches  
3. **Cold Cache** (1 hour): Queries with <3 searches

## Error Responses

```json
{
  "detail": "Error message",
  "status": 400,
  "type": "validation_error",
  "errors": [
    {
      "field": "query",
      "message": "Field required"
    }
  ]
}
```

## Status Codes

- `200 OK`: Success
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Device not found
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily down

## SDK Examples

### JavaScript/TypeScript
```javascript
// Typeahead search
const response = await fetch(
  'https://api.nyelux.com/api/v1/public/v2/typeahead?q=pump&limit=10'
);
const data = await response.json();

// Advanced search
const searchResponse = await fetch(
  'https://api.nyelux.com/api/v1/public/v3/search/advanced',
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: 'infusion pump',
      filters: { device_class: 'II' }
    })
  }
);
```

### Python
```python
import httpx

# Typeahead search
async with httpx.AsyncClient() as client:
    response = await client.get(
        'https://api.nyelux.com/api/v1/public/v2/typeahead',
        params={'q': 'pump', 'limit': 10}
    )
    data = response.json()

# Advanced search
async with httpx.AsyncClient() as client:
    response = await client.post(
        'https://api.nyelux.com/api/v1/public/v3/search/advanced',
        json={
            'query': 'infusion pump',
            'filters': {'device_class': 'II'}
        }
    )
```

## Database

- **Provider**: Supabase (PostgreSQL)
- **Records**: 4.78M FDA medical devices
- **Update Frequency**: Daily FDA sync
- **Fields**: 70+ FDA GUDID fields

## Support

- Documentation: https://docs.nyelux.com
- API Status: https://status.nyelux.com
- Support: api-support@nyelux.com

---

**Version:** 3.0  
**Last Updated:** January 2024  
**Status:** Production Ready
