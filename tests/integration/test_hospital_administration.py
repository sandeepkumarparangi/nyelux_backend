"""
Hospital Administration Tests
Based on NYELUX Test Coverage Document Section 7
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import csv
import io
import asyncio

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.department import Department
from src.db.models.user_credential import UserCredential
from src.db.models.training_record import TrainingRecord


class TestUserManagement:
    """Test cases TC-ADMIN-001 through TC-ADMIN-003"""
    
    @pytest.mark.asyncio
    async def test_bulk_user_import(
        self, client: AsyncClient, db_session: AsyncSession, admin_headers
    ):
        """TC-ADMIN-001: Bulk User Import"""
        # Create organization and departments
        org = Organization(
            name="Large Medical Center",
            type="hospital",
            license_tier="enterprise"
        )
        db_session.add(org)
        
        departments = [
            Department(name="Emergency", organization_id=1),
            Department(name="ICU", organization_id=1),
            Department(name="Radiology", organization_id=1)
        ]
        for dept in departments:
            db_session.add(dept)
        await db_session.commit()
        
        # Create CSV with 1000 users
        csv_content = self._generate_user_csv(1000, departments)
        
        # Upload CSV
        start_time = datetime.utcnow()
        
        import_response = await client.post(
            "/api/v1/admin/users/import",
            files={"file": ("users.csv", csv_content, "text/csv")},
            data={"send_welcome_emails": "true"},
            headers=admin_headers
        )
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Verify response
        assert import_response.status_code == 202  # Accepted for processing
        job_id = import_response.json()["job_id"]
        
        # Poll for completion
        max_wait = 300  # 5 minutes max
        poll_interval = 2
        elapsed = 0
        
        while elapsed < max_wait:
            status_response = await client.get(
                f"/api/v1/admin/jobs/{job_id}",
                headers=admin_headers
            )
            
            status = status_response.json()
            if status["status"] == "completed":
                break
            elif status["status"] == "failed":
                pytest.fail(f"Import job failed: {status.get('error')}")
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        # Verify results
        assert status["status"] == "completed"
        assert status["processed_count"] == 1000
        assert status["success_count"] >= 995  # Allow for some duplicates
        assert status["error_count"] <= 5
        assert status["processing_time_seconds"] < 300  # Under 5 minutes
        
        # Check error report
        if status["error_count"] > 0:
            errors_response = await client.get(
                f"/api/v1/admin/jobs/{job_id}/errors",
                headers=admin_headers
            )
            
            errors = errors_response.json()["errors"]
            for error in errors:
                assert "row_number" in error
                assert "email" in error
                assert "reason" in error
                # Common reasons: duplicate email, invalid department
        
        # Verify users created
        user_count = await db_session.execute(
            "SELECT COUNT(*) FROM users WHERE organization_id = :org_id",
            {"org_id": org.id}
        )
        assert user_count.scalar() >= 995
        
        # Verify welcome emails queued
        # In real implementation, check email service
        email_queue_response = await client.get(
            f"/api/v1/admin/jobs/{job_id}/email-queue",
            headers=admin_headers
        )
        
        assert email_queue_response.status_code == 200
        email_data = email_queue_response.json()
        assert email_data["emails_queued"] >= 995
        assert email_data["email_template"] == "welcome_bulk_import"
    
    @pytest.mark.asyncio
    async def test_active_directory_sync(
        self, client: AsyncClient, db_session: AsyncSession, admin_headers
    ):
        """TC-ADMIN-002: Active Directory Sync"""
        # Configure AD connection
        ad_config = {
            "server": "ldap://ad.hospital.local",
            "base_dn": "DC=hospital,DC=local",
            "bind_user": "CN=ServiceAccount,OU=Service,DC=hospital,DC=local",
            "bind_password": "SecurePassword123!",
            "user_filter": "(objectClass=user)",
            "group_filter": "(objectClass=group)",
            "attribute_mapping": {
                "email": "mail",
                "first_name": "givenName",
                "last_name": "sn",
                "department": "department",
                "title": "title",
                "employee_id": "employeeID"
            },
            "group_role_mapping": {
                "CN=Physicians,OU=Groups,DC=hospital,DC=local": "physician",
                "CN=Nurses,OU=Groups,DC=hospital,DC=local": "nurse",
                "CN=Technicians,OU=Groups,DC=hospital,DC=local": "technician",
                "CN=Administrators,OU=Groups,DC=hospital,DC=local": "org_admin"
            }
        }
        
        # Save AD configuration
        config_response = await client.post(
            "/api/v1/admin/integrations/active-directory",
            json=ad_config,
            headers=admin_headers
        )
        
        assert config_response.status_code == 200
        
        # Test connection
        test_response = await client.post(
            "/api/v1/admin/integrations/active-directory/test",
            headers=admin_headers
        )
        
        assert test_response.status_code == 200
        test_result = test_response.json()
        assert test_result["connection_successful"] is True
        assert test_result["users_found"] > 0
        assert test_result["groups_found"] > 0
        
        # Trigger initial sync
        sync_response = await client.post(
            "/api/v1/admin/integrations/active-directory/sync",
            json={"sync_type": "full"},
            headers=admin_headers
        )
        
        assert sync_response.status_code == 202
        sync_job_id = sync_response.json()["job_id"]
        
        # Wait for sync completion
        await self._wait_for_job_completion(client, sync_job_id, admin_headers)
        
        # Verify users created with correct attributes
        sample_users = await db_session.execute(
            """
            SELECT u.*, uc.external_id 
            FROM users u
            JOIN user_credentials uc ON u.id = uc.user_id
            WHERE uc.provider = 'active_directory'
            LIMIT 10
            """
        )
        
        for user in sample_users:
            assert user.email.endswith("@hospital.local")
            assert user.external_id is not None  # AD object GUID
            assert user.role in ["physician", "nurse", "technician", "org_admin"]
        
        # Test incremental sync
        # Simulate AD changes
        await asyncio.sleep(2)
        
        incremental_response = await client.post(
            "/api/v1/admin/integrations/active-directory/sync",
            json={"sync_type": "incremental"},
            headers=admin_headers
        )
        
        assert incremental_response.status_code == 202
        inc_job_id = incremental_response.json()["job_id"]
        
        inc_result = await self._wait_for_job_completion(client, inc_job_id, admin_headers)
        assert inc_result["changes"]["created"] >= 0
        assert inc_result["changes"]["updated"] >= 0
        assert inc_result["changes"]["deactivated"] >= 0
    
    @pytest.mark.asyncio
    async def test_credential_tracking(
        self, client: AsyncClient, db_session: AsyncSession, admin_headers
    ):
        """TC-ADMIN-003: Credential Tracking"""
        # Create test user
        user = User(
            email="nurse@hospital.com",
            first_name="Jane",
            last_name="Doe",
            role="nurse",
            organization_id=1
        )
        db_session.add(user)
        await db_session.commit()
        
        # Add nursing license
        license_response = await client.post(
            f"/api/v1/admin/users/{user.id}/credentials",
            json={
                "credential_type": "nursing_license",
                "credential_number": "RN123456",
                "issuing_authority": "State Board of Nursing",
                "issue_date": "2022-01-15",
                "expiry_date": (datetime.utcnow() + timedelta(days=25)).isoformat(),
                "verification_status": "verified"
            },
            headers=admin_headers
        )
        
        assert license_response.status_code == 201
        credential_id = license_response.json()["id"]
        
        # Fast-forward to 30-day warning period
        # In real implementation, this would be a scheduled job
        check_response = await client.post(
            "/api/v1/admin/credentials/check-expirations",
            headers=admin_headers
        )
        
        assert check_response.status_code == 200
        expiring = check_response.json()["expiring_soon"]
        
        # Find our test credential
        test_cred = next((c for c in expiring if c["id"] == credential_id), None)
        assert test_cred is not None
        assert test_cred["days_until_expiry"] <= 30
        
        # Verify warning notification sent
        notifications_response = await client.get(
            f"/api/v1/users/{user.id}/notifications?type=credential_expiry",
            headers={"Authorization": f"Bearer {self._get_token_for_user(user)}"}
        )
        
        notifications = notifications_response.json()["notifications"]
        assert len(notifications) > 0
        assert "nursing license" in notifications[0]["body"].lower()
        assert "expires in" in notifications[0]["body"].lower()
        
        # Test access restrictions after expiry
        # Update credential to expired
        await db_session.execute(
            """
            UPDATE user_credentials 
            SET expiry_date = :expired_date 
            WHERE id = :cred_id
            """,
            {
                "expired_date": datetime.utcnow() - timedelta(days=1),
                "cred_id": credential_id
            }
        )
        await db_session.commit()
        
        # Check user access
        access_response = await client.get(
            f"/api/v1/admin/users/{user.id}/access-status",
            headers=admin_headers
        )
        
        assert access_response.status_code == 200
        access_data = access_response.json()
        assert access_data["has_expired_credentials"] is True
        assert access_data["access_restricted"] is True
        assert "nursing_license" in access_data["expired_credentials"]
        
        # Verify compliance report
        report_response = await client.get(
            "/api/v1/admin/reports/credential-compliance",
            params={
                "format": "json",
                "include_expired": True,
                "department_id": user.department_id
            },
            headers=admin_headers
        )
        
        assert report_response.status_code == 200
        report = report_response.json()
        
        assert report["total_users"] > 0
        assert report["users_with_expired_credentials"] > 0
        assert report["compliance_percentage"] < 100
        
        # Test detailed breakdown
        assert "by_credential_type" in report
        assert "nursing_license" in report["by_credential_type"]
        assert report["by_credential_type"]["nursing_license"]["expired"] > 0
    
    def _generate_user_csv(self, count, departments):
        """Generate CSV content for bulk user import"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "email", "first_name", "last_name", "role", 
            "department", "title", "employee_id", "phone"
        ])
        
        # Generate users
        roles = ["physician", "nurse", "technician"]
        titles = {
            "physician": ["Attending Physician", "Resident", "Fellow"],
            "nurse": ["RN", "Charge Nurse", "Nurse Practitioner"],
            "technician": ["Radiology Tech", "Lab Tech", "Surgical Tech"]
        }
        
        for i in range(count):
            role = roles[i % len(roles)]
            dept = departments[i % len(departments)]
            title = titles[role][i % len(titles[role])]
            
            writer.writerow([
                f"user{i:04d}@hospital.com",
                f"First{i}",
                f"Last{i}",
                role,
                dept.name,
                title,
                f"EMP{i:06d}",
                f"555-{i%1000:04d}"
            ])
        
        return output.getvalue().encode('utf-8')
    
    async def _wait_for_job_completion(self, client, job_id, headers, timeout=300):
        """Wait for async job to complete"""
        elapsed = 0
        while elapsed < timeout:
            response = await client.get(
                f"/api/v1/admin/jobs/{job_id}",
                headers=headers
            )
            
            status = response.json()
            if status["status"] in ["completed", "failed"]:
                return status
            
            await asyncio.sleep(2)
            elapsed += 2
        
        raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
    
    def _get_token_for_user(self, user):
        """Generate auth token for user"""
        return f"test_token_user_{user.id}"


