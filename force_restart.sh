#!/bin/bash

echo "=== Force Restart Nyelux Backend ==="

# 1. Kill ALL Python processes related to the backend
echo "1. Force killing all Python processes..."
pkill -f "uvicorn" || true
pkill -f "python.*main:app" || true
pkill -f "src.main:app" || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 2

# 2. Clear Python cache
echo "2. Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# 3. Verify the fix is in place
echo "3. Checking if track-search fix is applied..."
if grep -q "Track search events from the frontend" src/api/v1/endpoints/public.py; then
    echo "   ✓ Fix is in the code"
else
    echo "   ✗ Fix is NOT in the code!"
fi

# 4. Start the server with explicit module path
echo "4. Starting server..."
cd /Users/nehamchangappa/Downloads/Nyelux\ Beta/nyelux-backend-beta
source venv/bin/activate

# Use explicit Python path to ensure correct version
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 &

sleep 3

# 5. Test the endpoint
echo "5. Testing track-search endpoint..."
curl -X POST http://localhost:8000/api/v1/public/track-search \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}' \
  -w "\nStatus: %{http_code}\n"

echo ""
echo "Server is running. Check http://localhost:8000/docs"
echo "Press Ctrl+C to stop the server"
