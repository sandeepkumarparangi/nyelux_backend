"""
Test configuration for REAL service testing.

IMPORTANT: This uses REAL services that cost money and create real resources.
Every test MUST clean up after itself.
"""
import os
import sys
from pathlib import Path
from typing import AsyncGenerator
import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load test environment variables
from dotenv import load_dotenv
test_env_path = Path(__file__).parent.parent / ".env.test"
if test_env_path.exists():
    load_dotenv(test_env_path)
else:
    raise FileNotFoundError(
        "Missing .env.test file. Copy .env.test.example and fill in REAL service credentials."
    )

# Verify required services are configured
required_vars = [
    "DATABASE_URL",
    "REDIS_URL", 
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "S3_BUCKET_NAME",
    "OPENAI_API_KEY",
    "SENDGRID_API_KEY"
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(
        f"Missing required environment variables for REAL service testing: {missing_vars}\n"
        f"Please configure these in .env.test"
    )

# Now import app modules (after env vars are set)
from src.core.config import settings
from src.db.base_class import Base
from src.db.session import get_db


# Import all models to ensure they're registered
def import_all_models():
    """Import all models to ensure they're registered with SQLAlchemy."""
    from src.db.models import (
        user, organization, gudid_device, vendor_device,
        device_document, document_chunk, chat_conversation,
        chat_message, device_incident, calendar_event,
        notification, analytics_event, audit_log, offline_sync
    )


import_all_models()


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,  # Disable pooling for tests
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
async def client(db_session):
    """Create test client with real database."""
    from httpx import AsyncClient
    from src.main import app
    from src.db.session import get_db
    
    # Override the get_db dependency
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def test_s3_cleanup():
    """Cleanup S3 test files after each test."""
    created_keys = []
    
    yield created_keys
    
    # Cleanup any S3 objects created during test
    if created_keys:
        from src.services.s3_service import get_s3_service
        try:
            s3 = get_s3_service()
            for key in created_keys:
                await s3.delete_file(key)
        except Exception as e:
            print(f"Warning: Failed to cleanup S3 test files: {e}")


@pytest.fixture(scope="function")
async def test_organization(db_session):
    """Create a test organization."""
    from src.db.models.organization import Organization
    
    org = Organization(
        name="Test Hospital",
        subdomain="test-hospital",
        license_tier="professional"
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    yield org
    
    # Cleanup handled by session rollback


@pytest.fixture(scope="function")
async def test_user(db_session, test_organization):
    """Create a test user."""
    from src.db.models.user import User
    from src.services.auth_service import AuthService
    
    auth_service = AuthService()
    
    user = User(
        email="test@example.com",
        password_hash=auth_service.get_password_hash("TestPassword123!"),
        first_name="Test",
        last_name="User",
        role="nurse",
        organization_id=test_organization.id,
        email_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    yield user
    
    # Cleanup handled by session rollback


@pytest.fixture(scope="function") 
async def test_vendor_device(db_session, test_organization):
    """Create a test vendor device."""
    from src.db.models.vendor_device import VendorDevice
    
    device = VendorDevice(
        gudid_device_di="00889842001234",
        organization_id=test_organization.id,
        custom_name="Test Infusion Pump",
        internal_sku="TEST-001",
        is_active=True
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    
    yield device
    
    # Cleanup handled by session rollback


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "external: marks tests that require external services"
    )
    config.addinivalue_line(
        "markers", "expensive: marks tests that incur costs (OpenAI, SMS, etc)"
    )


@pytest.fixture(autouse=True)
def verify_test_environment():
    """Verify we're in test environment before each test."""
    assert settings.ENVIRONMENT == "test", "Not in test environment!"
    assert "test" in settings.DATABASE_URL, "Not using test database!"
