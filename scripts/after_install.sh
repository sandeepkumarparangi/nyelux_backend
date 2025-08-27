#!/bin/bash
cd /var/www/myapp

# Activate virtual environment and install dependencies
source /var/www/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Set environment variable
echo 'export ENVIRONMENT=production' >> /home/ec2-user/.bashrc
