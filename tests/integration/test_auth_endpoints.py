"""
Integration tests for authentication endpoints.

Tests the complete authentication flow including database interactions.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from src.core.config import settings
from src.db.models.organization import Organization
from src.db.models.user import User
from src.main import app
from src.services.auth_service import AuthService


class TestAuthEndpoints:
    """Integration tests for authentication endpoints."""
    
    @pytest.mark.asyncio
    async def test_register_new_user(self, client: AsyncClient, db: AsyncSession):
        """Test complete user registration flow."""
        # Create organization first
        org = Organization(
            name="Test Hospital",
            type="hospital",
            subdomain="test-hospital"
        )
        db.add(org)
        await db.commit()
        await db.refresh(org)
        
        # Register new user
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePassword123!",
                "first_name": "New",
                "last_name": "User",
                "role": "nurse",
                "organization_id": org.id
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify response structure
        assert data["email"] == "newuser@example.com"
        assert data["first_name"] == "New"
        assert data["last_name"] == "User"
        assert data["role"] == "nurse"
        assert "id" in data
        assert "password" not in data
        assert "password_hash" not in data
        
        # Verify user in database
        user = await db.get(User, data["id"])
        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.organization_id == org.id
        
        # Verify password is hashed
        auth_service = AuthService()
        assert auth_service.verify_password("SecurePassword123!", user.password_hash)
    
    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, db: AsyncSession):
        """Test registration with already registered email."""
        # Create existing user
        auth_service = AuthService()
        existing_user = User(
            email="existing@example.com",
            password_hash=auth_service.get_password_hash("password"),
            role="physician"
        )
        db.add(existing_user)
        await db.commit()
        
        # Try to register with same email
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "existing@example.com",
                "password": "DifferentPassword123!",
                "first_name": "Another",
                "last_name": "User",
                "role": "nurse"
            }
        )
        
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, db: AsyncSession):
        """Test successful login flow."""
        # Create user
        auth_service = AuthService()
        user = User(
            email="testlogin@example.com",
            password_hash=auth_service.get_password_hash("TestPassword123!"),
            role="physician",
            first_name="Test",
            last_name="User"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "testlogin@example.com",
                "password": "TestPassword123!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify token response
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["email"] == "testlogin@example.com"
        
        # Verify token is valid JWT
        import jwt
        decoded = jwt.decode(
            data["access_token"],
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        assert decoded["sub"] == str(user.id)
        assert decoded["role"] == "physician"
    
    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, db: AsyncSession):
        """Test login with incorrect password."""
        # Create user
        auth_service = AuthService()
        user = User(
            email="wrongpass@example.com",
            password_hash=auth_service.get_password_hash("CorrectPassword"),
            role="nurse"
        )
        db.add(user)
        await db.commit()
        
        # Login with wrong password
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "wrongpass@example.com",
                "password": "WrongPassword"
            }
        )
        
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]
        
        # Verify failed login attempt was recorded
        await db.refresh(user)
        assert user.failed_login_attempts == 1
    
    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent user."""
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "nonexistent@example.com",
                "password": "AnyPassword123!"
            }
        )
        
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_current_user(self, client: AsyncClient, db: AsyncSession):
        """Test getting current user with valid token."""
        # Create and login user
        auth_service = AuthService()
        user = User(
            email="current@example.com",
            password_hash=auth_service.get_password_hash("password"),
            role="technician",
            first_name="Current",
            last_name="User"
        )
        db.add(user)
        await db.commit()
        
        # Get token
        login_response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "current@example.com",
                "password": "password"
            }
        )
        token = login_response.json()["access_token"]
        
        # Get current user
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "current@example.com"
        assert data["role"] == "technician"
    
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, client: AsyncClient):
        """Test getting current user with invalid token."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_refresh_token(self, client: AsyncClient, db: AsyncSession):
        """Test token refresh flow."""
        # Create user and get tokens
        auth_service = AuthService()
        user = User(
            email="refresh@example.com",
            password_hash=auth_service.get_password_hash("password"),
            role="nurse"
        )
        db.add(user)
        await db.commit()
        
        # Login to get initial tokens
        login_response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "refresh@example.com",
                "password": "password"
            }
        )
        initial_token = login_response.json()["access_token"]
        
        # Refresh token
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={"Authorization": f"Bearer {initial_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["access_token"] != initial_token  # New token issued
    
    @pytest.mark.asyncio
    async def test_logout(self, client: AsyncClient, auth_headers: dict):
        """Test logout endpoint."""
        response = await client.post(
            "/api/v1/auth/logout",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"
    
    @pytest.mark.asyncio
    async def test_forgot_password(self, client: AsyncClient, db: AsyncSession):
        """Test forgot password flow."""
        # Create user
        user = User(
            email="forgot@example.com",
            password_hash="old_hash",
            role="nurse"
        )
        db.add(user)
        await db.commit()
        
        # Request password reset
        response = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "forgot@example.com"}
        )
        
        assert response.status_code == 200
        assert "reset link" in response.json()["message"]
        
        # Verify reset token was generated
        await db.refresh(user)
        assert user.password_reset_token is not None
        assert user.password_reset_expires is not None
    
    @pytest.mark.asyncio
    async def test_reset_password(self, client: AsyncClient, db: AsyncSession):
        """Test password reset with token."""
        # Create user with reset token
        auth_service = AuthService()
        reset_token = "test_reset_token_12345"
        user = User(
            email="reset@example.com",
            password_hash=auth_service.get_password_hash("old_password"),
            role="nurse",
            password_reset_token=reset_token,
            password_reset_expires=datetime.utcnow() + timedelta(hours=1)
        )
        db.add(user)
        await db.commit()
        
        # Reset password
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "NewSecurePassword123!"
            }
        )
        
        assert response.status_code == 200
        
        # Verify password was changed
        await db.refresh(user)
        assert auth_service.verify_password("NewSecurePassword123!", user.password_hash)
        assert user.password_reset_token is None
    
    @pytest.mark.asyncio
    async def test_update_password(self, client: AsyncClient, db: AsyncSession, auth_headers: dict):
        """Test password update for authenticated user."""
        # Get current user
        me_response = await client.get("/api/v1/auth/me", headers=auth_headers)
        user_id = me_response.json()["id"]
        
        # Update password
        response = await client.put(
            "/api/v1/auth/update-password",
            headers=auth_headers,
            json={
                "current_password": "testpass123",  # From fixture
                "new_password": "UpdatedPassword123!"
            }
        )
        
        assert response.status_code == 200
        
        # Verify can login with new password
        login_response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "test@example.com",
                "password": "UpdatedPassword123!"
            }
        )
        assert login_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_verify_email(self, client: AsyncClient, db: AsyncSession):
        """Test email verification flow."""
        # Create unverified user
        auth_service = AuthService()
        user = User(
            email="verify@example.com",
            password_hash=auth_service.get_password_hash("password"),
            role="nurse",
            email_verified=False
        )
        db.add(user)
        await db.commit()
        
        # Generate verification token
        token = auth_service.create_email_verification_token(user.email)
        
        # Verify email
        response = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": token}
        )
        
        assert response.status_code == 200
        
        # Check user is verified
        await db.refresh(user)
        assert user.email_verified is True
    
    @pytest.mark.asyncio
    async def test_role_based_access(self, client: AsyncClient, db: AsyncSession):
        """Test role-based access control."""
        # Create users with different roles
        auth_service = AuthService()
        
        admin = User(
            email="admin@example.com",
            password_hash=auth_service.get_password_hash("adminpass"),
            role="org_admin"
        )
        
        regular = User(
            email="regular@example.com",
            password_hash=auth_service.get_password_hash("userpass"),
            role="nurse"
        )
        
        db.add_all([admin, regular])
        await db.commit()
        
        # Get tokens
        admin_token = (await client.post(
            "/api/v1/auth/login",
            data={"username": "admin@example.com", "password": "adminpass"}
        )).json()["access_token"]
        
        regular_token = (await client.post(
            "/api/v1/auth/login",
            data={"username": "regular@example.com", "password": "userpass"}
        )).json()["access_token"]
        
        # Test admin-only endpoint (example)
        # This would be an actual admin endpoint in your API
        # For now, we'll just verify the tokens work
        admin_response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert admin_response.status_code == 200
        assert admin_response.json()["role"] == "org_admin"
        
        regular_response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {regular_token}"}
        )
        assert regular_response.status_code == 200
        assert regular_response.json()["role"] == "nurse"