class TestDepartmentAdministration:
    """Test department-level administration features"""
    
    @pytest.mark.asyncio
    async def test_department_configuration(
        self, client: AsyncClient, db_session: AsyncSession, admin_headers
    ):
        """Test department hierarchy and configuration"""
        # Create organization
        org = Organization(name="Multi-Campus Hospital", type="hospital")
        db_session.add(org)
        await db_session.commit()
        
        # Create department hierarchy
        main_dept = await client.post(
            "/api/v1/admin/departments",
            json={
                "name": "Surgical Services",
                "code": "SURG",
                "cost_center": "CC-5000",
                "parent_id": None
            },
            headers=admin_headers
        )
        
        assert main_dept.status_code == 201
        main_id = main_dept.json()["id"]
        
        # Create sub-departments
        sub_depts = [
            {"name": "General Surgery", "code": "SURG-GEN", "cost_center": "CC-5001"},
            {"name": "Orthopedic Surgery", "code": "SURG-ORTH", "cost_center": "CC-5002"},
            {"name": "Neurosurgery", "code": "SURG-NEURO", "cost_center": "CC-5003"}
        ]
        
        for sub in sub_depts:
            response = await client.post(
                "/api/v1/admin/departments",
                json={**sub, "parent_id": main_id},
                headers=admin_headers
            )
            assert response.status_code == 201
        
        # Test hierarchy retrieval
        hierarchy_response = await client.get(
            "/api/v1/admin/departments/hierarchy",
            headers=admin_headers
        )
        
        assert hierarchy_response.status_code == 200
        hierarchy = hierarchy_response.json()
        
        surg_dept = next(d for d in hierarchy if d["name"] == "Surgical Services")
        assert len(surg_dept["children"]) == 3
        
        # Test approval chain configuration
        approval_response = await client.put(
            f"/api/v1/admin/departments/{main_id}/approval-chain",
            json={
                "levels": [
                    {
                        "level": 1,
                        "role": "department_manager",
                        "threshold_amount": 1000
                    },
                    {
                        "level": 2,
                        "role": "department_director",
                        "threshold_amount": 10000
                    },
                    {
                        "level": 3,
                        "role": "chief_medical_officer",
                        "threshold_amount": None  # No limit
                    }
                ]
            },
            headers=admin_headers
        )
        
        assert approval_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_department_analytics(
        self, client: AsyncClient, db_session: AsyncSession, admin_headers
    ):
        """Test department-level analytics"""
        # Get department analytics
        analytics_response = await client.get(
            "/api/v1/admin/departments/1/analytics",
            params={
                "start_date": (datetime.utcnow() - timedelta(days=30)).isoformat(),
                "end_date": datetime.utcnow().isoformat(),
                "metrics": ["device_usage", "incident_count", "training_completion", "cost_allocation"]
            },
            headers=admin_headers
        )
        
        assert analytics_response.status_code == 200
        analytics = analytics_response.json()
        
        # Verify metrics structure
        assert "device_usage" in analytics
        assert "top_devices" in analytics["device_usage"]
        assert "total_searches" in analytics["device_usage"]
        assert "unique_users" in analytics["device_usage"]
        
        assert "incident_trends" in analytics
        assert "by_severity" in analytics["incident_trends"]
        assert "resolution_time_avg" in analytics["incident_trends"]
        
        assert "training_metrics" in analytics
        assert "completion_rate" in analytics["training_metrics"]
        assert "overdue_count" in analytics["training_metrics"]
        
        assert "cost_allocation" in analytics
        assert "by_category" in analytics["cost_allocation"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
