"""
Global test configuration following PRODUCTION-READY principles.

IMPORTANT: Tests should mock external services, NOT use real ones.
This follows the principle that if a service isn't available, we don't fake it.
"""
import os
import sys
from pathlib import Path

import pytest
from unittest.mock import Mock, patch

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment variables BEFORE importing any app code
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:password@localhost:5432/nyelux_test"
os.environ["SYNC_DATABASE_URL"] = "postgresql://postgres:password@localhost:5432/nyelux_test"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "1440"

# Disable external services for tests
os.environ["AWS_ACCESS_KEY_ID"] = ""
os.environ["AWS_SECRET_ACCESS_KEY"] = ""
os.environ["S3_BUCKET_NAME"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["SENDGRID_API_KEY"] = ""
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["TWILIO_AUTH_TOKEN"] = ""
os.environ["ENABLE_EMBEDDINGS"] = "false"

# Now we can import app code
from src.core.config import settings


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure async test backend."""
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_singletons():
    """
    Reset any singleton instances between tests.
    This ensures test isolation.
    """
    # Since we removed singletons, this is just a placeholder
    # for future use if needed
    yield


@pytest.fixture(autouse=True)
def mock_external_services():
    """
    Automatically mock external service factory functions for all tests.
    This follows the PRODUCTION-READY principle:
    - If service not configured, raise ExternalServiceError
    - Tests should mock the factory functions, not use real services
    """
    # These patches will be active for ALL tests automatically
    with patch('src.services.s3_service.get_s3_service') as mock_s3_factory:
        with patch('src.services.ai_service.get_ai_service') as mock_ai_factory:
            with patch('src.services.email_service.get_email_service') as mock_email_factory:
                # Make factories raise by default - tests must explicitly mock them
                from src.core.exceptions import ExternalServiceError
                
                mock_s3_factory.side_effect = ExternalServiceError(
                    "AWS S3", 
                    "S3 not configured for tests. Mock get_s3_service() in your test."
                )
                mock_ai_factory.side_effect = ExternalServiceError(
                    "OpenAI", 
                    "AI not configured for tests. Mock get_ai_service() in your test."
                )
                mock_email_factory.side_effect = ExternalServiceError(
                    "SendGrid", 
                    "Email not configured for tests. Mock get_email_service() in your test."
                )
                
                yield


# Import model classes to ensure they're registered with SQLAlchemy
def import_all_models():
    """Import all models to ensure they're registered."""
    from src.db.models import (
        user, organization, gudid_device, vendor_device,
        device_document, document_chunk, chat_conversation,
        chat_message, device_incident, calendar_event,
        notification, analytics_event, audit_log, offline_sync
    )


# Import models when conftest loads
import_all_models()
