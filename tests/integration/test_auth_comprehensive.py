"""
Comprehensive Authentication & Authorization Tests
Based on NYELUX Test Coverage Document Section 1
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from datetime import datetime, timedelta
import pyotp
import json
from jose import jwt

from src.core.config import settings
from src.db.models.user import User
from src.db.models.organization import Organization
from src.services.auth_service import AuthService


class TestUserRegistration:
    """Test cases TC-AUTH-001 through TC-AUTH-006"""
    
    @pytest.mark.asyncio
    async def test_valid_healthcare_professional_registration(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-001: Valid Healthcare Professional Registration"""
        # Create test organization first
        org = Organization(
            name="Test Hospital",
            type="hospital",
            subdomain="test-hospital",
            license_tier="professional"
        )
        db_session.add(org)
        await db_session.commit()
        
        # Test registration
        registration_data = {
            "email": "nurse@hospital.com",
            "password": "SecurePass123!",
            "first_name": "Jane",
            "last_name": "Doe",
            "role": "nurse",
            "organization_id": org.id
        }
        
        # Record timestamp before request
        start_time = datetime.utcnow()
        
        response = await client.post("/api/v1/auth/register", json=registration_data)
        
        # Assertions
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == registration_data["email"]
        assert "id" in data
        assert "password_hash" not in data  # Security check
        
        # Verify in database - get a fresh session
        # The API endpoint has committed the transaction, so we need a new query
        from src.db.session import get_db
        async for fresh_session in get_db():
            result = await fresh_session.execute(
                select(User).where(User.id == data["id"])
            )
            user = result.scalar_one_or_none()
            break
        assert user is not None
        assert user.email == registration_data["email"]
        assert user.email_verified is False
        assert user.role == "nurse"
        assert user.organization_id == org.id
        
        # Verify password is hashed
        auth_service = AuthService()
        assert auth_service.verify_password(registration_data["password"], user.password_hash)
        assert user.password_hash != registration_data["password"]
        
        # Verify email sent within 30 seconds (check logs or email service)
        # In real implementation, check email queue/service
        
    @pytest.mark.asyncio
    async def test_duplicate_email_prevention(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-002: Duplicate Email Prevention"""
        # Create first user
        user1_data = {
            "email": "test@example.com",
            "password": "Password123!",
            "first_name": "First",
            "last_name": "User",
            "role": "physician"
        }
        
        response1 = await client.post("/api/v1/auth/register", json=user1_data)
        assert response1.status_code == 201
        
        # Attempt duplicate registration
        user2_data = {
            "email": "test@example.com",  # Same email
            "password": "DifferentPass123!",
            "first_name": "Second",
            "last_name": "User",
            "role": "nurse"
        }
        
        response2 = await client.post("/api/v1/auth/register", json=user2_data)
        assert response2.status_code == 400
        assert "Email already registered" in response2.json()["detail"]
        
        # Verify only one user in database
        result = await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
        users = result.scalars().all()
        assert len(users) == 1
    
    @pytest.mark.asyncio
    async def test_password_complexity_validation(self, client: AsyncClient):
        """TC-AUTH-003: Password Complexity Validation"""
        test_cases = [
            ("short", "Password must be at least 8 characters"),
            ("alllowercase", "Password must contain uppercase letter"),
            ("ALLUPPERCASE", "Password must contain lowercase letter"),
            ("NoNumbers!", "Password must contain number"),
            ("NoSpecial8", "Password must contain special character"),
            ("Valid123!", None)  # Should succeed
        ]
        
        base_data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "role": "nurse"
        }
        
        for password, expected_error in test_cases:
            data = {**base_data, "password": password}
            data["email"] = f"{password}@example.com"  # Unique email for each test
            
            response = await client.post("/api/v1/auth/register", json=data)
            
            if expected_error:
                assert response.status_code == 422
                assert expected_error in str(response.json())
            else:
                assert response.status_code == 201
    
    @pytest.mark.asyncio
    async def test_sql_injection_and_xss_prevention(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-004: SQL Injection and XSS Prevention"""
        malicious_data = {
            "email": "test'; DROP TABLE users; --@example.com",
            "password": "Password123!",
            "first_name": "Jane<script>alert('xss')</script>",
            "last_name": "Doe'; DELETE FROM users; --",
            "role": "nurse"
        }
        
        response = await client.post("/api/v1/auth/register", json=malicious_data)
        
        # Should handle gracefully - either reject or escape
        if response.status_code == 201:
            user_id = response.json()["id"]
            user = await db_session.get(User, user_id)
            # Verify input was escaped, not executed
            assert "<script>" in user.first_name  # Script tags should be stored as text
            assert "DROP TABLE" in user.email  # SQL should be stored as text
        
        # Verify database integrity
        # Check users table still exists and has records
        result = await db_session.execute(text("SELECT COUNT(*) FROM users"))
        assert result.scalar() >= 0  # Table exists
    
    @pytest.mark.asyncio
    async def test_registration_rate_limiting(self, client: AsyncClient):
        """TC-AUTH-005: Registration Rate Limiting"""
        # Attempt 6 registrations from same IP
        for i in range(6):
            data = {
                "email": f"user{i}@example.com",
                "password": "Password123!",
                "first_name": "Test",
                "last_name": "User",
                "role": "nurse"
            }
            
            response = await client.post(
                "/api/v1/auth/register",
                json=data,
                headers={"X-Forwarded-For": "192.168.1.100"}
            )
            
            if i < 5:
                assert response.status_code in [201, 400]  # Could be duplicate
            else:
                # 6th attempt should be rate limited
                assert response.status_code == 429
                assert "Retry-After" in response.headers
    
    @pytest.mark.asyncio
    async def test_organization_license_limit(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-006: Organization License Limit"""
        # Create organization at limit
        org = Organization(
            name="Small Clinic",
            type="clinic",
            subdomain="small-clinic",
            license_tier="free",  # Free tier has 5 user limit
            employee_count_range="1-10"
        )
        db_session.add(org)
        await db_session.commit()
        
        # Create 5 users (at limit)
        for i in range(5):
            user = User(
                email=f"user{i}@clinic.com",
                password_hash="hashed",
                role="nurse",
                organization_id=org.id
            )
            db_session.add(user)
        await db_session.commit()
        
        # Attempt to add 6th user
        response = await client.post("/api/v1/auth/register", json={
            "email": "user6@clinic.com",
            "password": "Password123!",
            "first_name": "Sixth",
            "last_name": "User",
            "role": "nurse",
            "organization_id": org.id
        })
        
        assert response.status_code == 403
        assert "Organization has reached user limit" in response.json()["detail"]


class TestLoginAndSessions:
    """Test cases TC-AUTH-007 through TC-AUTH-011"""
    
    @pytest.mark.asyncio
    async def test_successful_login_all_roles(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-007: Successful Login All Roles"""
        roles = [
            "healthcare_professional",
            "org_admin", 
            "vendor_rep",
            "vendor_admin",
            "super_admin"
        ]
        
        auth_service = AuthService()
        
        for role in roles:
            # Create user with role
            user = User(
                email=f"{role}@example.com",
                password_hash=auth_service.get_password_hash("Password123!"),
                role=role,
                email_verified=True
            )
            db_session.add(user)
            await db_session.commit()
            
            # Login
            response = await client.post("/api/v1/auth/login", data={
                "username": f"{role}@example.com",
                "password": "Password123!",
                "grant_type": "password"
            })
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify JWT structure
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            
            # Decode and verify token claims
            decoded = jwt.decode(
                data["access_token"],
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            assert str(user.id) in decoded["sub"]
            assert decoded["role"] == role
            assert "exp" in decoded
            
            # Test protected endpoint with token
            protected_response = await client.get(
                "/api/v1/users/me",
                headers={"Authorization": f"Bearer {data['access_token']}"}
            )
            assert protected_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_account_lockout_after_failed_attempts(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-008: Account Lockout After Failed Attempts"""
        # Create user
        auth_service = AuthService()
        user = User(
            email="locktest@example.com",
            password_hash=auth_service.get_password_hash("CorrectPassword123!"),
            email_verified=True,
            role="nurse"
        )
        db_session.add(user)
        await db_session.commit()
        
        # Attempt 5 failed logins
        for i in range(5):
            response = await client.post("/api/v1/auth/login", data={
                "username": "locktest@example.com",
                "password": "WrongPassword123!",
                "grant_type": "password"
            })
            assert response.status_code == 401
        
        # Check account is locked
        await db_session.refresh(user)
        assert user.failed_login_attempts == 5
        assert user.locked_until is not None
        assert user.locked_until > datetime.utcnow()
        
        # Try correct password immediately - should fail
        response = await client.post("/api/v1/auth/login", data={
            "username": "locktest@example.com",
            "password": "CorrectPassword123!",
            "grant_type": "password"
        })
        assert response.status_code == 403
        assert "Account locked" in response.json()["detail"]
        
        # Simulate waiting 15 minutes
        user.locked_until = datetime.utcnow() - timedelta(minutes=1)
        await db_session.commit()
        
        # Try again - should succeed
        response = await client.post("/api/v1/auth/login", data={
            "username": "locktest@example.com",
            "password": "CorrectPassword123!",
            "grant_type": "password"
        })
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_unverified_email_login_prevention(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-009: Unverified Email Login Prevention"""
        auth_service = AuthService()
        user = User(
            email="unverified@example.com",
            password_hash=auth_service.get_password_hash("Password123!"),
            email_verified=False,  # Not verified
            role="nurse"
        )
        db_session.add(user)
        await db_session.commit()
        
        response = await client.post("/api/v1/auth/login", data={
            "username": "unverified@example.com",
            "password": "Password123!",
            "grant_type": "password"
        })
        
        assert response.status_code == 403
        assert "Email not verified" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_jwt_token_expiration(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-010: JWT Token Expiration"""
        # Create and login user
        auth_service = AuthService()
        user = User(
            email="expiry@example.com",
            password_hash=auth_service.get_password_hash("Password123!"),
            email_verified=True,
            role="nurse"
        )
        db_session.add(user)
        await db_session.commit()
        
        # Create expired token
        expired_token = auth_service.create_access_token(
            data={"sub": str(user.id), "role": user.role},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        # Try to use expired token
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code == 401
        assert "Token expired" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_concurrent_session_handling(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-011: Concurrent Session Handling"""
        # Create user
        auth_service = AuthService()
        user = User(
            email="concurrent@example.com",
            password_hash=auth_service.get_password_hash("Password123!"),
            email_verified=True,
            role="nurse"
        )
        db_session.add(user)
        await db_session.commit()
        
        # Login from Device A
        response_a = await client.post("/api/v1/auth/login", data={
            "username": "concurrent@example.com",
            "password": "Password123!",
            "grant_type": "password"
        })
        assert response_a.status_code == 200
        token_a = response_a.json()["access_token"]
        
        # Login from Device B
        response_b = await client.post("/api/v1/auth/login", data={
            "username": "concurrent@example.com",
            "password": "Password123!",
            "grant_type": "password"
        })
        assert response_b.status_code == 200
        token_b = response_b.json()["access_token"]
        
        # Both tokens should work
        response_with_a = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        assert response_with_a.status_code == 200
        
        response_with_b = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert response_with_b.status_code == 200


class TestMultiFactorAuthentication:
    """Test cases TC-AUTH-012 through TC-AUTH-014"""
    
    @pytest.mark.asyncio
    async def test_totp_setup_flow(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_user
    ):
        """TC-AUTH-012: TOTP Setup Flow"""
        headers = {"Authorization": f"Bearer {authenticated_user['token']}"}
        
        # Enable MFA
        response = await client.post("/api/v1/auth/mfa/enable", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "secret" in data
        assert "qr_code" in data
        assert data["qr_code"].startswith("otpauth://")
        
        # Generate TOTP code
        totp = pyotp.TOTP(data["secret"])
        code = totp.now()
        
        # Verify TOTP
        verify_response = await client.post(
            "/api/v1/auth/mfa/verify",
            json={"code": code},
            headers=headers
        )
        assert verify_response.status_code == 200
        assert "recovery_codes" in verify_response.json()
        
        # Check user record
        user = await db_session.get(User, authenticated_user["user_id"])
        assert user.mfa_enabled is True
        assert user.mfa_secret is not None
    
    @pytest.mark.asyncio
    async def test_mfa_login_flow(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-013: MFA Login Flow"""
        # Create user with MFA enabled
        auth_service = AuthService()
        secret = pyotp.random_base32()
        user = User(
            email="mfa@example.com",
            password_hash=auth_service.get_password_hash("Password123!"),
            email_verified=True,
            role="nurse",
            mfa_enabled=True,
            mfa_secret=secret
        )
        db_session.add(user)
        await db_session.commit()
        
        # Initial login
        response = await client.post("/api/v1/auth/login", data={
            "username": "mfa@example.com",
            "password": "Password123!",
            "grant_type": "password"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("mfa_required") is True
        assert "mfa_token" in data
        
        # Submit TOTP
        totp = pyotp.TOTP(secret)
        mfa_response = await client.post("/api/v1/auth/mfa/validate", json={
            "mfa_token": data["mfa_token"],
            "code": totp.now()
        })
        
        assert mfa_response.status_code == 200
        assert "access_token" in mfa_response.json()
        
        # Test invalid code
        invalid_response = await client.post("/api/v1/auth/mfa/validate", json={
            "mfa_token": data["mfa_token"],
            "code": "000000"
        })
        assert invalid_response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_recovery_code_single_use(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-AUTH-014: Recovery Code Single Use"""
        # Create user with MFA and recovery codes
        auth_service = AuthService()
        user = User(
            email="recovery@example.com",
            password_hash=auth_service.get_password_hash("Password123!"),
            email_verified=True,
            role="nurse",
            mfa_enabled=True,
            mfa_secret=pyotp.random_base32(),
            mfa_backup_codes=["CODE123", "CODE456", "CODE789"]
        )
        db_session.add(user)
        await db_session.commit()
        
        # Login and get MFA challenge
        response = await client.post("/api/v1/auth/login", data={
            "username": "recovery@example.com",
            "password": "Password123!",
            "grant_type": "password"
        })
        
        mfa_token = response.json()["mfa_token"]
        
        # Use recovery code
        recovery_response = await client.post("/api/v1/auth/mfa/validate", json={
            "mfa_token": mfa_token,
            "recovery_code": "CODE123"
        })
        assert recovery_response.status_code == 200
        
        # Check code was removed
        await db_session.refresh(user)
        assert "CODE123" not in user.mfa_backup_codes
        assert len(user.mfa_backup_codes) == 2
        
        # Try to reuse same code
        response2 = await client.post("/api/v1/auth/login", data={
            "username": "recovery@example.com",
            "password": "Password123!",
            "grant_type": "password"
        })
        
        reuse_response = await client.post("/api/v1/auth/mfa/validate", json={
            "mfa_token": response2.json()["mfa_token"],
            "recovery_code": "CODE123"
        })
        assert reuse_response.status_code == 401
        assert "Invalid recovery code" in reuse_response.json()["detail"]


class TestSSOSAMLIntegration:
    """Test cases TC-AUTH-015 through TC-AUTH-016"""
    
    @pytest.mark.asyncio
    async def test_okta_sso_flow(self, client: AsyncClient, db_session: AsyncSession):
        """TC-AUTH-015: Okta SSO Integration"""
        # This would require mocking SAML responses in a real test
        # For now, test the endpoint exists and returns proper redirect
        
        response = await client.get("/api/v1/auth/sso/okta/login")
        assert response.status_code in [302, 307]  # Redirect to Okta
        
        # Test SAML callback endpoint exists
        # In real test, would POST actual SAML assertion
        callback_response = await client.post("/api/v1/auth/sso/okta/callback", data={
            "SAMLResponse": "mock_saml_response"
        })
        # Would validate user creation/update in real implementation
    
    @pytest.mark.asyncio
    async def test_saml_clock_skew_tolerance(self, client: AsyncClient):
        """TC-AUTH-016: SAML Clock Skew Tolerance"""
        # Test with timestamps at various offsets
        test_cases = [
            (-4 * 60, True),   # -4 minutes, should pass
            (4 * 60, True),    # +4 minutes, should pass
            (-6 * 60, False),  # -6 minutes, should fail
            (6 * 60, False),   # +6 minutes, should fail
        ]
        
        for offset_seconds, should_pass in test_cases:
            # In real implementation, would create SAML assertion with timestamp offset
            # and verify acceptance/rejection based on clock skew tolerance
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
