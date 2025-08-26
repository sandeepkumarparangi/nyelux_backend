"""
AI Chat API endpoints.
Handles conversations with AI assistant about medical devices.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional, Dict, Any
from uuid import uuid4
import logging

from src.api.deps import get_current_user, get_db
from src.db.models.user import User
from src.db.models.chat import ChatConversation, ChatMessage, ChatCitation
from src.db.models.vendor_device import VendorDevice
from src.db.models.gudid_device import GUDIDDevice
from src.schemas.chat import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    ConversationList
)
from src.services.ai_service import get_ai_service
from src.core.exceptions import ExternalServiceError
from src.services.document_service import DocumentService
from src.services.analytics_service import AnalyticsService
from src.core.cache import CacheService

router = APIRouter()
logger = logging.getLogger(__name__)

# Create service instances for this router
document_service = DocumentService()
analytics_service = AnalyticsService()
cache = CacheService()

# AI service is created on demand since it requires API key
ai_service = get_ai_service()
if not ai_service:
    logger.warning("AI service not available - OpenAI API key not configured")


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    *,
    db: AsyncSession = Depends(get_db),
    conversation_in: ConversationCreate,
    current_user: User = Depends(get_current_user)
) -> ChatConversation:
    """
    Create a new chat conversation.
    
    - **device_id**: Optional device ID to provide context
    - **title**: Optional conversation title
    - **context_type**: Type of conversation (general, troubleshooting, training, etc.)
    """
    # Verify device access if provided
    if conversation_in.device_id:
        device = await db.get(VendorDevice, conversation_in.device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )
    
    conversation = ChatConversation(
        user_id=current_user.id,
        device_id=conversation_in.device_id,
        title=conversation_in.title or "New Conversation",
        context_type=conversation_in.context_type or "general"
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    
    # Track analytics
    await analytics_service.track_event(
        db=db,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        event_type="chat_start",
        event_category="engagement",
        resource_type="conversation",
        resource_id=str(conversation.id),
        metadata={"device_id": conversation_in.device_id} if conversation_in.device_id else None
    )
    
    return conversation


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    device_id: Optional[int] = None,
    active_only: bool = True
) -> dict:
    """
    List user's chat conversations.
    
    - **skip**: Number of conversations to skip
    - **limit**: Maximum number of conversations to return
    - **device_id**: Filter by specific device
    - **active_only**: Only return active conversations
    """
    # Build query
    query = select(ChatConversation).where(
        ChatConversation.user_id == current_user.id
    )
    
    if device_id:
        query = query.where(ChatConversation.device_id == device_id)
    
    if active_only:
        query = query.where(ChatConversation.status == 'active')
    
    # Get total count
    count_query = select(func.count()).select_from(ChatConversation).where(
        ChatConversation.user_id == current_user.id
    )
    if device_id:
        count_query = count_query.where(ChatConversation.device_id == device_id)
    if active_only:
        count_query = count_query.where(ChatConversation.status == 'active')
    
    total = await db.scalar(count_query)
    
    # Get conversations
    query = query.order_by(ChatConversation.last_message_at.desc().nullsfirst(), 
                          ChatConversation.created_at.desc())
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    conversations = result.scalars().all()
    
    return {
        "conversations": conversations,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    *,
    db: AsyncSession = Depends(get_db),
    conversation_id: int,
    current_user: User = Depends(get_current_user)
) -> ChatConversation:
    """Get a specific conversation by ID."""
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    return conversation


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    *,
    db: AsyncSession = Depends(get_db),
    conversation_id: int,
    message_in: MessageCreate,
    current_user: User = Depends(get_current_user)
) -> ChatMessage:
    """
    Send a message in a conversation and get AI response.
    Implements RAG with device documentation.
    
    - **content**: The message content
    - **attachments**: Optional list of attachment URLs
    """
    # Get conversation
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.status != 'active':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation is not active"
        )
    
    # Create user message
    user_message = ChatMessage(
        conversation_id=conversation_id,
        role="user",
        content=message_in.content
    )
    db.add(user_message)
    await db.flush()
    
    # Check if AI service is available
    if not ai_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI chat service is not available. OpenAI API key not configured."
        )
    
    try:
        # Get conversation history for context
        messages_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
            .limit(10)  # Last 10 messages for context
        )
        history = messages_result.scalars().all()
        
        # Get device context if available
        device_context = None
        rag_documents = []
        
        if conversation.device_id:
            # Get device information with GUDID data
            device_result = await db.execute(
                select(VendorDevice, GUDIDDevice)
                .join(GUDIDDevice, VendorDevice.gudid_device_di == GUDIDDevice.primary_di)
                .where(VendorDevice.id == conversation.device_id)
            )
            result = device_result.first()
            
            if result:
                vendor_device, gudid_device = result
                device_context = {
                    "device_name": vendor_device.custom_name or gudid_device.device_name,
                    "manufacturer": gudid_device.manufacturer_name,
                    "model_number": gudid_device.model_number,
                    "device_class": gudid_device.device_class,
                    "device_description": gudid_device.device_description,
                    "mri_safety": gudid_device.mri_safety,
                    "sterile": gudid_device.sterile,
                    "single_use": gudid_device.single_use,
                    "implantable": gudid_device.implantable,
                    "specifications": vendor_device.specifications,
                    "features": vendor_device.features
                }
                
                # Get relevant documents for RAG
                rag_documents = await document_service.get_document_context_for_rag(
                    db=db,
                    device_id=conversation.device_id,
                    query=message_in.content,
                    organization_id=current_user.organization_id,
                    limit=5
                )
        
        # Build message history for AI
        message_history = [
            {"role": msg.role, "content": msg.content}
            for msg in history
        ]
        
        # Get AI response
        ai_response = await ai_service.get_device_answer(
            question=message_in.content,
            device_context=device_context,
            citations=rag_documents,
            conversation_history=message_history
        )
        
        # Create AI message
        ai_message = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=ai_response["answer"],
            model_used=ai_response.get("model", "gpt-4"),
            tokens_used=ai_response.get("tokens_used", 0),
            confidence_score=ai_response.get("confidence_score"),
            has_citations=len(ai_response.get("citations_used", 0)) > 0
        )
        db.add(ai_message)
        await db.flush()
        
        # Add citations if any
        if rag_documents and ai_response.get("citations_used", 0) > 0:
            for i, doc in enumerate(rag_documents[:ai_response.get("citations_used", 0)]):
                citation = ChatCitation(
                    message_id=ai_message.id,
                    source_type="document",
                    source_id=str(doc["document_id"]),
                    source_title=doc["document_title"],
                    page_number=doc.get("page_number"),
                    section_reference=f"Chunk {doc['chunk_index']}",
                    excerpt=doc["text"][:500],  # First 500 chars
                    relevance_score=doc.get("relevance_score", 0.0)
                )
                db.add(citation)
        
        # Update conversation stats
        conversation.add_message("assistant", ai_response["answer"], ai_response.get("tokens_used", 0))
        
        await db.commit()
        await db.refresh(ai_message)
        
        # Load citations for response
        if ai_message.has_citations:
            citations_result = await db.execute(
                select(ChatCitation).where(ChatCitation.message_id == ai_message.id)
            )
            ai_message.citations = citations_result.scalars().all()
        
        # Clear cache
        await cache.delete(f"conversation:{conversation_id}:messages")
        
        # Track analytics
        await analytics_service.track_event(
            db=db,
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="chat_message",
            event_category="engagement",
            resource_type="conversation",
            resource_id=str(conversation_id),
            metadata={
                "device_id": conversation.device_id,
                "message_length": len(message_in.content),
                "has_citations": ai_message.has_citations,
                "tokens_used": ai_message.tokens_used
            }
        )
        
        return ai_message
        
    except Exception as e:
        logger.error(f"Chat error for conversation {conversation_id}: {e}")
        await db.rollback()
        
        # Create error message
        error_message = ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content="I apologize, but I encountered an error processing your request. Please try again."
        )
        db.add(error_message)
        await db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable"
        )


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    *,
    db: AsyncSession = Depends(get_db),
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
) -> List[ChatMessage]:
    """
    Get messages in a conversation with pagination.
    
    - **skip**: Number of messages to skip
    - **limit**: Maximum number of messages to return
    """
    from sqlalchemy.orm import selectinload
    
    # Verify conversation ownership
    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Check cache
    cache_key = f"conversation:{conversation_id}:messages:{skip}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    
    # Get messages with citations
    result = await db.execute(
        select(ChatMessage)
        .options(selectinload(ChatMessage.citations))
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    
    messages = result.scalars().all()
    
    # Cache for 5 minutes
    await cache.set(cache_key, messages, expire=300)
    
    return messages


@router.post("/conversations/{conversation_id}/messages/{message_id}/feedback")
async def submit_feedback(
    *,
    db: AsyncSession = Depends(get_db),
    conversation_id: int,
    message_id: int,
    rating: int = Query(..., ge=1, le=5),
    comment: Optional[str] = None,
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Submit feedback for an AI message.
    
    - **rating**: Rating from 1-5
    - **comment**: Optional feedback comment
    """
    # Verify message ownership
    result = await db.execute(
        select(ChatMessage)
        .join(ChatConversation)
        .where(
            and_(
                ChatMessage.id == message_id,
                ChatMessage.conversation_id == conversation_id,
                ChatConversation.user_id == current_user.id,
                ChatMessage.role == "assistant"
            )
        )
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Update feedback
    message.feedback_rating = rating
    message.feedback_comment = comment
    
    await db.commit()
    
    # Track analytics
    await analytics_service.track_event(
        db=db,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        event_type="chat_feedback",
        event_category="engagement",
        resource_type="message",
        resource_id=str(message_id),
        value=float(rating),
        metadata={"comment": comment} if comment else None
    )
    
    return {"status": "success", "message": "Feedback recorded"}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    *,
    db: AsyncSession = Depends(get_db),
    conversation_id: int,
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Archive a conversation (soft delete).
    """
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Archive instead of hard delete
    conversation.status = 'archived'
    await db.commit()
    
    # Clear cache
    await cache.delete(f"conversation:{conversation_id}:*")
    
    return {"status": "success", "message": "Conversation archived"}


@router.post("/conversations/{conversation_id}/export")
async def export_conversation(
    *,
    db: AsyncSession = Depends(get_db),
    conversation_id: int,
    format: str = Query("json", regex="^(txt|pdf|json)$"),
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Export a conversation in various formats.
    
    - **format**: Export format (txt, pdf, json)
    """
    from sqlalchemy.orm import selectinload
    
    # Get conversation with messages
    result = await db.execute(
        select(ChatConversation)
        .options(selectinload(ChatConversation.messages).selectinload(ChatMessage.citations))
        .where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if format == "json":
        # Return JSON immediately
        export_data = {
            "conversation_id": conversation.id,
            "title": conversation.title,
            "device_id": conversation.device_id,
            "created_at": conversation.created_at.isoformat(),
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat(),
                    "citations": [
                        {
                            "source_title": c.source_title,
                            "page_number": c.page_number,
                            "excerpt": c.excerpt
                        }
                        for c in msg.citations
                    ] if msg.citations else []
                }
                for msg in conversation.messages
            ]
        }
        
        return {
            "status": "success",
            "format": "json",
            "data": export_data
        }
    
    else:
        # Queue export job for PDF/TXT
        from src.background.worker import worker
        
        export_id = str(uuid4())
        job_id = await worker.add_job(
            job_type="export_conversation",
            payload={
                "conversation_id": conversation_id,
                "user_id": current_user.id,
                "format": format,
                "export_id": export_id
            },
            priority=3
        )
        
        return {
            "status": "processing",
            "message": f"Conversation export in {format} format is being processed",
            "export_id": export_id,
            "job_id": job_id
        }


