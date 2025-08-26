"""
Team Collaboration & Notes Tests
Based on NYELUX Test Coverage Document Section 6
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import asyncio
import json
from unittest.mock import patch

from src.db.models.user import User
from src.db.models.organization import Organization
from src.db.models.department import Department
from src.db.models.team import Team
from src.db.models.note import Note
from src.db.models.note_mention import NoteMention
from src.db.models.note_version import NoteVersion


class TestNoteManagement:
    """Test cases TC-TEAM-001 through TC-TEAM-003"""
    
    @pytest.mark.asyncio
    async def test_real_time_note_collaboration(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-TEAM-001: Real-Time Note Collaboration"""
        # Create test users
        org = Organization(name="Test Hospital", type="hospital")
        db_session.add(org)
        await db_session.commit()
        
        user_a = User(
            email="user_a@hospital.com",
            first_name="User",
            last_name="A",
            role="nurse",
            organization_id=org.id
        )
        user_b = User(
            email="user_b@hospital.com",
            first_name="User",
            last_name="B",
            role="physician",
            organization_id=org.id
        )
        db_session.add_all([user_a, user_b])
        await db_session.commit()
        
        # User A creates note
        note_response = await client.post(
            "/api/v1/notes",
            json={
                "title": "Patient Care Protocol",
                "content": "Initial protocol notes...",
                "type": "device_specific",
                "device_id": "TEST001",
                "access_level": "team"
            },
            headers=authenticated_headers
        )
        
        assert note_response.status_code == 201
        note_id = note_response.json()["id"]
        
        # User B connects via WebSocket
        # In real test, would use actual WebSocket client
        ws_url = f"ws://localhost:8000/ws/notes/{note_id}"
        
        # Simulate concurrent edits
        edit_a = {
            "user_id": user_a.id,
            "operation": "insert",
            "position": 25,
            "content": " Additional safety measures:",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        edit_b = {
            "user_id": user_b.id,
            "operation": "insert",
            "position": 50,
            "content": " Physician approval required.",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Apply edits via API (simulating WebSocket in real implementation)
        for edit in [edit_a, edit_b]:
            edit_response = await client.patch(
                f"/api/v1/notes/{note_id}/realtime",
                json=edit,
                headers=authenticated_headers
            )
            assert edit_response.status_code == 200
        
        # Verify merged content
        final_response = await client.get(
            f"/api/v1/notes/{note_id}",
            headers=authenticated_headers
        )
        
        assert final_response.status_code == 200
        final_content = final_response.json()["content"]
        
        # Check both edits are present
        assert "Additional safety measures:" in final_content
        assert "Physician approval required." in final_content
        
        # Verify change tracking
        history_response = await client.get(
            f"/api/v1/notes/{note_id}/history",
            headers=authenticated_headers
        )
        
        assert history_response.status_code == 200
        history = history_response.json()["versions"]
        assert len(history) >= 3  # Initial + 2 edits
        
        # Test conflict resolution
        # Simulate same position edit
        conflict_edit_a = {
            "user_id": user_a.id,
            "operation": "replace",
            "position": 10,
            "length": 5,
            "content": "AAAAA",
            "version": 3
        }
        
        conflict_edit_b = {
            "user_id": user_b.id,
            "operation": "replace",
            "position": 10,
            "length": 5,
            "content": "BBBBB",
            "version": 3  # Same version = conflict
        }
        
        # First edit succeeds
        response_a = await client.patch(
            f"/api/v1/notes/{note_id}/realtime",
            json=conflict_edit_a,
            headers=authenticated_headers
        )
        assert response_a.status_code == 200
        
        # Second edit gets conflict
        response_b = await client.patch(
            f"/api/v1/notes/{note_id}/realtime",
            json=conflict_edit_b,
            headers=authenticated_headers
        )
        
        assert response_b.status_code == 409  # Conflict
        conflict_data = response_b.json()
        assert "conflict" in conflict_data
        assert "merge_suggestion" in conflict_data
    
    @pytest.mark.asyncio
    async def test_permission_inheritance(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """TC-TEAM-002: Permission Inheritance"""
        # Create organization hierarchy
        org = Organization(name="Medical Center", type="hospital")
        db_session.add(org)
        
        dept = Department(
            name="Emergency Department",
            organization_id=org.id
        )
        db_session.add(dept)
        
        team = Team(
            name="Trauma Team",
            department_id=dept.id,
            organization_id=org.id
        )
        db_session.add(team)
        await db_session.commit()
        
        # Create users at different levels
        users = {
            "owner": User(
                email="owner@hospital.com",
                role="nurse",
                organization_id=org.id
            ),
            "team_member": User(
                email="team@hospital.com",
                role="nurse",
                organization_id=org.id,
                department_id=dept.id
            ),
            "dept_member": User(
                email="dept@hospital.com",
                role="physician",
                organization_id=org.id,
                department_id=dept.id
            ),
            "org_member": User(
                email="org@hospital.com",
                role="technician",
                organization_id=org.id
            ),
            "outsider": User(
                email="outsider@other.com",
                role="nurse",
                organization_id=999  # Different org
            )
        }
        
        for user in users.values():
            db_session.add(user)
        await db_session.commit()
        
        # Add team member to team
        await db_session.execute(
            "INSERT INTO team_members (team_id, user_id) VALUES (:team_id, :user_id)",
            {"team_id": team.id, "user_id": users["team_member"].id}
        )
        await db_session.commit()
        
        # Test different access levels
        test_cases = [
            {
                "note_type": "private",
                "created_by": users["owner"],
                "can_access": ["owner"],
                "cannot_access": ["team_member", "dept_member", "org_member", "outsider"]
            },
            {
                "note_type": "team",
                "created_by": users["team_member"],
                "team_id": team.id,
                "can_access": ["owner", "team_member"],
                "cannot_access": ["dept_member", "org_member", "outsider"]
            },
            {
                "note_type": "department",
                "created_by": users["dept_member"],
                "department_id": dept.id,
                "can_access": ["dept_member", "team_member"],  # Team is in dept
                "cannot_access": ["org_member", "outsider"],
                "admin_override": True  # Dept admin can access
            },
            {
                "note_type": "organization",
                "created_by": users["org_member"],
                "can_access": ["owner", "team_member", "dept_member", "org_member"],
                "cannot_access": ["outsider"]
            }
        ]
        
        for test in test_cases:
            # Create note
            note_data = {
                "title": f"{test['note_type']} Note Test",
                "content": "Test content",
                "access_level": test["note_type"]
            }
            
            if "team_id" in test:
                note_data["team_id"] = test["team_id"]
            if "department_id" in test:
                note_data["department_id"] = test["department_id"]
            
            # Create as the specified user
            creator_token = self._get_token_for_user(test["created_by"])
            create_response = await client.post(
                "/api/v1/notes",
                json=note_data,
                headers={"Authorization": f"Bearer {creator_token}"}
            )
            
            assert create_response.status_code == 201
            note_id = create_response.json()["id"]
            
            # Test access for each user type
            for user_type, user in users.items():
                user_token = self._get_token_for_user(user)
                access_response = await client.get(
                    f"/api/v1/notes/{note_id}",
                    headers={"Authorization": f"Bearer {user_token}"}
                )
                
                if user_type in test["can_access"]:
                    assert access_response.status_code == 200
                elif user_type in test["cannot_access"]:
                    assert access_response.status_code in [403, 404]
    
    @pytest.mark.asyncio
    async def test_mention_notifications(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-TEAM-003: @Mention Notifications"""
        # Create users
        mentioner = User(
            email="mentioner@hospital.com",
            first_name="John",
            last_name="Doe",
            role="physician"
        )
        mentioned = User(
            email="mentioned@hospital.com",
            first_name="Jane",
            last_name="Smith",
            role="nurse"
        )
        db_session.add_all([mentioner, mentioned])
        await db_session.commit()
        
        # Create note with mention
        note_content = f"@jane.smith please review this protocol. @{mentioned.id} check the dosage calculations."
        
        note_response = await client.post(
            "/api/v1/notes",
            json={
                "title": "Protocol Review",
                "content": note_content,
                "access_level": "team"
            },
            headers=authenticated_headers
        )
        
        assert note_response.status_code == 201
        note_data = note_response.json()
        note_id = note_data["id"]
        
        # Verify mentions detected
        assert "mentions" in note_data
        assert len(note_data["mentions"]) == 2
        
        # Check mention records created
        mentions = await db_session.execute(
            "SELECT * FROM note_mentions WHERE note_id = :note_id",
            {"note_id": note_id}
        )
        mention_records = mentions.fetchall()
        assert len(mention_records) == 2
        
        # Verify notifications sent
        # Check notification queue (mocked in test)
        notifications_response = await client.get(
            f"/api/v1/users/{mentioned.id}/notifications",
            headers={"Authorization": f"Bearer {self._get_token_for_user(mentioned)}"}
        )
        
        assert notifications_response.status_code == 200
        notifications = notifications_response.json()["notifications"]
        
        # Find mention notification
        mention_notif = next(
            (n for n in notifications if n["type"] == "mention"),
            None
        )
        
        assert mention_notif is not None
        assert mention_notif["title"] == "You were mentioned in a note"
        assert "Protocol Review" in mention_notif["body"]
        assert mention_notif["action_url"] == f"/notes/{note_id}"
        assert mention_notif["created_at"] is not None
        
        # Verify notification sent within 30 seconds
        created_time = datetime.fromisoformat(mention_notif["created_at"])
        note_time = datetime.fromisoformat(note_data["created_at"])
        time_diff = (created_time - note_time).total_seconds()
        assert time_diff < 30
        
        # Test mention in comment
        comment_response = await client.post(
            f"/api/v1/notes/{note_id}/comments",
            json={
                "content": "@john.doe what do you think about this?"
            },
            headers={"Authorization": f"Bearer {self._get_token_for_user(mentioned)}"}
        )
        
        assert comment_response.status_code == 201
        
        # Verify comment mention notification
        await asyncio.sleep(1)  # Allow notification processing
        
        notif_check = await client.get(
            f"/api/v1/users/{mentioner.id}/notifications?type=mention&after={note_time.isoformat()}",
            headers={"Authorization": f"Bearer {self._get_token_for_user(mentioner)}"}
        )
        
        assert notif_check.status_code == 200
        new_notifs = notif_check.json()["notifications"]
        assert len(new_notifs) > 0
        assert any("comment" in n["body"].lower() for n in new_notifs)
    
    def _get_token_for_user(self, user):
        """Helper to generate auth token for user"""
        # In real implementation, use proper auth service
        return f"test_token_for_user_{user.id}"


class TestTeamManagement:
    """Test cases TC-TEAM-004 and team-related features"""
    
    @pytest.mark.asyncio
    async def test_cross_functional_team_creation(
        self, client: AsyncClient, db_session: AsyncSession, admin_headers
    ):
        """TC-TEAM-004: Cross-Functional Team Creation"""
        # Create departments
        er_dept = Department(name="Emergency Room", organization_id=1)
        rad_dept = Department(name="Radiology", organization_id=1)
        admin_dept = Department(name="Administration", organization_id=1)
        
        db_session.add_all([er_dept, rad_dept, admin_dept])
        await db_session.commit()
        
        # Create users from different departments
        users = [
            {
                "email": "nurse1@er.com",
                "first_name": "ER",
                "last_name": "Nurse1",
                "role": "nurse",
                "department_id": er_dept.id
            },
            {
                "email": "nurse2@er.com",
                "first_name": "ER",
                "last_name": "Nurse2",
                "role": "nurse",
                "department_id": er_dept.id
            },
            {
                "email": "tech@radiology.com",
                "first_name": "Rad",
                "last_name": "Tech",
                "role": "technician",
                "department_id": rad_dept.id
            },
            {
                "email": "admin@hospital.com",
                "first_name": "Admin",
                "last_name": "User",
                "role": "org_admin",
                "department_id": admin_dept.id
            }
        ]
        
        created_users = []
        for user_data in users:
            user = User(**user_data, organization_id=1)
            db_session.add(user)
            created_users.append(user)
        await db_session.commit()
        
        # Create cross-functional team
        team_response = await client.post(
            "/api/v1/teams",
            json={
                "name": "Rapid Response Team",
                "description": "Cross-departmental emergency response",
                "team_type": "cross_functional",
                "member_ids": [u.id for u in created_users]
            },
            headers=admin_headers
        )
        
        assert team_response.status_code == 201
        team_data = team_response.json()
        team_id = team_data["id"]
        
        # Verify team composition
        assert len(team_data["members"]) == 4
        departments_represented = set(m["department_name"] for m in team_data["members"])
        assert len(departments_represented) == 3  # ER, Radiology, Admin
        
        # Test team resource access
        # Create team-specific note
        team_note_response = await client.post(
            "/api/v1/notes",
            json={
                "title": "Rapid Response Protocol",
                "content": "Emergency response procedures...",
                "access_level": "team",
                "team_id": team_id
            },
            headers={"Authorization": f"Bearer {self._get_token_for_user(created_users[0])}"}
        )
        
        assert team_note_response.status_code == 201
        note_id = team_note_response.json()["id"]
        
        # Verify all team members can access
        for user in created_users:
            user_token = self._get_token_for_user(user)
            access_response = await client.get(
                f"/api/v1/notes/{note_id}",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            assert access_response.status_code == 200
        
        # Verify original department permissions retained
        # Create ER-only note
        er_note_response = await client.post(
            "/api/v1/notes",
            json={
                "title": "ER Internal Protocol",
                "content": "ER-specific procedures...",
                "access_level": "department",
                "department_id": er_dept.id
            },
            headers={"Authorization": f"Bearer {self._get_token_for_user(created_users[0])}"}
        )
        
        er_note_id = er_note_response.json()["id"]
        
        # ER nurses can access
        for user in created_users[:2]:  # First two are ER nurses
            response = await client.get(
                f"/api/v1/notes/{er_note_id}",
                headers={"Authorization": f"Bearer {self._get_token_for_user(user)}"}
            )
            assert response.status_code == 200
        
        # Radiology tech cannot
        rad_response = await client.get(
            f"/api/v1/notes/{er_note_id}",
            headers={"Authorization": f"Bearer {self._get_token_for_user(created_users[2])}"}
        )
        assert rad_response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_team_collaboration_features(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """Test additional team collaboration features"""
        # Create team
        team_response = await client.post(
            "/api/v1/teams",
            json={
                "name": "Device Training Team",
                "description": "Coordinates device training"
            },
            headers=authenticated_headers
        )
        
        team_id = team_response.json()["id"]
        
        # Test shared bookmarks
        bookmark_response = await client.post(
            "/api/v1/teams/{team_id}/bookmarks",
            json={
                "resource_type": "device",
                "resource_id": "PUMP001",
                "title": "Primary Infusion Pump",
                "notes": "Standard pump for our unit"
            },
            headers=authenticated_headers
        )
        
        assert bookmark_response.status_code == 201
        
        # Test team dashboard
        dashboard_response = await client.get(
            f"/api/v1/teams/{team_id}/dashboard",
            headers=authenticated_headers
        )
        
        assert dashboard_response.status_code == 200
        dashboard = dashboard_response.json()
        
        assert "recent_notes" in dashboard
        assert "shared_bookmarks" in dashboard
        assert "upcoming_training" in dashboard
        assert "team_activity" in dashboard
        
        # Test team calendar integration
        event_response = await client.post(
            f"/api/v1/teams/{team_id}/events",
            json={
                "title": "Ventilator Training Session",
                "description": "Monthly team training",
                "start_time": "2024-02-01T14:00:00Z",
                "end_time": "2024-02-01T16:00:00Z",
                "notify_team": True
            },
            headers=authenticated_headers
        )
        
        assert event_response.status_code == 201
        assert event_response.json()["attendee_count"] > 0
    
    def _get_token_for_user(self, user):
        """Helper to generate auth token for user"""
        return f"test_token_for_user_{user.id}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
