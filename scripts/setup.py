#!/usr/bin/env python
"""
Setup script for Nyelux backend.
Creates database, runs migrations, and optionally creates a super admin user.
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import engine, AsyncSessionLocal
from src.db.models.user import User
from src.db.models.organization import Organization
from src.services.auth_service import auth_service
from src.core.config import settings


async def create_super_admin():
    """Create a super admin user for initial setup"""
    async with AsyncSessionLocal() as db:
        # Check if super admin already exists
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.email == "admin@nyelux.com")
        )
        if result.scalar_one_or_none():
            print("Super admin already exists")
            return
        
        # Create Nyelux organization
        nyelux_org = Organization(
            name="Nyelux",
            type="vendor",
            subdomain="nyelux",
            license_tier="enterprise",
            is_verified=True
        )
        db.add(nyelux_org)
        await db.commit()
        await db.refresh(nyelux_org)
        
        # Create super admin user
        admin_user = User(
            email="admin@nyelux.com",
            password_hash=auth_service.get_password_hash("Admin123!"),
            role="super_admin",
            first_name="Super",
            last_name="Admin",
            organization_id=nyelux_org.id,
            email_verified=True,
            onboarding_completed=True
        )
        db.add(admin_user)
        await db.commit()
        
        print("Super admin created successfully!")
        print("Email: admin@nyelux.com")
        print("Password: Admin123!")
        print("⚠️  Please change this password immediately!")


def run_migrations():
    """Run database migrations"""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("Migrations completed successfully!")


async def main():
    print("🚀 Nyelux Backend Setup")
    print("=" * 50)
    
    # Check database connection
    print("Checking database connection...")
    try:
        from src.db.session import test_database_connection
        await test_database_connection()
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("Please ensure PostgreSQL is running and configured correctly.")
        sys.exit(1)
    
    # Run migrations
    print("\nRunning database migrations...")
    try:
        run_migrations()
        print("✅ Migrations completed")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
    
    # Create super admin
    create_admin = input("\nCreate super admin user? (y/n): ").lower() == 'y'
    if create_admin:
        await create_super_admin()
    
    # Clean up
    await engine.dispose()
    
    print("\n✅ Setup completed successfully!")
    print("\nYou can now start the server with:")
    print("  python run.py")


if __name__ == "__main__":
    asyncio.run(main())
