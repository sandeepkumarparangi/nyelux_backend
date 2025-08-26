"""
AI-Powered Chat System Tests
Based on NYELUX Test Coverage Document Section 5
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import json
import asyncio
from unittest.mock import patch, MagicMock

from src.db.models.chat import ChatConversation, ChatMessage, ChatCitation
from src.db.models.device_document import DeviceDocument
from src.db.models.document_chunk import DocumentChunk
from src.db.models.gudid_device import GUDIDDevice
from src.services.ai_service import AIService


class TestConversationManagement:
    """Test cases TC-AI-001 through TC-AI-004"""
    
    @pytest.mark.asyncio
    async def test_context_aware_responses(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-AI-001: Context-Aware Responses"""
        # Create test device
        device = GUDIDDevice(
            primary_di="AI001",
            device_name="SmartPump Pro X500",
            manufacturer_name="MedTech Solutions",
            device_class="II",
            device_description="Advanced infusion pump with smart dosing",
            device_size_text="Dimensions: 25cm x 15cm x 10cm",
            mri_safety="MR Conditional"
        )
        db_session.add(device)
        await db_session.commit()
        
        # Start conversation about specific device
        conversation_response = await client.post(
            "/api/v1/chat/conversations",
            json={
                "device_id": device.primary_di,
                "title": "SmartPump Pro Questions"
            },
            headers=authenticated_headers
        )
        
        assert conversation_response.status_code == 201
        conversation_id = conversation_response.json()["id"]
        
        # First question - direct reference
        message1_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "What are the dimensions of this device?"},
            headers=authenticated_headers
        )
        
        assert message1_response.status_code == 200
        message1_data = message1_response.json()
        
        # Verify response contains dimension information
        assert "25cm x 15cm x 10cm" in message1_data["content"]
        assert message1_data["role"] == "assistant"
        assert message1_data["has_citations"] is True
        
        # Second question - pronoun reference
        message2_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "Is it MRI safe?"},
            headers=authenticated_headers
        )
        
        assert message2_response.status_code == 200
        message2_data = message2_response.json()
        
        # Verify AI understands "it" refers to the device
        assert "MR Conditional" in message2_data["content"]
        assert "SmartPump Pro" in message2_data["content"] or "device" in message2_data["content"]
        
        # Third question - context from previous answers
        message3_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "Given its size and MRI status, can it be used in the MRI suite?"},
            headers=authenticated_headers
        )
        
        assert message3_response.status_code == 200
        message3_data = message3_response.json()
        
        # Verify context retention across multiple turns
        assert "conditional" in message3_data["content"].lower()
        assert message3_data["confidence_score"] >= 0.7
        
        # Verify conversation history is maintained
        history_response = await client.get(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            headers=authenticated_headers
        )
        
        assert history_response.status_code == 200
        messages = history_response.json()["messages"]
        assert len(messages) == 6  # 3 user + 3 assistant messages
    
    @pytest.mark.asyncio
    async def test_rag_document_integration(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-AI-002: RAG Document Integration"""
        # Create device and upload manual
        device = GUDIDDevice(
            primary_di="RAG001",
            device_name="UltraScan 3000",
            manufacturer_name="Imaging Corp"
        )
        db_session.add(device)
        
        # Create document with specific content
        document = DeviceDocument(
            device_id=1,  # Will be updated after device creation
            document_type="manual",
            title="UltraScan 3000 User Manual",
            file_url="s3://bucket/manual.pdf",
            page_count=150
        )
        db_session.add(document)
        await db_session.commit()
        
        # Create document chunks for RAG
        chunks = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                chunk_text="Chapter 3: Maintenance. Page 45. The device requires calibration every 6 months for optimal performance.",
                page_number=45,
                section_heading="Maintenance Schedule"
            ),
            DocumentChunk(
                document_id=document.id,
                chunk_index=1,
                chunk_text="Page 46. During calibration, ensure the device is at room temperature (20-25°C) and follow the step-by-step procedure outlined below.",
                page_number=46,
                section_heading="Calibration Procedure"
            )
        ]
        
        for chunk in chunks:
            db_session.add(chunk)
        await db_session.commit()
        
        # Start conversation
        conv_response = await client.post(
            "/api/v1/chat/conversations",
            json={"device_id": device.primary_di},
            headers=authenticated_headers
        )
        conversation_id = conv_response.json()["id"]
        
        # Ask specific question from manual
        message_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "How often does the UltraScan 3000 need calibration?"},
            headers=authenticated_headers
        )
        
        assert message_response.status_code == 200
        response_data = message_response.json()
        
        # Verify answer quotes manual
        assert "6 months" in response_data["content"]
        assert response_data["has_citations"] is True
        
        # Get citations
        citations_response = await client.get(
            f"/api/v1/chat/messages/{response_data['id']}/citations",
            headers=authenticated_headers
        )
        
        assert citations_response.status_code == 200
        citations = citations_response.json()["citations"]
        
        # Verify citation includes page number
        assert len(citations) > 0
        citation = citations[0]
        assert citation["page_number"] == 45
        assert citation["source_title"] == "UltraScan 3000 User Manual"
        assert "calibration every 6 months" in citation["excerpt"]
        assert citation["relevance_score"] >= 0.8
        
        # Test no hallucination - ask about non-existent feature
        hallucination_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "Does it have a built-in WiFi module?"},
            headers=authenticated_headers
        )
        
        assert hallucination_response.status_code == 200
        hall_data = hallucination_response.json()
        
        # Should indicate information not found in available sources
        assert "not found" in hall_data["content"].lower() or "no information" in hall_data["content"].lower()
        assert hall_data["confidence_score"] < 0.5
    
    @pytest.mark.asyncio
    async def test_token_usage_tracking(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-AI-003: Token Usage Tracking"""
        # Create conversation
        conv_response = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Token Test Conversation"},
            headers=authenticated_headers
        )
        conversation_id = conv_response.json()["id"]
        
        # Have 10-message conversation
        total_tokens = 0
        messages = [
            "What is an infusion pump?",
            "What are the main safety features?",
            "How do I troubleshoot error code E001?",
            "What's the difference between volumetric and syringe pumps?",
            "Can you explain the occlusion detection mechanism?",
            "What are the maintenance requirements?",
            "How do I perform a flow rate calibration?",
            "What are the alarm priorities?",
            "How do I clean the device properly?",
            "What's the expected lifespan of the pump?"
        ]
        
        for i, message in enumerate(messages):
            response = await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json={"content": message},
                headers=authenticated_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "tokens_used" in data
            assert data["tokens_used"] > 0
            total_tokens += data["tokens_used"]
        
        # Get conversation summary
        summary_response = await client.get(
            f"/api/v1/chat/conversations/{conversation_id}",
            headers=authenticated_headers
        )
        
        assert summary_response.status_code == 200
        summary = summary_response.json()
        
        # Verify token tracking
        assert summary["total_messages"] == 20  # 10 user + 10 assistant
        assert summary["total_tokens_used"] == total_tokens
        assert summary["total_tokens_used"] > 1000  # Reasonable for 10 exchanges
        
        # Verify cost calculation
        assert "estimated_cost" in summary
        assert summary["estimated_cost"] > 0
        
        # Test cost breakdown
        cost_response = await client.get(
            f"/api/v1/chat/conversations/{conversation_id}/cost-breakdown",
            headers=authenticated_headers
        )
        
        assert cost_response.status_code == 200
        cost_data = cost_response.json()
        
        assert "input_tokens" in cost_data
        assert "output_tokens" in cost_data
        assert "total_cost_usd" in cost_data
        assert cost_data["model_used"] == "gpt-4"
    
    @pytest.mark.asyncio
    async def test_response_time_sla(
        self, client: AsyncClient, authenticated_headers
    ):
        """TC-AI-004: Response Time SLA"""
        # Create conversation
        conv_response = await client.post(
            "/api/v1/chat/conversations",
            headers=authenticated_headers
        )
        conversation_id = conv_response.json()["id"]
        
        # Test simple question
        simple_start = datetime.utcnow()
        simple_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "What is a catheter?"},
            headers=authenticated_headers
        )
        simple_duration = (datetime.utcnow() - simple_start).total_seconds()
        
        assert simple_response.status_code == 200
        assert simple_duration < 3.0  # Complete response < 3 seconds
        
        # Test complex technical question
        complex_start = datetime.utcnow()
        
        # Use streaming to measure time to first token
        stream_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={
                "content": "Explain the detailed physics behind MRI conditional ratings for implantable devices, including specific absorption rate calculations and magnetic field interactions.",
                "stream": True
            },
            headers=authenticated_headers
        )
        
        # Measure time to first chunk
        first_chunk_time = None
        complete_response = ""
        
        async for line in stream_response.aiter_lines():
            if first_chunk_time is None:
                first_chunk_time = (datetime.utcnow() - complex_start).total_seconds()
            
            if line.startswith("data: "):
                chunk_data = json.loads(line[6:])
                if "content" in chunk_data:
                    complete_response += chunk_data["content"]
        
        total_duration = (datetime.utcnow() - complex_start).total_seconds()
        
        # Assertions
        assert first_chunk_time < 1.0  # First token < 1 second
        assert total_duration < 3.0  # Complete response < 3 seconds
        assert len(complete_response) > 100  # Substantial response


