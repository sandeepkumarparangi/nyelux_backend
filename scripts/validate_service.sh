#!/bin/bash
# Wait for the application to fully start
sleep 10

# Check if the application is responding
curl -f http://localhost:5000/health || exit 1

echo "Application is running and responding correctly"
