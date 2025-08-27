#!/bin/bash
# Stop the application if it's running
pkill -f "gunicorn" || true
pkill -f "python.*app.py" || true

# Clean up previous deployment
rm -rf /var/www/myapp/*

# Create directories if they don't exist
mkdir -p /var/www/myapp
mkdir -p /var/log/myapp
chown -R ec2-user:ec2-user /var/www/myapp
chown -R ec2-user:ec2-user /var/log/myapp

# Create virtual environment if it doesn't exist
if [ ! -d "/var/www/venv" ]; then
    python3 -m venv /var/www/venv
    chown -R ec2-user:ec2-user /var/www/venv
fi
