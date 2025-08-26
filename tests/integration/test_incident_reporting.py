"""
Incident Reporting & Support Tests
Based on NYELUX Test Coverage Document Section 8
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import asyncio
from unittest.mock import patch, MagicMock

from src.db.models.device_incident import DeviceIncident
from src.db.models.incident_attachment import IncidentAttachment
from src.db.models.incident_comment import IncidentComment
from src.db.models.support_conversation import SupportConversation
from src.db.models.support_message import SupportMessage
from src.db.models.agent_availability import AgentAvailability
from src.db.models.vendor_device import VendorDevice
from src.db.models.organization import Organization
from src.db.models.user import User


class TestIncidentManagement:
    """Test cases TC-INCIDENT-001 through TC-INCIDENT-002"""
    
    @pytest.mark.asyncio
    async def test_critical_incident_flow(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-INCIDENT-001: Critical Incident Flow"""
        # Create vendor and device
        vendor_org = Organization(
            name="MedDevice Corp",
            type="vendor"
        )
        db_session.add(vendor_org)
        
        device = VendorDevice(
            gudid_device_di="CRIT001",
            organization_id=vendor_org.id,
            custom_name="Critical Care Ventilator X1"
        )
        db_session.add(device)
        
        # Create vendor support agent
        vendor_agent = User(
            email="support@meddevice.com",
            first_name="Support",
            last_name="Agent",
            role="vendor_rep",
            organization_id=vendor_org.id
        )
        db_session.add(vendor_agent)
        await db_session.commit()
        
        # Report critical incident
        incident_start = datetime.utcnow()
        
        incident_data = {
            "device_id": device.id,
            "incident_type": "malfunction",
            "urgency": "critical",
            "incident_date": incident_start.isoformat(),
            "description": "Ventilator stopped functioning during patient care. Error code E501 displayed. Patient required manual ventilation.",
            "patient_impact": "life_threatening",
            "serial_number": "VX1-2024-0123",
            "lot_number": "LOT2024A",
            "location": "ICU Room 203",
            "witnesses": ["Dr. Smith", "Nurse Johnson"]
        }
        
        incident_response = await client.post(
            "/api/v1/incidents",
            json=incident_data,
            headers=authenticated_headers
        )
        
        notification_time = datetime.utcnow()
        
        # Verify incident created
        assert incident_response.status_code == 201
        incident = incident_response.json()
        
        assert incident["ticket_number"] is not None
        assert incident["status"] == "open"
        assert incident["urgency"] == "critical"
        
        # Verify vendor notification time
        notification_delay = (notification_time - incident_start).total_seconds()
        assert notification_delay < 300  # Less than 5 minutes
        
        # Check vendor notification sent
        vendor_notif_response = await client.get(
            f"/api/v1/users/{vendor_agent.id}/notifications?type=incident&after={incident_start.isoformat()}",
            headers={"Authorization": f"Bearer vendor_token_{vendor_agent.id}"}
        )
        
        vendor_notifs = vendor_notif_response.json()["notifications"]
        assert len(vendor_notifs) > 0
        assert vendor_notifs[0]["priority"] == "critical"
        assert "IMMEDIATE RESPONSE REQUIRED" in vendor_notifs[0]["title"]
        
        # Verify SLA timer started
        sla_response = await client.get(
            f"/api/v1/incidents/{incident['id']}/sla",
            headers=authenticated_headers
        )
        
        sla_data = sla_response.json()
        assert sla_data["response_deadline"] is not None
        assert sla_data["response_sla_minutes"] == 15  # Critical = 15 min
        assert sla_data["timer_status"] == "running"
        
        # Simulate vendor acknowledgment after 10 minutes
        await asyncio.sleep(1)  # Simulate time passing
        
        ack_response = await client.post(
            f"/api/v1/incidents/{incident['id']}/acknowledge",
            json={"message": "Acknowledged. Escalating to engineering team."},
            headers={"Authorization": f"Bearer vendor_token_{vendor_agent.id}"}
        )
        
        assert ack_response.status_code == 200
        ack_data = ack_response.json()
        
        # Verify SLA met
        assert ack_data["sla_status"] == "met"
        assert ack_data["response_time_minutes"] < 15
        
        # Test escalation if no response (separate test)
        # Create another critical incident
        no_response_incident = await client.post(
            "/api/v1/incidents",
            json={
                **incident_data,
                "description": "Another critical failure - testing escalation"
            },
            headers=authenticated_headers
        )
        
        no_resp_id = no_response_incident.json()["id"]
        
        # Wait 16 minutes (past SLA)
        # In real test, would mock time
        await db_session.execute(
            """
            UPDATE device_incidents 
            SET created_at = :past_time 
            WHERE id = :incident_id
            """,
            {
                "past_time": datetime.utcnow() - timedelta(minutes=16),
                "incident_id": no_resp_id
            }
        )
        await db_session.commit()
        
        # Trigger SLA check
        sla_check_response = await client.post(
            "/api/v1/admin/incidents/check-slas",
            headers=authenticated_headers
        )
        
        # Verify escalation occurred
        escalation_response = await client.get(
            f"/api/v1/incidents/{no_resp_id}",
            headers=authenticated_headers
        )
        
        escalated_incident = escalation_response.json()
        assert escalated_incident["status"] == "escalated"
        assert escalated_incident["escalation_level"] > 0
        
        # Check escalation notifications sent to vendor management
        # Would check actual notification service in production
    
    @pytest.mark.asyncio
    async def test_fda_mdr_determination(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-INCIDENT-002: FDA MDR Determination"""
        # Create test device
        device = VendorDevice(
            gudid_device_di="MDR001",
            custom_name="Implantable Cardiac Device",
            organization_id=1
        )
        db_session.add(device)
        await db_session.commit()
        
        # Test case: Serious injury requiring MDR
        serious_incident = {
            "device_id": device.id,
            "incident_type": "malfunction",
            "urgency": "high",
            "incident_date": datetime.utcnow().isoformat(),
            "description": "Device malfunction resulted in patient requiring emergency surgery",
            "patient_impact": "serious_injury",
            "serial_number": "ICD-2024-456",
            "clinical_outcome": "Patient required immediate surgical intervention. Extended hospitalization by 5 days."
        }
        
        response = await client.post(
            "/api/v1/incidents",
            json=serious_incident,
            headers=authenticated_headers
        )
        
        assert response.status_code == 201
        incident_data = response.json()
        
        # Verify MDR flag set automatically
        assert incident_data["fda_reportable"] is True
        assert incident_data["mdr_determination_reason"] == "serious_injury"
        
        # Check MDR workflow initiated
        mdr_response = await client.get(
            f"/api/v1/incidents/{incident_data['id']}/mdr-status",
            headers=authenticated_headers
        )
        
        assert mdr_response.status_code == 200
        mdr_status = mdr_response.json()
        
        assert mdr_status["reportable"] is True
        assert mdr_status["reporting_deadline"] is not None
        assert mdr_status["required_forms"] == ["FDA 3500A"]
        assert mdr_status["workflow_stage"] == "initial_assessment"
        
        # Generate MDR report
        report_response = await client.post(
            f"/api/v1/incidents/{incident_data['id']}/generate-mdr",
            json={
                "reporter_info": {
                    "name": "Dr. Jane Smith",
                    "title": "Chief Medical Officer",
                    "phone": "555-0100",
                    "email": "cmo@hospital.com"
                },
                "manufacturer_aware_date": datetime.utcnow().isoformat(),
                "device_evaluation": "pending"
            },
            headers=authenticated_headers
        )
        
        assert report_response.status_code == 200
        report_data = report_response.json()
        
        assert report_data["report_number"] is not None
        assert report_data["form_type"] == "FDA 3500A"
        assert "draft_url" in report_data
        
        # Test submission tracking
        submission_response = await client.post(
            f"/api/v1/incidents/{incident_data['id']}/submit-mdr",
            json={
                "submission_method": "electronic",
                "confirmation_number": "FDA-2024-00123",
                "submitted_by": "Dr. Jane Smith"
            },
            headers=authenticated_headers
        )
        
        assert submission_response.status_code == 200
        
        # Verify audit trail
        audit_response = await client.get(
            f"/api/v1/incidents/{incident_data['id']}/audit-trail",
            headers=authenticated_headers
        )
        
        audit_events = audit_response.json()["events"]
        
        # Check key events recorded
        event_types = [e["event_type"] for e in audit_events]
        assert "incident_created" in event_types
        assert "mdr_determination" in event_types
        assert "mdr_report_generated" in event_types
        assert "mdr_submitted" in event_types
        
        # Test follow-up management
        followup_response = await client.post(
            f"/api/v1/incidents/{incident_data['id']}/mdr-followup",
            json={
                "followup_type": "supplemental",
                "reason": "Additional information from device analysis",
                "new_findings": "Root cause identified as firmware bug in version 2.3.1"
            },
            headers=authenticated_headers
        )
        
        assert followup_response.status_code == 201
        assert followup_response.json()["followup_number"] is not None


class TestLiveSupportChat:
    """Test real-time support chat functionality"""
    
    @pytest.mark.asyncio
    async def test_queue_management(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test support queue management with skill-based routing"""
        # Create support agents with different skills
        agents = [
            {
                "email": "agent1@vendor.com",
                "skills": ["infusion_pumps", "training"],
                "languages": ["en", "es"],
                "max_capacity": 3
            },
            {
                "email": "agent2@vendor.com", 
                "skills": ["ventilators", "troubleshooting"],
                "languages": ["en"],
                "max_capacity": 5
            },
            {
                "email": "agent3@vendor.com",
                "skills": ["general", "billing"],
                "languages": ["en", "fr"],
                "max_capacity": 4
            }
        ]
        
        created_agents = []
        for agent_data in agents:
            agent = User(
                email=agent_data["email"],
                role="vendor_rep",
                organization_id=1
            )
            db_session.add(agent)
            created_agents.append(agent)
        
        await db_session.commit()
        
        # Set agent availability
        for i, agent in enumerate(created_agents):
            availability = AgentAvailability(
                agent_id=agent.id,
                organization_id=1,
                available=True,
                available_channels=["chat"],
                current_capacity=0,
                max_capacity=agents[i]["max_capacity"],
                skills=agents[i]["skills"],
                languages=agents[i]["languages"]
            )
            db_session.add(availability)
        
        await db_session.commit()
        
        # Simulate 20 users entering queue with different needs
        queue_entries = []
        for i in range(20):
            # Vary the required skills
            if i % 4 == 0:
                required_skill = "infusion_pumps"
                priority = "medium"
            elif i % 4 == 1:
                required_skill = "ventilators" 
                priority = "high"
            elif i % 4 == 2:
                required_skill = "general"
                priority = "low"
            else:
                required_skill = "troubleshooting"
                priority = "critical"
            
            chat_response = await client.post(
                "/api/v1/support/chat/request",
                json={
                    "device_type": required_skill,
                    "issue_description": f"Test issue {i}",
                    "priority": priority,
                    "preferred_language": "en"
                },
                headers={"Authorization": f"Bearer user_token_{i}"}
            )
            
            assert chat_response.status_code in [200, 202]
            queue_entries.append(chat_response.json())
        
        # Check queue status
        queue_response = await client.get(
            "/api/v1/support/queue/status",
            headers={"Authorization": "Bearer admin_token"}
        )
        
        queue_data = queue_response.json()
        assert queue_data["total_waiting"] > 0
        assert queue_data["average_wait_time"] is not None
        
        # Verify skill-based routing
        for entry in queue_entries[:10]:  # Check first 10
            if entry["status"] == "connected":
                # Verify correct agent assignment
                agent_skills = next(
                    a["skills"] for a in agents 
                    if f"agent{entry['agent_id']}@vendor.com" in [a["email"] for a in agents]
                )
                assert entry["requested_skill"] in agent_skills or "general" in agent_skills
        
        # Test priority ordering
        critical_entries = [e for e in queue_entries if e.get("priority") == "critical"]
        high_entries = [e for e in queue_entries if e.get("priority") == "high"]
        
        if critical_entries and high_entries:
            # Critical should be served before high priority
            critical_positions = [e.get("queue_position", 999) for e in critical_entries]
            high_positions = [e.get("queue_position", 999) for e in high_entries]
            
            assert min(critical_positions) < min(high_positions)
    
    @pytest.mark.asyncio
    async def test_chat_features(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """Test live chat features including file sharing and co-browsing"""
        # Start support chat
        chat_response = await client.post(
            "/api/v1/support/chat/start",
            json={
                "device_id": "TEST001",
                "subject": "Device not powering on"
            },
            headers=authenticated_headers
        )
        
        assert chat_response.status_code == 200
        conversation_id = chat_response.json()["conversation_id"]
        
        # Test file sharing
        test_image = b"fake_image_data"  # In real test, use actual image
        
        file_response = await client.post(
            f"/api/v1/support/chat/{conversation_id}/upload",
            files={"file": ("error_photo.jpg", test_image, "image/jpeg")},
            data={"description": "Error message on display"},
            headers=authenticated_headers
        )
        
        assert file_response.status_code == 200
        file_data = file_response.json()
        
        assert file_data["file_id"] is not None
        assert file_data["scan_status"] == "clean"  # Virus scan passed
        assert file_data["file_size"] <= 10 * 1024 * 1024  # 10MB limit
        
        # Send message with file reference
        message_response = await client.post(
            f"/api/v1/support/chat/{conversation_id}/messages",
            json={
                "content": "Here's a photo of the error message",
                "attachments": [file_data["file_id"]]
            },
            headers=authenticated_headers
        )
        
        assert message_response.status_code == 200
        
        # Test screen sharing request
        screen_response = await client.post(
            f"/api/v1/support/chat/{conversation_id}/screen-share",
            json={"request_type": "request_permission"},
            headers=authenticated_headers
        )
        
        assert screen_response.status_code == 200
        assert "session_url" in screen_response.json()
        
        # Test co-browsing
        cobrowse_response = await client.post(
            f"/api/v1/support/chat/{conversation_id}/cobrowse",
            json={"page_url": "/devices/TEST001/troubleshooting"},
            headers=authenticated_headers
        )
        
        assert cobrowse_response.status_code == 200
        cobrowse_data = cobrowse_response.json()
        assert "session_id" in cobrowse_data
        assert cobrowse_data["agent_can_interact"] is False  # View-only by default
        
        # Test canned responses
        canned_response = await client.post(
            f"/api/v1/support/chat/{conversation_id}/messages",
            json={
                "content_type": "canned_response",
                "template_id": "power_troubleshooting_steps"
            },
            headers={"Authorization": "Bearer agent_token"}
        )
        
        assert canned_response.status_code == 200
        assert "1. Check power cable" in canned_response.json()["content"]
        
        # End chat and collect satisfaction
        end_response = await client.post(
            f"/api/v1/support/chat/{conversation_id}/end",
            json={
                "rating": 5,
                "feedback": "Very helpful agent!"
            },
            headers=authenticated_headers
        )
        
        assert end_response.status_code == 200
        
        # Verify transcript available
        transcript_response = await client.get(
            f"/api/v1/support/chat/{conversation_id}/transcript",
            headers=authenticated_headers
        )
        
        assert transcript_response.status_code == 200
        transcript = transcript_response.json()
        
        assert len(transcript["messages"]) > 0
        assert transcript["duration_seconds"] > 0
        assert transcript["satisfaction_rating"] == 5
    
    @pytest.mark.asyncio
    async def test_performance_metrics(
        self, client: AsyncClient, db_session: AsyncSession, admin_headers
    ):
        """Test support performance metrics tracking"""
        # Get support metrics
        metrics_response = await client.get(
            "/api/v1/support/metrics",
            params={
                "start_date": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                "end_date": datetime.utcnow().isoformat(),
                "group_by": "agent"
            },
            headers=admin_headers
        )
        
        assert metrics_response.status_code == 200
        metrics = metrics_response.json()
        
        # Verify metrics structure
        assert "summary" in metrics
        assert metrics["summary"]["total_conversations"] >= 0
        assert metrics["summary"]["average_wait_time_seconds"] >= 0
        assert metrics["summary"]["average_resolution_time_seconds"] >= 0
        assert metrics["summary"]["average_satisfaction_rating"] >= 0
        assert metrics["summary"]["first_response_time_seconds"] >= 0
        
        assert "by_agent" in metrics
        for agent_metrics in metrics["by_agent"]:
            assert "agent_id" in agent_metrics
            assert "conversations_handled" in agent_metrics
            assert "average_rating" in agent_metrics
            assert "utilization_percentage" in agent_metrics
        
        assert "by_queue" in metrics
        assert "abandonment_rate" in metrics["by_queue"]
        assert "transfer_rate" in metrics["by_queue"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
