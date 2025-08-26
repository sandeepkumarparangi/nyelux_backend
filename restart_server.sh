#!/bin/bash

echo "=== Complete Server Restart ==="
echo ""

# Kill any existing server processes
echo "1. Stopping existing server processes..."
pkill -f "uvicorn" 2>/dev/null || true
sleep 2

# Clear Python cache to ensure our changes are picked up
echo "2. Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# Activate virtual environment
echo "3. Activating virtual environment..."
source venv/bin/activate

# Restart the server
echo "4. Starting server..."
echo "Server will be available at: http://localhost:8000"
echo "API docs at: http://localhost:8000/docs"
echo ""
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
