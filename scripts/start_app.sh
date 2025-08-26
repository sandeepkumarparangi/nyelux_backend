#!/bin/bash
# Start the Nyelux backend application with proper checks

echo "============================================================"
echo "NYELUX BACKEND STARTUP SCRIPT"
echo "============================================================"

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "❌ Virtual environment not activated!"
    echo "Please run: source venv/bin/activate"
    exit 1
fi

# Kill any existing processes on port 8000
echo "Checking for existing processes on port 8000..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true

# Check required services
echo ""
echo "Checking required services..."

# Check PostgreSQL
if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo "✅ PostgreSQL is running"
else
    echo "❌ PostgreSQL is not running"
    echo "Please start PostgreSQL first"
    exit 1
fi

# Check Redis
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is running"
else
    echo "❌ Redis is not running"
    echo "Please start Redis first"
    exit 1
fi

# Check environment file
if [ ! -f .env ]; then
    echo "❌ .env file not found"
    echo "Please create .env file from .env.example"
    exit 1
else
    echo "✅ Environment file found"
fi

# Run startup checks
echo ""
echo "Running startup checks..."
python scripts/check_startup.py

if [ $? -ne 0 ]; then
    echo "❌ Startup checks failed"
    exit 1
fi

# Start the application
echo ""
echo "============================================================"
echo "Starting Nyelux Backend..."
echo "API: http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
echo "Press Ctrl+C to stop"
echo "============================================================"
echo ""

# Start with auto-reload for development
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
