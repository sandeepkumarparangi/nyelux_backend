#!/bin/bash

echo "=== Safe Database Migration Script ==="
echo "This script will add missing columns and tables without dropping existing data"
echo ""

# Activate virtual environment
source venv/bin/activate

echo "1. Checking current database status..."
psql -d nyelux_development -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'users' LIMIT 5;" 2>/dev/null || echo "Users table doesn't exist yet"

echo ""
echo "2. Checking Alembic migration history..."
alembic current 2>/dev/null || echo "No migrations applied yet"

echo ""
echo "3. Creating migration for missing columns and tables..."
alembic revision --autogenerate -m "add_sso_and_vendor_columns_to_users"

echo ""
echo "4. Review the generated migration file..."
echo "The migration file has been created. Please review it before applying."
echo "Migration files are in: alembic/versions/"
ls -la alembic/versions/*.py 2>/dev/null | tail -1

echo ""
echo "5. Apply the migration? (y/n)"
read -r response
if [[ "$response" == "y" ]]; then
    echo "Applying migrations..."
    alembic upgrade head
    echo "✅ Migrations applied successfully!"
else
    echo "⚠️  Migrations not applied. Run 'alembic upgrade head' when ready."
fi

echo ""
echo "6. Final database status:"
alembic current

echo ""
echo "=== Done ==="
