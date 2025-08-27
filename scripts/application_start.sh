#!/bin/bash
cd /var/www/myapp

# Activate virtual environment
source /var/www/venv/bin/activate

# Start the application with gunicorn
nohup gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 60 wsgi:app > /var/log/myapp/gunicorn.log 2>&1 &

# Wait a moment for the application to start
sleep 5
