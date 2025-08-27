#!/bin/bash
# Stop the application
pkill -f "gunicorn" || true
pkill -f "python.*app.py" || true

# Wait for processes to stop
sleep 3
