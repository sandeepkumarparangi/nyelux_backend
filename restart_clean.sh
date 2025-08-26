#!/bin/bash

echo "Stopping existing server..."
pkill -f "uvicorn src.main:app" || true
sleep 2

echo "Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "Activating virtual environment..."
source venv/bin/activate

echo "Starting server..."
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
