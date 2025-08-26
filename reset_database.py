#!/usr/bin/env python3
"""
Reset and reinitialize the database to fix relationship issues.
This will drop and recreate all tables with proper relationships.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from src.db.session import get_sync_engine
from src.db.base_class import Base
from src.core.config import settings

# Import ALL models to ensure relationships are registered
from src.db.models import *

async def reset_database():
    """Drop and recreate all tables with proper relationships."""
    
    print("⚠️  WARNING: This will DROP all tables and recreate them!")
    print(f"Database: {settings.POSTGRES_DB}")
    
    if settings.ENVIRONMENT == "production":
        print("❌ Cannot reset production database!")
        return
    
    response = input("Are you sure you want to continue? (yes/no): ")
    if response.lower() != "yes":
        print("Aborted.")
        return
    
    engine = get_sync_engine()
    
    try:
        # Drop all tables
        print("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        print("✅ All tables dropped")
        
        # Create all tables with proper relationships
        print("Creating tables with correct relationships...")
        Base.metadata.create_all(bind=engine)
        print("✅ All tables created successfully")
        
        # Verify tables exist
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            
            print(f"\n✅ Created {len(tables)} tables:")
            for table in tables:
                print(f"   - {table}")
        
        print("\n✅ Database reset complete!")
        print("You can now run: python run.py")
        
    except Exception as e:
        print(f"❌ Error resetting database: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    asyncio.run(reset_database())
