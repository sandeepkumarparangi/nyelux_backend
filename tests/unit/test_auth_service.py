"""
Unit tests for authentication service.

Tests cover all authentication functionality including user registration,
login, token management, and password operations.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
from fastapi import HTTPException
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.user import User
from src.schemas.auth import TokenData
from src.services.auth_service import AuthService


class TestAuthService:
    """Test suite for AuthService class."""
    
    @pytest.fixture
    def auth_service(self):
        """Create AuthService instance for testing."""
        return AuthService()
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock user for testing."""
        user = MagicMock(spec=User)
        user.id = 1
        user.email = "test@example.com"
        user.password_hash = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"  # secret
        user.role = "nurse"
        user.is_active = True
        user.locked_until = None
        user.failed_login_attempts = 0
        user.deleted_at = None
        return user
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock(spec=AsyncSession)
        return db
    
    def test_verify_password_correct(self, auth_service):
        """Test password verification with correct password."""
        # Password hash for "secret"
        hashed = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
        assert auth_service.verify_password("secret", hashed) is True
    
    def test_verify_password_incorrect(self, auth_service):
        """Test password verification with incorrect password."""
        hashed = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
        assert auth_service.verify_password("wrong", hashed) is False
    
    def test_verify_password_invalid_hash(self, auth_service):
        """Test password verification with invalid hash."""
        assert auth_service.verify_password("secret", "invalid_hash") is False
    
    def test_get_password_hash(self, auth_service):
        """Test password hashing."""
        password = "test_password123"
        hashed = auth_service.get_password_hash(password)
        
        # Verify the hash is valid bcrypt format
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60
        
        # Verify we can verify the password
        assert auth_service.verify_password(password, hashed) is True
    
    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, auth_service, mock_db, mock_user):
        """Test successful user authentication."""
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        # Test authentication
        result = await auth_service.authenticate_user(mock_db, "test@example.com", "secret")
        
        assert result == mock_user
        assert mock_user.failed_login_attempts == 0
        assert mock_user.last_login_at is not None
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, auth_service, mock_db):
        """Test authentication with non-existent user."""
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        result = await auth_service.authenticate_user(mock_db, "notfound@example.com", "password")
        
        assert result is None
        mock_db.commit.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, auth_service, mock_db, mock_user):
        """Test authentication with wrong password."""
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        result = await auth_service.authenticate_user(mock_db, "test@example.com", "wrong")
        
        assert result is None
        assert mock_user.failed_login_attempts == 1
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_authenticate_user_account_locked(self, auth_service, mock_db, mock_user):
        """Test authentication with locked account."""
        # Lock the account
        mock_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        result = await auth_service.authenticate_user(mock_db, "test@example.com", "secret")
        
        assert result is None
        mock_db.commit.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_authenticate_user_lockout_after_failures(self, auth_service, mock_db, mock_user):
        """Test account lockout after 5 failed attempts."""
        # Set failed attempts to 4 (next failure will lock)
        mock_user.failed_login_attempts = 4
        
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        result = await auth_service.authenticate_user(mock_db, "test@example.com", "wrong")
        
        assert result is None
        assert mock_user.failed_login_attempts == 5
        assert mock_user.locked_until is not None
        assert mock_user.locked_until > datetime.utcnow()
        mock_db.commit.assert_called_once()
    
    def test_create_access_token(self, auth_service):
        """Test JWT token creation."""
        data = {"sub": "1", "role": "nurse"}
        token = auth_service.create_access_token(data)
        
        # Verify token format
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT has 3 parts
        
        # Decode and verify payload
        payload = jwt.decode(
            token, 
            auth_service.SECRET_KEY, 
            algorithms=[auth_service.ALGORITHM]
        )
        assert payload["sub"] == "1"
        assert payload["role"] == "nurse"
        assert "exp" in payload
        
        # Verify expiration time using UTC consistently
        exp_time = datetime.utcfromtimestamp(payload["exp"])
        expected_exp = datetime.utcnow() + timedelta(minutes=auth_service.ACCESS_TOKEN_EXPIRE_MINUTES)
        assert abs((exp_time - expected_exp).total_seconds()) < 60  # Within 1 minute
    
    def test_create_refresh_token(self, auth_service):
        """Test refresh token creation."""
        data = {"sub": "1"}
        token = auth_service.create_refresh_token(data)
        
        # Verify token format
        assert isinstance(token, str)
        assert len(token.split(".")) == 3
        
        # Decode and verify payload
        payload = jwt.decode(
            token,
            auth_service.SECRET_KEY,
            algorithms=[auth_service.ALGORITHM]
        )
        assert payload["sub"] == "1"
        assert "exp" in payload
        
        # Verify expiration time (7 days) using UTC consistently
        exp_time = datetime.utcfromtimestamp(payload["exp"])
        expected_exp = datetime.utcnow() + timedelta(days=7)
        assert abs((exp_time - expected_exp).total_seconds()) < 60
    
    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self, auth_service, mock_db, mock_user):
        """Test getting current user with valid token."""
        # Create valid token
        token = auth_service.create_access_token({"sub": "1"})
        
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        result = await auth_service.get_current_user(mock_db, token)
        
        assert result == mock_user
        assert mock_user.last_activity_at is not None
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, auth_service, mock_db):
        """Test getting current user with invalid token."""
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.get_current_user(mock_db, "invalid_token")
        
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Could not validate credentials"
    
    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, auth_service, mock_db):
        """Test getting current user with expired token."""
        # Create expired token
        data = {"sub": "1", "exp": datetime.utcnow() - timedelta(hours=1)}
        expired_token = jwt.encode(
            data, 
            auth_service.SECRET_KEY, 
            algorithm=auth_service.ALGORITHM
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.get_current_user(mock_db, expired_token)
        
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_get_current_user_deleted_user(self, auth_service, mock_db, mock_user):
        """Test getting current user when user is deleted."""
        # Mark user as deleted
        mock_user.deleted_at = datetime.utcnow()
        
        # Create valid token
        token = auth_service.create_access_token({"sub": "1"})
        
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # User not found due to deleted_at filter
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await auth_service.get_current_user(mock_db, token)
        
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_verify_email_token_valid(self, auth_service, mock_db, mock_user):
        """Test email verification with valid token."""
        # Create email verification token
        token = auth_service.create_email_verification_token(mock_user.email)
        
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        result = await auth_service.verify_email_token(mock_db, token)
        
        assert result is True
        assert mock_user.email_verified is True
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_reset_password(self, auth_service, mock_db, mock_user):
        """Test password reset functionality."""
        # Create reset token
        reset_token = "test_reset_token_123"
        mock_user.password_reset_token = reset_token
        mock_user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        new_password = "new_secure_password123"
        result = await auth_service.reset_password(mock_db, reset_token, new_password)
        
        assert result is True
        assert mock_user.password_reset_token is None
        assert mock_user.password_reset_expires is None
        # Verify password was updated (we can't check the exact hash)
        assert mock_user.password_hash != "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_reset_password_expired_token(self, auth_service, mock_db, mock_user):
        """Test password reset with expired token."""
        # Create expired reset token
        reset_token = "expired_token"
        mock_user.password_reset_token = reset_token
        mock_user.password_reset_expires = datetime.utcnow() - timedelta(hours=1)
        
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        result = await auth_service.reset_password(mock_db, reset_token, "new_password")
        
        assert result is False
        mock_db.commit.assert_not_called()
