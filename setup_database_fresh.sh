#!/bin/bash

echo "=== NYELUX Database Setup Script ==="
echo "This script will set up your database with all required tables"
echo ""

# Activate virtual environment
source venv/bin/activate

# First, let's drop and recreate the database to start fresh (DEVELOPMENT ONLY)
echo "⚠️  WARNING: This will DROP and RECREATE the database!"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

echo "1. Dropping existing database..."
dropdb nyelux_development 2>/dev/null || true

echo "2. Creating fresh database..."
createdb nyelux_development

echo "3. Initializing Alembic (if needed)..."
if [ ! -f "alembic.ini" ]; then
    alembic init alembic
fi

echo "4. Creating initial migration..."
# Remove existing migrations to start fresh
rm -f alembic/versions/*.py 2>/dev/null || true

# Create a new migration with all tables
alembic revision --autogenerate -m "initial_complete_schema_with_all_tables"

echo "5. Applying migration to database..."
alembic upgrade head

echo "6. Verifying tables were created..."
psql -d nyelux_development -c "\dt" | head -20

echo ""
echo "=== Database Setup Complete ==="
echo "All tables should now be created. You can restart the server."
