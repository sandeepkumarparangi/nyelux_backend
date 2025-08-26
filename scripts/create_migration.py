#!/usr/bin/env python
"""Create new migration that properly handles existing schema."""
import subprocess
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_fresh_migration():
    """Create a new migration from current models."""
    print("🔧 Creating fresh migration from current models...\n")
    
    try:
        # First, remove the problematic migration
        migration_file = "alembic/versions/64df3531058a_initial_complete_schema.py"
        if os.path.exists(migration_file):
            os.remove(migration_file)
            print(f"✅ Removed old migration: {migration_file}")
        
        # Generate new migration
        print("\n📝 Generating new migration...")
        result = subprocess.run(
            ["alembic", "revision", "--autogenerate", "-m", "initial_schema"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Migration created successfully!")
            print(f"Output: {result.stdout}")
            
            # Find the new migration file
            import glob
            new_migrations = glob.glob("alembic/versions/*_initial_schema.py")
            if new_migrations:
                print(f"\n📄 New migration file: {new_migrations[0]}")
                print("\nYou can now run: alembic upgrade head")
        else:
            print(f"❌ Error creating migration: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🎯 Migration Creation Script\n")
    
    # First check if we need to update alembic state
    import asyncio
    from check_db_state import check_database_state, fix_alembic_state
    
    print("Checking current database state...")
    tables = asyncio.run(check_database_state())
    
    if 'gudid_devices' in tables and 'alembic_version' not in tables:
        print("\n⚠️  Tables exist but Alembic not initialized. Creating alembic_version table...")
        # Create alembic_version table
        from src.db.session import engine
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession
        
        async def create_alembic_table():
            async with AsyncSession(engine) as db:
                await db.execute(text("""
                    CREATE TABLE IF NOT EXISTS alembic_version (
                        version_num VARCHAR(32) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    );
                """))
                await db.commit()
        
        asyncio.run(create_alembic_table())
        print("✅ Created alembic_version table")
    
    # Now create the migration
    if create_fresh_migration():
        print("\n✅ Migration setup complete!")
    else:
        print("\n❌ Migration setup failed!")
        sys.exit(1)