class TestDocumentProcessing:
    """Test cases TC-AI-005 through TC-AI-006"""
    
    @pytest.mark.asyncio
    async def test_pdf_text_extraction(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-AI-005: PDF Text Extraction"""
        # Test different PDF types
        test_files = [
            {
                "name": "text_based.pdf",
                "type": "text",
                "expected_accuracy": 0.95,
                "content": "This is a text-based PDF with clear content."
            },
            {
                "name": "scanned_document.pdf",
                "type": "scanned",
                "expected_accuracy": 0.90,
                "content": "Scanned document requiring OCR processing."
            },
            {
                "name": "mixed_content.pdf",
                "type": "mixed",
                "expected_accuracy": 0.92,
                "content": "Mixed PDF with text and scanned images."
            }
        ]
        
        for test_file in test_files:
            # Upload document
            with open(f"test_fixtures/{test_file['name']}", "rb") as f:
                upload_response = await client.post(
                    "/api/v1/documents/upload",
                    files={"file": (test_file["name"], f, "application/pdf")},
                    data={"document_type": "manual"},
                    headers=authenticated_headers
                )
            
            assert upload_response.status_code == 201
            document_id = upload_response.json()["id"]
            
            # Wait for processing
            await asyncio.sleep(2)
            
            # Get extracted text
            extraction_response = await client.get(
                f"/api/v1/documents/{document_id}/extracted-text",
                headers=authenticated_headers
            )
            
            assert extraction_response.status_code == 200
            extracted_data = extraction_response.json()
            
            # Verify extraction quality
            extracted_text = extracted_data["text"]
            assert len(extracted_text) > 0
            
            # Calculate accuracy (simplified - in real test, use proper metrics)
            if test_file["type"] == "text":
                assert extracted_data["extraction_method"] == "pdfplumber"
                assert extracted_data["confidence"] >= test_file["expected_accuracy"]
            elif test_file["type"] == "scanned":
                assert extracted_data["extraction_method"] == "tesseract"
                assert extracted_data["confidence"] >= test_file["expected_accuracy"]
            
            # Verify table extraction
            if "tables" in extracted_data:
                for table in extracted_data["tables"]:
                    assert "headers" in table
                    assert "rows" in table
                    assert table["accuracy"] >= 0.85
    
    @pytest.mark.asyncio
    async def test_document_chunking_strategy(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """TC-AI-006: Document Chunking Strategy"""
        # Upload a large manual (100+ pages)
        large_manual_content = self._generate_large_manual()
        
        upload_response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("large_manual.pdf", large_manual_content, "application/pdf")},
            data={
                "document_type": "manual",
                "device_id": "TEST001"
            },
            headers=authenticated_headers
        )
        
        assert upload_response.status_code == 201
        document_id = upload_response.json()["id"]
        
        # Wait for processing
        await asyncio.sleep(5)
        
        # Get chunks
        chunks_response = await client.get(
            f"/api/v1/documents/{document_id}/chunks",
            headers=authenticated_headers
        )
        
        assert chunks_response.status_code == 200
        chunks = chunks_response.json()["chunks"]
        
        # Verify chunking parameters
        for i, chunk in enumerate(chunks):
            # Check chunk size (tokens)
            assert 800 <= chunk["token_count"] <= 1200  # 1000 +/- 20%
            
            # Check overlap with next chunk
            if i < len(chunks) - 1:
                next_chunk = chunks[i + 1]
                overlap_tokens = self._calculate_overlap(chunk["text"], next_chunk["text"])
                assert 150 <= overlap_tokens <= 250  # 200 +/- 50 tokens
            
            # Verify metadata
            assert "chunk_index" in chunk
            assert "page_numbers" in chunk
            assert "section_heading" in chunk
            assert chunk["chunk_index"] == i
        
        # Test boundary preservation
        # Verify no information lost at chunk boundaries
        full_text = " ".join([c["text"] for c in chunks])
        
        # Check specific boundary cases
        test_phrases = [
            "CAUTION: Do not exceed maximum pressure",
            "Table 4.1: Maintenance Schedule",
            "Step 3: Connect the power cable"
        ]
        
        for phrase in test_phrases:
            # Each phrase should appear in at least one chunk completely
            found_complete = any(phrase in chunk["text"] for chunk in chunks)
            assert found_complete, f"Phrase '{phrase}' was split across chunks"
    
    def _generate_large_manual(self):
        """Generate a large PDF manual for testing"""
        # In real implementation, create actual PDF
        return b"fake_pdf_content" * 10000
    
    def _calculate_overlap(self, text1, text2):
        """Calculate token overlap between chunks"""
        # Simplified - in real implementation, use tokenizer
        words1 = set(text1.split()[-50:])  # Last 50 words
        words2 = set(text2.split()[:50])   # First 50 words
        return len(words1.intersection(words2))


class TestAIErrorHandling:
    """Test AI system error scenarios"""
    
    @pytest.mark.asyncio
    async def test_openai_api_failure_handling(
        self, client: AsyncClient, authenticated_headers, monkeypatch
    ):
        """Test graceful handling when OpenAI API is down"""
        # Mock OpenAI failure
        def mock_openai_error(*args, **kwargs):
            raise Exception("OpenAI API unavailable")
        
        monkeypatch.setattr("openai.ChatCompletion.acreate", mock_openai_error)
        
        # Try to send message
        conv_response = await client.post(
            "/api/v1/chat/conversations",
            headers=authenticated_headers
        )
        conversation_id = conv_response.json()["id"]
        
        message_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "Test message"},
            headers=authenticated_headers
        )
        
        assert message_response.status_code == 503
        error_data = message_response.json()
        assert "AI service temporarily unavailable" in error_data["detail"]
        assert "fallback_available" in error_data
        
        # Verify conversation still exists
        conv_check = await client.get(
            f"/api/v1/chat/conversations/{conversation_id}",
            headers=authenticated_headers
        )
        assert conv_check.status_code == 200
    
    @pytest.mark.asyncio
    async def test_token_limit_exceeded(
        self, client: AsyncClient, authenticated_headers
    ):
        """Test handling of token limit exceeded"""
        # Create very long message
        long_content = "Explain in extreme detail " * 1000  # Exceed token limit
        
        conv_response = await client.post(
            "/api/v1/chat/conversations",
            headers=authenticated_headers
        )
        conversation_id = conv_response.json()["id"]
        
        response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": long_content},
            headers=authenticated_headers
        )
        
        assert response.status_code == 400
        assert "Message too long" in response.json()["detail"]
        assert "max_tokens" in response.json()


class TestChatExportAndHistory:
    """Test chat export and history features"""
    
    @pytest.mark.asyncio
    async def test_conversation_export(
        self, client: AsyncClient, db_session: AsyncSession, authenticated_headers
    ):
        """Test exporting chat history with citations"""
        # Create conversation with multiple messages
        conv_response = await client.post(
            "/api/v1/chat/conversations",
            json={"title": "Export Test"},
            headers=authenticated_headers
        )
        conversation_id = conv_response.json()["id"]
        
        # Add messages
        messages = [
            ("What is a ventilator?", "A ventilator is a medical device..."),
            ("How does it work?", "Ventilators work by...")
        ]
        
        for user_msg, ai_response in messages:
            await client.post(
                f"/api/v1/chat/conversations/{conversation_id}/messages",
                json={"content": user_msg},
                headers=authenticated_headers
            )
        
        # Export as PDF
        pdf_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/export",
            json={"format": "pdf", "include_citations": True},
            headers=authenticated_headers
        )
        
        assert pdf_response.status_code == 200
        assert pdf_response.headers["content-type"] == "application/pdf"
        
        # Export as Markdown
        md_response = await client.post(
            f"/api/v1/chat/conversations/{conversation_id}/export",
            json={"format": "markdown", "include_citations": True},
            headers=authenticated_headers
        )
        
        assert md_response.status_code == 200
        content = md_response.text
        assert "# Export Test" in content
        assert "## User:" in content
        assert "## Assistant:" in content
        assert "### Citations:" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
