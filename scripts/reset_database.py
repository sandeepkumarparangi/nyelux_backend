#!/usr/bin/env python
"""Reset database and run migrations from scratch."""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def reset_database():
    """Drop all tables and reset Alembic."""
    try:
        from src.db.session import engine
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession
        
        print("⚠️  WARNING: This will drop ALL tables in the database!")
        response = input("Are you sure you want to continue? (yes/no): ")
        
        if response.lower() != 'yes':
            print("❌ Operation cancelled.")
            return False
        
        async with AsyncSession(engine) as db:
            print("\n🔧 Dropping all tables...")
            
            # Get all table names
            result = await db.execute(text("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY tablename;
            """))
            tables = [row[0] for row in result]
            
            # Drop all tables
            for table in tables:
                if table != 'alembic_version':  # Keep alembic_version for now
                    print(f"  Dropping table: {table}")
                    await db.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            
            # Drop alembic_version last
            print("  Dropping table: alembic_version")
            await db.execute(text('DROP TABLE IF EXISTS alembic_version CASCADE'))
            
            await db.commit()
            print("✅ All tables dropped successfully!")
            
        return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def verify_clean_state():
    """Verify database is clean."""
    from src.db.session import engine
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    
    async with AsyncSession(engine) as db:
        result = await db.execute(text("""
            SELECT COUNT(*) FROM pg_tables 
            WHERE schemaname = 'public'
        """))
        count = result.scalar()
        
        if count == 0:
            print("✅ Database is clean - no tables exist")
            return True
        else:
            print(f"⚠️  Database still has {count} tables")
            return False

if __name__ == "__main__":
    print("🗑️  Database Reset Script\n")
    
    success = asyncio.run(reset_database())
    if success:
        print("\n🔍 Verifying clean state...")
        asyncio.run(verify_clean_state())
        print("\n✅ Database reset complete!")
        print("You can now run: alembic upgrade head")
    else:
        print("\n❌ Database reset failed!")
        sys.exit(1)
