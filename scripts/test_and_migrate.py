#!/usr/bin/env python3
"""Test database connection and apply migrations"""
import os
import sys
import asyncio
import subprocess
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import settings

def test_database_connection():
    """Test if we can connect to the database"""
    try:
        # Create a synchronous engine for testing
        engine = create_engine(settings.SYNC_DATABASE_URL)
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
            
            # Check if alembic_version table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'alembic_version'
                );
            """))
            alembic_exists = result.scalar()
            
            if alembic_exists:
                # Get current version
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                versions = result.fetchall()
                if versions:
                    print(f"✓ Current migration version: {versions[0][0]}")
                else:
                    print("⚠ No migration version found in alembic_version table")
            else:
                print("⚠ No alembic_version table found - migrations have not been run")
                
        return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False

def run_alembic_command(command, *args):
    """Run an alembic command and capture output"""
    cmd = ["alembic", command] + list(args)
    print(f"\nRunning: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(f"Error: {result.stderr}")
            
        return result.returncode == 0
    except Exception as e:
        print(f"Failed to run command: {e}")
        return False

def main():
    """Main function"""
    print("=" * 60)
    print("DATABASE MIGRATION TEST")
    print("=" * 60)
    
    # Test database connection
    if not test_database_connection():
        print("\n✗ Cannot proceed without database connection")
        return 1
    
    # Check current migration status
    print("\n" + "-" * 60)
    print("CHECKING MIGRATION STATUS")
    print("-" * 60)
    
    # Check current revision
    run_alembic_command("current")
    
    # Check available heads
    print("\nChecking migration heads...")
    run_alembic_command("heads")
    
    # Show migration history
    print("\nMigration history:")
    run_alembic_command("history")
    
    # Ask user if they want to apply migrations
    print("\n" + "-" * 60)
    print("MIGRATION OPTIONS")
    print("-" * 60)
    print("\n1. Apply all migrations (alembic upgrade head)")
    print("2. Show what would be done (alembic upgrade head --sql)")
    print("3. Exit without changes")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        print("\nApplying all migrations...")
        if run_alembic_command("upgrade", "head"):
            print("\n✓ Migrations applied successfully!")
            
            # Show new status
            print("\nNew migration status:")
            run_alembic_command("current")
        else:
            print("\n✗ Migration failed!")
            return 1
            
    elif choice == "2":
        print("\nShowing SQL that would be executed...")
        run_alembic_command("upgrade", "head", "--sql")
        
    else:
        print("\nExiting without changes.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
