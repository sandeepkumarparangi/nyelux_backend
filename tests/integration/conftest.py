"""
Additional test fixtures for integration tests.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator, Dict, Any
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.main import app
from src.core.config import settings
from src.db.models.user import User
from src.db.models.organization import Organization
from src.services.auth_service import AuthService
from src.db.base import Base  # Import to ensure all models are loaded

# Import the base fixtures from parent conftest
from tests.conftest import db, client

# IMPORTANT: Use pytest_asyncio.fixture for async fixtures to work properly
@pytest_asyncio.fixture
async def db_session(db) -> AsyncSession:
    """Alias for db fixture to match test expectations."""
    # db is already yielding an AsyncSession, just pass it through
    yield db

@pytest_asyncio.fixture
async def test_organization(db_session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        name="Test Hospital",
        type="hospital",
        subdomain="test-hospital",
        license_tier="professional",
        is_verified=True
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_organization: Organization) -> User:
    """Create a test user."""
    auth_service = AuthService()
    user = User(
        email="test.user@example.com",
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
    return user

@pytest_asyncio.fixture
async def authenticated_user(client: AsyncClient, test_user: User) -> Dict[str, Any]:
    """Create an authenticated user with token."""
    # Login to get token
    response = await client.post("/api/v1/auth/login", data={
        "username": test_user.email,
        "password": "TestPassword123!",
        "grant_type": "password"
    })
    
    if response.status_code != 200:
        # If login endpoint doesn't exist yet, create token directly
        auth_service = AuthService()
        token = auth_service.create_access_token(
            data={"sub": str(test_user.id), "role": test_user.role}
        )
        return {
            "user_id": test_user.id,
            "token": token,
            "user": test_user
        }
    
    data = response.json()
    return {
        "user_id": test_user.id,
        "token": data["access_token"],
        "user": test_user
    }

@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, test_organization: Organization) -> User:
    """Create an admin user."""
    auth_service = AuthService()
    user = User(
        email="admin@example.com",
        password_hash=auth_service.get_password_hash("AdminPassword123!"),
        first_name="Admin",
        last_name="User",
        role="org_admin",
        organization_id=test_organization.id,
        email_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def super_admin_user(db_session: AsyncSession) -> User:
    """Create a super admin user."""
    auth_service = AuthService()
    user = User(
        email="superadmin@nyelux.com",
        password_hash=auth_service.get_password_hash("SuperAdmin123!"),
        first_name="Super",
        last_name="Admin",
        role="super_admin",
        email_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

# Mock external services for testing
@pytest.fixture(autouse=True)
def mock_external_services(monkeypatch):
    """Mock external services to prevent real API calls during tests."""
    # Mock email sending
    async def mock_send_email(*args, **kwargs):
        return {"status": "sent", "message_id": "test-message-id"}
    
    # Mock OpenAI if used
    async def mock_openai_completion(*args, **kwargs):
        return {
            "choices": [{
                "message": {
                    "content": "This is a test response from AI."
                }
            }],
            "usage": {
                "total_tokens": 100
            }
        }
    
    # Apply mocks
    monkeypatch.setattr("src.services.email_service.EmailService.send_email", mock_send_email)
    # Add more mocks as needed based on what external services the tests use
