#!/bin/bash

echo "=== Database Status Check ==="
echo ""

# Check what tables exist
echo "1. Existing tables in database:"
psql -d nyelux_development -c "\dt" 2>/dev/null || echo "Database doesn't exist or connection failed"

echo ""
echo "2. Checking if users table exists:"
psql -d nyelux_development -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position;" 2>/dev/null || echo "Users table doesn't exist"

echo ""
echo "3. Checking if organizations table exists (needed for foreign keys):"
psql -d nyelux_development -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'organizations' LIMIT 5;" 2>/dev/null || echo "Organizations table doesn't exist"

echo ""
echo "=== End of Status Check ==="
