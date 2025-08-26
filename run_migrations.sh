#!/bin/bash

echo "=== Database Migration Script ==="
echo "This script will create and apply all database migrations"
echo ""

# Activate virtual environment
source venv/bin/activate

# First, let's check the current migration status
echo "1. Checking current migration status..."
alembic current

echo ""
echo "2. Creating a new migration for all current models..."
alembic revision --autogenerate -m "add_all_missing_columns_and_tables"

echo ""
echo "3. Applying all pending migrations..."
alembic upgrade head

echo ""
echo "4. Verifying migration status..."
alembic current

echo ""
echo "=== Migration Complete ==="
echo "You can now restart the server."
