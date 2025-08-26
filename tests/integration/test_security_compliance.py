"""
Integration tests for Security & Compliance.
Tests cover HIPAA compliance, security testing, and vulnerability prevention.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import hashlib
import secrets
import json
import base64
from typing import List, Dict
from unittest.mock import patch, AsyncMock
import re

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.audit_log import AuditLog
from src.db.models.api_key import APIKey
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.device_document import DeviceDocument
from src.services.auth_service import AuthService
from src.core.security import encrypt_field, decrypt_field


class TestSecurityCompliance:
    """Test cases for Security & Compliance - Section 15"""

    @pytest.fixture
    async def setup_security_test_data(self, db: AsyncSession):
        """Create test data for security testing"""
        # Create healthcare organization
        hospital = Organization(
            name="HIPAA Test Hospital",
            type="hospital",
            subdomain="hipaa-test",
            settings={"hipaa_compliant": True}
        )
        db.add(hospital)
        await db.flush()

        auth_service = AuthService()
        
        # Create users with different roles
        admin_user = User(
            email="admin@hipaa-test.com",
            password_hash=auth_service.get_password_hash("SecureP@ssw0rd123!"),
            first_name="Admin",
            last_name="User",
            role="org_admin",
            organization_id=hospital.id,
            mfa_enabled=True,
            mfa_secret=auth_service.generate_mfa_secret()
        )
        
        doctor_user = User(
            email="doctor@hipaa-test.com",
            password_hash=auth_service.get_password_hash("DoctorP@ss123!"),
            first_name="Doctor",
            last_name="User",
            role="physician",
            organization_id=hospital.id
        )
        
        nurse_user = User(
            email="nurse@hipaa-test.com",
            password_hash=auth_service.get_password_hash("NurseP@ss123!"),
            first_name="Nurse",
            last_name="User",
            role="nurse",
            organization_id=hospital.id
        )
        
        db.add_all([admin_user, doctor_user, nurse_user])
        
        # Create PHI-containing device
        device = GUDIDDevice(
            primary_di="00889842PHI001",
            device_name="Patient Monitor with PHI",
            manufacturer_name="SecureMed Corp",
            device_class="II"
        )
        db.add(device)
        
        # Create document with sensitive data
        sensitive_doc = DeviceDocument(
            device_id=1,  # Will be updated after flush
            organization_id=hospital.id,
            document_type="clinical_study",
            title="Patient Data Analysis",
            file_url="s3://secure-bucket/phi-document.pdf",
            access_level="restricted",
            metadata={"contains_phi": True}
        )
        db.add(sensitive_doc)
        
        await db.commit()
        
        return {
            "hospital": hospital,
            "admin_user": admin_user,
            "doctor_user": doctor_user,
            "nurse_user": nurse_user,
            "device": device,
            "sensitive_doc": sensitive_doc
        }

    @pytest.mark.asyncio
    async def test_tc_sec_001_audit_log_completeness(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """TC-SEC-001: Test HIPAA-compliant audit logging"""
        data = setup_security_test_data
        
        # Login as doctor
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["doctor_user"].email, "password": "DoctorP@ss123!"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Perform various CRUD operations
        operations = []
        
        # 1. View device (READ)
        response = await client.get(
            f"/api/v1/devices/{data['device'].primary_di}",
            headers=headers
        )
        operations.append(("view", "device", data['device'].primary_di, response.status_code))
        
        # 2. Create note (CREATE)
        response = await client.post(
            "/api/v1/notes",
            json={"content": "Patient showed improvement", "device_id": data['device'].primary_di},
            headers=headers
        )
        if response.status_code == 201:
            note_id = response.json()["id"]
            operations.append(("create", "note", note_id, response.status_code))
        
        # 3. Update user profile (UPDATE)
        response = await client.patch(
            "/api/v1/users/me",
            json={"title": "Senior Physician"},
            headers=headers
        )
        operations.append(("update", "user", data['doctor_user'].id, response.status_code))
        
        # 4. Download document (DOWNLOAD)
        response = await client.get(
            f"/api/v1/documents/{data['sensitive_doc'].id}/download",
            headers=headers
        )
        operations.append(("download", "document", data['sensitive_doc'].id, response.status_code))
        
        # Verify audit logs were created
        await asyncio.sleep(0.5)  # Allow async audit logging to complete
        
        # Check audit logs as admin
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["admin_user"].email, "password": "SecureP@ssw0rd123!"}
        )
        admin_token = response.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = await client.get(
            "/api/v1/audit-logs?user_id=" + str(data['doctor_user'].id),
            headers=admin_headers
        )
        assert response.status_code == 200
        
        audit_logs = response.json()["logs"]
        
        # Verify required fields in audit logs
        for log in audit_logs:
            assert "id" in log
            assert "user_id" in log
            assert "action" in log
            assert "resource_type" in log
            assert "resource_id" in log
            assert "ip_address" in log
            assert "user_agent" in log
            assert "created_at" in log
            assert "success" in log
            
            # Verify timestamp format
            assert re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', log["created_at"])
        
        # Verify all operations were logged
        logged_actions = [(log["action"], log["resource_type"]) for log in audit_logs]
        for operation in operations:
            if operation[3] == 200:  # Only successful operations
                assert (operation[0], operation[1]) in logged_actions
        
        # Test audit log immutability
        if audit_logs:
            log_id = audit_logs[0]["id"]
            
            # Try to update audit log (should fail)
            response = await client.put(
                f"/api/v1/audit-logs/{log_id}",
                json={"action": "modified_action"},
                headers=admin_headers
            )
            assert response.status_code in [403, 405]  # Forbidden or Method Not Allowed
            
            # Try to delete audit log (should fail)
            response = await client.delete(
                f"/api/v1/audit-logs/{log_id}",
                headers=admin_headers
            )
            assert response.status_code in [403, 405]

    @pytest.mark.asyncio
    async def test_tc_sec_002_encryption_verification(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """TC-SEC-002: Test encryption at rest and in transit"""
        data = setup_security_test_data
        
        # Test 1: Verify sensitive fields are encrypted in database
        user = await db.get(User, data["admin_user"].id)
        
        # MFA secret should be encrypted
        assert user.mfa_secret != auth_service.generate_mfa_secret()  # Not plaintext
        assert len(user.mfa_secret) > 32  # Encrypted values are longer
        
        # Password should be hashed (not reversible)
        assert user.password_hash != "SecureP@ssw0rd123!"
        assert user.password_hash.startswith("$2b$")  # bcrypt prefix
        
        # Test 2: Verify TLS 1.3 enforcement
        # Check response headers for security
        response = await client.get("/api/v1/health")
        
        # Security headers should be present
        assert "Strict-Transport-Security" in response.headers
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        
        # Test 3: File encryption
        # Upload a file with sensitive data
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["doctor_user"].email, "password": "DoctorP@ss123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get presigned URL for upload
        response = await client.post(
            "/api/v1/documents/upload/presigned",
            json={
                "filename": "patient_data.pdf",
                "content_type": "application/pdf",
                "contains_phi": True
            },
            headers=headers
        )
        
        if response.status_code == 200:
            upload_data = response.json()
            
            # Verify S3 encryption parameters
            assert "x-amz-server-side-encryption" in upload_data.get("fields", {})
            assert upload_data.get("fields", {}).get("x-amz-server-side-encryption") == "AES256"
        
        # Test 4: API response encryption
        # Sensitive data should be encrypted in responses
        response = await client.get(
            f"/api/v1/users/me",
            headers=headers
        )
        
        user_data = response.json()
        # Sensitive fields should not be exposed
        assert "password_hash" not in user_data
        assert "mfa_secret" not in user_data

    @pytest.mark.asyncio
    async def test_tc_sec_003_owasp_top_10(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """TC-SEC-003: Test against OWASP Top 10 vulnerabilities"""
        data = setup_security_test_data
        
        # Get auth token
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["nurse_user"].email, "password": "NurseP@ss123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 1. SQL Injection
        sql_injection_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "1' UNION SELECT * FROM users--",
            "admin'--",
            "' OR 1=1--"
        ]
        
        for payload in sql_injection_payloads:
            response = await client.post(
                "/api/v1/devices/search",
                json={"query": payload},
                headers=headers
            )
            # Should handle safely
            assert response.status_code in [200, 400]
            
            # Verify no data breach
            if response.status_code == 200:
                results = response.json().get("results", [])
                # Should not return all records
                assert len(results) < 100
        
        # 2. XSS (Cross-Site Scripting)
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>",
            "<<SCRIPT>alert('XSS');//<</SCRIPT>"
        ]
        
        for payload in xss_payloads:
            response = await client.post(
                "/api/v1/notes",
                json={"content": payload},
                headers=headers
            )
            
            if response.status_code == 201:
                note_id = response.json()["id"]
                
                # Retrieve and verify sanitization
                response = await client.get(
                    f"/api/v1/notes/{note_id}",
                    headers=headers
                )
                
                content = response.json()["content"]
                # Should be escaped or sanitized
                assert "<script>" not in content
                assert "javascript:" not in content
        
        # 3. CSRF (Cross-Site Request Forgery)
        # Try request without proper token
        response = await client.post(
            "/api/v1/users",
            json={"email": "csrf@test.com", "role": "admin"},
            headers={"Origin": "https://evil-site.com"}
        )
        assert response.status_code == 401  # Unauthorized
        
        # 4. XML External Entities (XXE)
        xxe_payload = """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
        <data>&xxe;</data>"""
        
        response = await client.post(
            "/api/v1/import/xml",
            content=xxe_payload,
            headers={**headers, "Content-Type": "application/xml"}
        )
        
        # Should reject or handle safely
        assert response.status_code in [400, 415, 404]  # Bad request or unsupported
        
        # 5. Broken Access Control
        # Try to access another user's data
        response = await client.get(
            f"/api/v1/users/{data['admin_user'].id}",
            headers=headers
        )
        
        # Nurse should not access admin details
        assert response.status_code in [403, 404]
        
        # 6. Security Misconfiguration
        # Check for exposed sensitive endpoints
        sensitive_endpoints = [
            "/api/v1/admin/config",
            "/api/v1/debug",
            "/.env",
            "/api/v1/database/backup",
            "/swagger.json"
        ]
        
        for endpoint in sensitive_endpoints:
            response = await client.get(endpoint)
            # Should not be publicly accessible
            assert response.status_code in [401, 403, 404]
        
        # 7. Sensitive Data Exposure
        # Verify passwords are not returned
        response = await client.get(
            "/api/v1/users/me",
            headers=headers
        )
        
        user_data = response.json()
        assert "password" not in user_data
        assert "password_hash" not in user_data
        
        # 8. Insufficient Attack Protection
        # Test rate limiting
        for i in range(10):
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": "fake@user.com", "password": "wrong"}
            )
        
        # Should be rate limited
        assert any(r.status_code == 429 for r in [response])
        
        # 9. Using Components with Known Vulnerabilities
        # This would be tested in dependency scanning
        
        # 10. Insufficient Logging & Monitoring
        # Verify security events are logged
        failed_login_response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["admin_user"].email, "password": "wrongpassword"}
        )
        
        # Should log failed attempt
        assert failed_login_response.status_code == 401

    @pytest.mark.asyncio
    async def test_password_security(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test password security requirements"""
        data = setup_security_test_data
        
        # Test weak passwords
        weak_passwords = [
            "password",
            "12345678",
            "qwerty123",
            "admin123",
            "Password",  # No special char
            "Pass123",   # Too short
            "password123!",  # No uppercase
            "PASSWORD123!",  # No lowercase
            "Password!",     # No number
        ]
        
        for weak_pass in weak_passwords:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"weak{weak_pass}@test.com",
                    "password": weak_pass,
                    "first_name": "Test",
                    "last_name": "User",
                    "role": "nurse",
                    "organization_id": data["hospital"].id
                }
            )
            
            # Should reject weak passwords
            assert response.status_code == 422
            assert "password" in response.json()["detail"].lower()
        
        # Test password history (if implemented)
        # Login as admin
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["admin_user"].email, "password": "SecureP@ssw0rd123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to change to same password
        response = await client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "SecureP@ssw0rd123!",
                "new_password": "SecureP@ssw0rd123!"
            },
            headers=headers
        )
        
        # Should reject reusing same password
        if response.status_code == 400:
            assert "same" in response.json()["detail"].lower() or "reuse" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_api_key_security(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test API key security"""
        data = setup_security_test_data
        
        # Login as admin
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["admin_user"].email, "password": "SecureP@ssw0rd123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create API key
        response = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Test Integration",
                "scopes": ["read:devices", "read:users"],
                "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat()
            },
            headers=headers
        )
        
        assert response.status_code == 201
        api_key_data = response.json()
        api_key = api_key_data["key"]
        
        # Verify key format (should be secure random)
        assert len(api_key) >= 32
        assert api_key.startswith("nyx_")  # Prefix for key type identification
        
        # Verify key is shown only once
        response = await client.get(
            f"/api/v1/api-keys/{api_key_data['id']}",
            headers=headers
        )
        
        key_info = response.json()
        assert "key" not in key_info  # Full key not returned
        assert "key_prefix" in key_info  # Only prefix shown
        assert key_info["key_prefix"] == api_key[:8]
        
        # Test API key usage
        api_headers = {"X-API-Key": api_key}
        
        # Should work for allowed scopes
        response = await client.get(
            "/api/v1/devices",
            headers=api_headers
        )
        assert response.status_code == 200
        
        # Should fail for unauthorized scopes
        response = await client.post(
            "/api/v1/devices",
            json={"name": "New Device"},
            headers=api_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_data_privacy_compliance(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test data privacy and GDPR-like compliance"""
        data = setup_security_test_data
        
        # Login as user
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["nurse_user"].email, "password": "NurseP@ss123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test data export (GDPR right to data portability)
        response = await client.post(
            "/api/v1/users/me/export-data",
            headers=headers
        )
        
        if response.status_code == 202:  # Accepted for processing
            export_id = response.json()["export_id"]
            
            # Check export status
            response = await client.get(
                f"/api/v1/users/me/exports/{export_id}",
                headers=headers
            )
            
            # Should include all user data
            if response.status_code == 200 and response.json()["status"] == "completed":
                # Download export
                response = await client.get(
                    f"/api/v1/users/me/exports/{export_id}/download",
                    headers=headers
                )
                
                # Verify contains user data
                assert response.status_code == 200
        
        # Test data deletion (GDPR right to erasure)
        response = await client.post(
            "/api/v1/users/me/request-deletion",
            json={"reason": "No longer using service"},
            headers=headers
        )
        
        if response.status_code == 202:
            deletion_request_id = response.json()["request_id"]
            
            # Verify soft delete implemented
            user = await db.get(User, data["nurse_user"].id)
            assert user.deleted_at is None  # Not immediately deleted
        
        # Test data minimization
        # Public endpoints should not expose unnecessary data
        response = await client.get(
            f"/api/v1/public/devices/{data['device'].primary_di}"
        )
        
        if response.status_code == 200:
            public_data = response.json()
            
            # Should not include sensitive organizational data
            assert "organization_id" not in public_data
            assert "internal_notes" not in public_data

    @pytest.mark.asyncio
    async def test_security_headers(
        self, client: AsyncClient, db: AsyncSession
    ):
        """Test security headers are properly set"""
        response = await client.get("/api/v1/health")
        
        # Required security headers
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": True,  # Just check it exists
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }
        
        for header, expected_value in security_headers.items():
            assert header in response.headers
            
            if expected_value is not True:
                assert response.headers[header] == expected_value

    @pytest.mark.asyncio
    async def test_input_validation_security(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test input validation prevents security issues"""
        data = setup_security_test_data
        
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["doctor_user"].email, "password": "DoctorP@ss123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test various malicious inputs
        malicious_inputs = [
            # Path traversal
            {"filename": "../../../etc/passwd"},
            {"path": "../../../../etc/shadow"},
            
            # Command injection
            {"command": "; cat /etc/passwd"},
            {"name": "test`whoami`"},
            
            # LDAP injection
            {"username": "admin)(uid=*))(|(uid=*"},
            
            # NoSQL injection
            {"filter": {"$ne": None}},
            
            # Buffer overflow attempt
            {"data": "A" * 100000},
            
            # Null byte injection
            {"file": "test.pdf\x00.exe"},
            
            # Unicode exploits
            {"text": "test\u202e\u0000malicious"}
        ]
        
        for malicious_input in malicious_inputs:
            # Try various endpoints
            endpoints = [
                ("/api/v1/documents", "POST"),
                ("/api/v1/devices/search", "POST"),
                ("/api/v1/notes", "POST")
            ]
            
            for endpoint, method in endpoints:
                response = await client.request(
                    method,
                    endpoint,
                    json=malicious_input,
                    headers=headers
                )
                
                # Should handle safely
                assert response.status_code in [400, 422]  # Bad request or validation error

    @pytest.mark.asyncio
    async def test_session_security(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test session management security"""
        data = setup_security_test_data
        
        # Test session fixation
        # Get session before login
        response = await client.get("/api/v1/health")
        initial_cookies = response.cookies
        
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["doctor_user"].email, "password": "DoctorP@ss123!"}
        )
        
        # Session should be regenerated after login
        post_login_cookies = response.cookies
        
        # If using session cookies, they should differ
        if initial_cookies and post_login_cookies:
            assert initial_cookies != post_login_cookies
        
        # Test concurrent session limits (if implemented)
        token1 = response.json()["access_token"]
        
        # Login from "another device"
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["doctor_user"].email, "password": "DoctorP@ss123!"},
            headers={"User-Agent": "Mobile App"}
        )
        token2 = response.json()["access_token"]
        
        # Both tokens should work (concurrent sessions allowed)
        response1 = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token1}"}
        )
        response2 = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token2}"}
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200

    @pytest.mark.asyncio
    async def test_file_upload_security(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test file upload security measures"""
        data = setup_security_test_data
        
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["doctor_user"].email, "password": "DoctorP@ss123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test malicious file types
        malicious_files = [
            ("virus.exe", b"MZ\x90\x00", "application/x-msdownload"),
            ("script.js", b"alert('xss')", "application/javascript"),
            ("shell.php", b"<?php system($_GET['cmd']); ?>", "application/x-php"),
            ("macro.docm", b"PK", "application/vnd.ms-word.document.macroEnabled"),
        ]
        
        for filename, content, content_type in malicious_files:
            response = await client.post(
                "/api/v1/documents/upload",
                files={"file": (filename, content, content_type)},
                headers=headers
            )
            
            # Should reject dangerous file types
            assert response.status_code in [400, 415]  # Bad request or unsupported media type

    @pytest.mark.asyncio
    async def test_privilege_escalation_prevention(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test prevention of privilege escalation"""
        data = setup_security_test_data
        
        # Login as nurse (lower privilege)
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["nurse_user"].email, "password": "NurseP@ss123!"}
        )
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to escalate privileges
        escalation_attempts = [
            # Try to change own role
            {
                "endpoint": "/api/v1/users/me",
                "method": "PATCH",
                "json": {"role": "org_admin"}
            },
            # Try to access admin endpoints
            {
                "endpoint": "/api/v1/admin/users",
                "method": "GET"
            },
            # Try to create admin user
            {
                "endpoint": "/api/v1/users",
                "method": "POST",
                "json": {
                    "email": "newadmin@test.com",
                    "password": "Admin123!",
                    "role": "org_admin"
                }
            },
            # Try to modify organization settings
            {
                "endpoint": f"/api/v1/organizations/{data['hospital'].id}",
                "method": "PATCH",
                "json": {"license_tier": "enterprise"}
            }
        ]
        
        for attempt in escalation_attempts:
            response = await client.request(
                attempt["method"],
                attempt["endpoint"],
                json=attempt.get("json"),
                headers=headers
            )
            
            # Should be forbidden
            assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_secure_password_reset(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test secure password reset flow"""
        data = setup_security_test_data
        
        # Request password reset
        response = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": data["doctor_user"].email}
        )
        assert response.status_code == 200
        
        # Response should not indicate if email exists
        assert "email sent" in response.json()["message"].lower()
        
        # Try with non-existent email
        response = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nonexistent@test.com"}
        )
        assert response.status_code == 200
        
        # Same response to prevent email enumeration
        assert "email sent" in response.json()["message"].lower()
        
        # Test reset token security
        # In real scenario, token would be from email
        # Simulate getting user's reset token from DB
        user = await db.get(User, data["doctor_user"].id)
        
        if user.password_reset_token:
            # Token should be secure random
            assert len(user.password_reset_token) >= 32
            
            # Token should expire
            assert user.password_reset_expires is not None
            assert user.password_reset_expires > datetime.utcnow()
            
            # Try to use token
            response = await client.post(
                "/api/v1/auth/reset-password",
                json={
                    "token": user.password_reset_token,
                    "new_password": "NewSecureP@ss123!"
                }
            )
            
            # Should validate password strength
            assert response.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_security_monitoring_alerts(
        self, client: AsyncClient, db: AsyncSession, setup_security_test_data
    ):
        """Test security monitoring and alerting"""
        data = setup_security_test_data
        
        # Simulate suspicious activities
        suspicious_activities = []
        
        # 1. Multiple failed login attempts
        for i in range(6):
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": data["admin_user"].email, "password": "wrong_password"}
            )
            suspicious_activities.append(("failed_login", response.status_code))
        
        # 2. Access from unusual location
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["doctor_user"].email, "password": "DoctorP@ss123!"},
            headers={"X-Forwarded-For": "185.220.101.1"}  # Tor exit node
        )
        token = response.json()["access_token"] if response.status_code == 200 else None
        suspicious_activities.append(("tor_access", response.status_code))
        
        # 3. Rapid API calls (potential DoS)
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            for i in range(20):
                response = await client.get("/api/v1/devices", headers=headers)
            suspicious_activities.append(("rapid_calls", True))
        
        # Check if security events were logged
        # Admin should see security alerts
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": data["admin_user"].email, "password": "SecureP@ssw0rd123!"}
        )
        
        if response.status_code == 200:
            admin_token = response.json()["access_token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}"}
            
            response = await client.get(
                "/api/v1/security/alerts",
                headers=admin_headers
            )
            
            if response.status_code == 200:
                alerts = response.json()["alerts"]
                
                # Should have security alerts
                alert_types = [alert["type"] for alert in alerts]
                
                # Failed login attempts should trigger alert
                assert any("failed_login" in t or "brute_force" in t for t in alert_types)
