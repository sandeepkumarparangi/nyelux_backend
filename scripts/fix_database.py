#!/usr/bin/env python
"""
Fix database and migration issues.
This script handles the case where tables already exist.
"""
import asyncio
import sys
import os
import subprocess

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def check_and_fix_database():
    """Check database state and fix issues."""
    from src.db.session import engine
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    
    print("🔍 Checking database state...\n")
    
    async with AsyncSession(engine) as db:
        # Check if alembic_version table exists
        result = await db.execute(text("""
            SELECT EXISTS (
                SELECT FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename = 'alembic_version'
            );
        """))
        alembic_exists = result.scalar()
        
        # Check if other tables exist
        result = await db.execute(text("""
            SELECT COUNT(*) FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename != 'alembic_version';
        """))
        table_count = result.scalar()
        
        print(f"📊 Database status:")
        print(f"  - Alembic version table: {'EXISTS' if alembic_exists else 'NOT FOUND'}")
        print(f"  - Other tables: {table_count}")
        
        if table_count > 0 and not alembic_exists:
            print("\n⚠️  Tables exist but Alembic is not initialized!")
            print("Creating alembic_version table...")
            
            await db.execute(text("""
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(32) NOT NULL,
                    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                );
            """))
            await db.commit()
            print("✅ Created alembic_version table")
            
            # Mark the current state as up-to-date
            print("Stamping current state...")
            result = subprocess.run(
                ["alembic", "stamp", "head"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("✅ Database stamped as current")
            else:
                print(f"❌ Error stamping: {result.stderr}")
                return False
        
        elif table_count == 0:
            print("\n✅ Database is clean. Ready for migrations.")
            
        else:
            print("\n✅ Database and Alembic are properly configured.")
            
            # Check current version
            if alembic_exists:
                result = await db.execute(text("SELECT version_num FROM alembic_version"))
                version = result.scalar()
                if version:
                    print(f"📌 Current migration version: {version}")
    
    return True

async def run_migrations():
    """Run Alembic migrations."""
    print("\n🔧 Running migrations...\n")
    
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✅ Migrations completed successfully!")
        print(result.stdout)
        return True
    else:
        # Check if it's just because tables already exist
        if "already exists" in result.stderr:
            print("ℹ️  Tables already exist. Marking as current...")
            
            # Stamp the database as current
            stamp_result = subprocess.run(
                ["alembic", "stamp", "head"],
                capture_output=True,
                text=True
            )
            
            if stamp_result.returncode == 0:
                print("✅ Database marked as current")
                return True
            else:
                print(f"❌ Error stamping: {stamp_result.stderr}")
                return False
        else:
            print(f"❌ Migration error: {result.stderr}")
            return False

async def verify_tables():
    """Verify all required tables exist."""
    from src.db.session import engine
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    
    print("\n🔍 Verifying tables...\n")
    
    required_tables = [
        'organizations',
        'departments', 
        'users',
        'gudid_devices',
        'vendor_devices',
        'device_documents',
        'device_videos',
        'leads',
        'notes',
        'teams',
        'alembic_version'
    ]
    
    async with AsyncSession(engine) as db:
        result = await db.execute(text("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """))
        existing_tables = [row[0] for row in result]
        
        print("📊 Table verification:")
        for table in required_tables:
            status = "✅" if table in existing_tables else "❌"
            print(f"  {status} {table}")
        
        missing = [t for t in required_tables if t not in existing_tables]
        if missing:
            print(f"\n⚠️  Missing tables: {', '.join(missing)}")
            return False
        else:
            print("\n✅ All required tables exist!")
            return True

async def main():
    """Main function to fix database issues."""
    print("🚀 Nyelux Database Fix Script\n")
    print("This script will ensure your database is properly configured.\n")
    
    try:
        # Step 1: Check and fix database state
        if not await check_and_fix_database():
            print("\n❌ Failed to fix database state")
            return False
        
        # Step 2: Run migrations
        if not await run_migrations():
            print("\n❌ Failed to run migrations")
            return False
        
        # Step 3: Verify tables
        if not await verify_tables():
            print("\n❌ Table verification failed")
            return False
        
        print("\n🎉 Database is ready!")
        print("\nNext steps:")
        print("1. Run: python add_test_data.py")
        print("2. Start server: python start_server.py")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
