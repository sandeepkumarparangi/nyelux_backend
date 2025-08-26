#!/bin/bash

# Test the track-search endpoint with correct data structure

echo "Testing Nyelux Public Track Search Endpoint"
echo "==========================================="

# Test 1: Simple track search
echo -e "\n1. Testing simple track search:"
curl -X POST http://localhost:8000/api/v1/public/track-search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "infusion pump",
    "results_shown": 5
  }'

# Test 2: Track search with all fields
echo -e "\n\n2. Testing track search with all fields:"
curl -X POST http://localhost:8000/api/v1/public/track-search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "medtronic ventilator",
    "results_count": 10,
    "results_shown": 5,
    "search_type": "public",
    "session_id": "test-session-123",
    "filters": {
      "device_class": "II",
      "mri_safety": "Safe"
    },
    "source": "web"
  }'

# Test 3: Multiple searches to trigger lead capture
echo -e "\n\n3. Testing multiple searches (should trigger lead capture after 3):"
SESSION_ID="lead-test-$(date +%s)"

for i in 1 2 3 4; do
  echo -e "\nSearch #$i:"
  curl -X POST http://localhost:8000/api/v1/public/track-search \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": \"search query $i\",
      \"results_count\": 5,
      \"session_id\": \"$SESSION_ID\"
    }"
done

# Test 4: Test public search endpoint (no API key required)
echo -e "\n\n4. Testing public search endpoint:"
curl -X GET "http://localhost:8000/api/v1/public/search?q=infusion%20pump&limit=5"

# Test 5: Test typeahead
echo -e "\n\n5. Testing typeahead:"
curl -X GET "http://localhost:8000/api/v1/public/typeahead?q=med&limit=5"

echo -e "\n\nAll tests completed!"
