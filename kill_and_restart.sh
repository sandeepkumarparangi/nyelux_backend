#!/bin/bash

echo "=== FORCE KILL AND RESTART ==="

# 1. KILL EVERYTHING
echo "Killing all Python/Uvicorn processes..."
pkill -9 -f python
pkill -9 -f uvicorn
lsof -ti:8000 | xargs kill -9 2>/dev/null
sleep 3

# 2. Clear ALL Python cache
echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
find . -name "*.pyo" -delete 2>/dev/null

# 3. Test the fix works
echo "Testing track-search endpoint..."
cd /Users/nehamchangappa/Downloads/Nyelux\ Beta/nyelux-backend-beta
source venv/bin/activate

# Start server in background
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

# Wait for server to start
echo "Waiting for server to start..."
sleep 5

# Test the endpoint
echo "Testing track-search with curl..."
curl -X POST http://localhost:8000/api/v1/public/track-search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "results_shown": 5}' \
  -w "\nHTTP Status: %{http_code}\n"

echo ""
echo "Server PID: $SERVER_PID"
echo "Server is running at http://localhost:8000"
echo "API docs at http://localhost:8000/docs"
echo ""
echo "To stop: kill $SERVER_PID"
