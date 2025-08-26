#!/bin/bash

cd /Users/nehamchangappa/Downloads/Nyelux\ Beta/nyelux-backend-beta
source venv/bin/activate

echo "Starting Nyelux backend application..."
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 2>&1