@router.get("/device/{device_id}/suggested-questions")
async def get_suggested_questions(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[str]:
    """
    Get AI-suggested questions for a specific device.
    Based on device type and common queries.
    """
    # Get device info
    device_result = await db.execute(
        select(VendorDevice, GUDIDDevice)
        .join(GUDIDDevice, VendorDevice.gudid_device_di == GUDIDDevice.primary_di)
        .where(VendorDevice.id == device_id)
    )
    result = device_result.first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    vendor_device, gudid_device = result
    
    # Generate contextual suggestions based on device type
    suggestions = [
        f"How do I properly maintain the {gudid_device.device_name}?",
        f"What are the safety precautions for using this device?",
        f"What is the recommended cleaning procedure?",
        "What are the common troubleshooting steps?",
        "How often should this device be calibrated?"
    ]
    
    # Add specific questions based on device characteristics
    if gudid_device.mri_safety:
        suggestions.append(f"What are the MRI safety considerations ({gudid_device.mri_safety})?")
    
    if gudid_device.sterile:
        suggestions.append("How should I handle the sterile packaging?")
    
    if gudid_device.implantable:
        suggestions.append("What is the expected lifespan of this implant?")
        suggestions.append("What are the post-implantation care instructions?")
    
    if vendor_device.training_required:
        suggestions.append("What training is required to use this device?")
    
    return suggestions[:8]  # Return top 8 suggestions
