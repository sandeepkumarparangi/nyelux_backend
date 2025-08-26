#!/bin/bash

# Quick restart script
echo "Restarting Nyelux Backend Server..."

# Kill any existing uvicorn processes
pkill -f uvicorn || true
sleep 1

# Navigate to the project directory
cd "/Users/nehamchangappa/Downloads/Nyelux Beta/nyelux-backend-beta"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start the server
echo "Starting server..."
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 &

# Wait for server to start
sleep 3

# Test the health endpoint
echo "Testing server health..."
curl -s http://localhost:8000/health | python3 -m json.tool

echo ""
echo "Server restarted! Backend is running at http://localhost:8000"
echo "API docs available at: http://localhost:8000/docs"
echo ""
echo "To test the track-search endpoint, run:"
echo "  python3 test_track_search_fixed.py"
echo "  or"
echo "  chmod +x test_track_api.sh && ./test_track_api.sh"
