#!/usr/bin/env python3
"""Check and fix database migration state"""
import os
import sys
import psycopg2
from psycopg2 import sql
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database connection parameters
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "nyelux_development"
DB_USER = "postgres"
DB_PASSWORD = "password"

def check_alembic_version_table():
    """Check if alembic_version table exists and its contents"""
    conn = None
    try:
        # Connect to the database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = conn.cursor()
        
        # Check if alembic_version table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'alembic_version'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print("✓ alembic_version table exists")
            
            # Get current version(s)
            cursor.execute("SELECT version_num FROM alembic_version;")
            versions = cursor.fetchall()
            
            if versions:
                print(f"\nCurrent migration version(s) in database:")
                for version in versions:
                    print(f"  - {version[0]}")
            else:
                print("\n⚠ No migration versions found in alembic_version table")
        else:
            print("✗ alembic_version table does not exist")
            print("  This means no migrations have been applied yet.")
        
        # Check if any of our tables exist
        print("\nChecking for existing tables...")
        tables_to_check = ['users', 'organizations', 'gudid_devices', 'vendor_devices']
        
        for table in tables_to_check:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                );
            """, (table,))
            exists = cursor.fetchone()[0]
            print(f"  - {table}: {'✓ exists' if exists else '✗ does not exist'}")
        
        cursor.close()
        return table_exists, versions if table_exists else []
        
    except Exception as e:
        print(f"Error checking database: {e}")
        return False, []
    finally:
        if conn:
            conn.close()

def remove_redundant_migration():
    """Remove the redundant encrypted MFA migration file"""
    migration_file = "alembic/versions/c3d4e5f6a7b8_add_encrypted_mfa_fields.py"
    full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), migration_file)
    
    if os.path.exists(full_path):
        print(f"\nRemoving redundant migration file: {migration_file}")
        os.remove(full_path)
        print("✓ Migration file removed")
        return True
    else:
        print(f"\n⚠ Migration file not found: {migration_file}")
        return False

def main():
    """Main function"""
    print("=" * 60)
    print("DATABASE MIGRATION STATE CHECK")
    print("=" * 60)
    
    # Check database state
    table_exists, versions = check_alembic_version_table()
    
    # Remove redundant migration
    print("\n" + "=" * 60)
    print("FIXING MIGRATION ISSUES")
    print("=" * 60)
    
    removed = remove_redundant_migration()
    
    # Provide recommendations
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    
    if not table_exists or not versions:
        print("\n1. The database has no migration history.")
        print("2. The redundant migration has been removed.")
        print("3. You can now run: alembic upgrade head")
        print("\nThis will apply all migrations in order:")
        print("  - 64df3531058a_initial_complete_schema.py")
        print("  - b2c3d4e5f6a7_add_missing_billing_tables.py")
    else:
        print("\n1. The database has existing migrations.")
        print("2. The redundant migration has been removed.")
        print("3. Check if all migrations are applied with: alembic current")
        print("4. If needed, run: alembic upgrade head")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
