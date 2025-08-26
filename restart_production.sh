#!/bin/bash

echo "=== Production-Ready Server Restart ==="
echo ""

# Kill any existing server processes
echo "1. Stopping existing server processes..."
pkill -f "uvicorn" 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 2

# Clear Python cache to ensure our changes are picked up
echo "2. Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true

# Clear any temporary files
echo "3. Clearing temporary files..."
rm -rf .pytest_cache 2>/dev/null || true
rm -rf .mypy_cache 2>/dev/null || true

# Activate virtual environment
echo "4. Activating virtual environment..."
source venv/bin/activate

# Export Python path to avoid import issues
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Start the server with proper configuration
echo "5. Starting server with production settings..."
echo "=================================="
echo "Server starting on: http://localhost:8000"
echo "API Documentation: http://localhost:8000/docs"
echo "Health Check: http://localhost:8000/health"
echo "=================================="
echo ""

# Run with explicit Python path and module
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 --log-level info
