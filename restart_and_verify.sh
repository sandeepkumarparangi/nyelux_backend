#!/bin/bash

# Kill any existing processes
echo "Stopping existing server..."
pkill -f uvicorn || true
pkill -f "python.*main:app" || true
sleep 2

# Navigate to project directory
cd "/Users/nehamchangappa/Downloads/Nyelux Beta/nyelux-backend-beta"

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start server in background
echo "Starting server..."
nohup uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 > server.log 2>&1 &

# Wait for server to start
echo "Waiting for server to start..."
sleep 5

# Check if server is running
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ Server started successfully!"
    
    # Now run the verification
    echo ""
    echo "Running Supabase verification..."
    echo "================================"
    python3 verify_real_data.py
    
else
    echo "❌ Server failed to start. Check server.log for errors"
    tail -20 server.log
fi
