"""
Vendor Chat API endpoints.
Handles chat functionality with vendor-specific context.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
import logging
import json

from src.db.session import get_db
from src.db.models.user import User
from src.db.models.vendor_profile import VendorProfile, VendorChatKnowledge
from src.db.models.vendor_device import VendorDevice
from src.db.models.gudid_device import GUDIDDevice
from src.db.models.device_document import DeviceDocument
from src.db.models.chat import ChatConversation, ChatMessage
from src.db.models.vendor_lead import VendorLead
from src.api.deps import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vendor-chat", tags=["vendor-chat"])


@router.post("/{url_slug}/start")
async def start_vendor_chat_session(
    url_slug: str,
    device_id: Optional[int] = None,
    visitor_info: Optional[Dict[str, Any]] = None,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Start a chat session on vendor page.
    Can be anonymous or authenticated.
    Tracks for lead generation.
    """
    
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile).where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True,
                VendorProfile.chat_enabled == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor chat not available"
        )
    
    # Get device context if specified
    device_context = None
    if device_id:
        device_result = await db.execute(
            select(VendorDevice).where(
                and_(
                    VendorDevice.id == device_id,
                    VendorDevice.organization_id == vendor_profile.organization_id
                )
            ).options(selectinload(VendorDevice.gudid_device))
        )
        device = device_result.scalar_one_or_none()
        
        if device:
            device_context = {
                "device_id": device.id,
                "device_name": device.display_name,
                "manufacturer": device.manufacturer_name,
                "fda_class": device.gudid_device.device_class if device.gudid_device else None,
                "description": device.gudid_device.device_description if device.gudid_device else None
            }
    
    # Create chat session
    session_id = f"vendor-{vendor_profile.id}-{datetime.utcnow().timestamp()}"
    
    # Track as potential lead if visitor info provided
    if visitor_info and visitor_info.get('email'):
        # Check if lead exists
        existing_lead = await db.execute(
            select(VendorLead).where(
                and_(
                    VendorLead.vendor_profile_id == vendor_profile.id,
                    VendorLead.email == visitor_info['email']
                )
            )
        )
        lead = existing_lead.scalar_one_or_none()
        
        if not lead:
            # Create new lead
            lead = VendorLead(
                vendor_profile_id=vendor_profile.id,
                organization_id=vendor_profile.organization_id,
                email=visitor_info['email'],
                first_name=visitor_info.get('first_name'),
                last_name=visitor_info.get('last_name'),
                source_type='chat',
                device_id=device_id,
                chat_questions=[]
            )
            db.add(lead)
            await db.commit()
    
    # Get vendor-specific knowledge
    knowledge_query = select(VendorChatKnowledge).where(
        and_(
            VendorChatKnowledge.vendor_profile_id == vendor_profile.id,
            VendorChatKnowledge.is_active == True,
            VendorChatKnowledge.approved == True
        )
    )
    
    if device_id:
        knowledge_query = knowledge_query.where(
            or_(
                VendorChatKnowledge.device_id == device_id,
                VendorChatKnowledge.device_id.is_(None)
            )
        )
    
    knowledge_query = knowledge_query.limit(20)
    result = await db.execute(knowledge_query)
    knowledge_items = result.scalars().all()
    
    # Format response
    return {
        "session_id": session_id,
        "vendor": {
            "name": vendor_profile.display_name,
            "welcome_message": vendor_profile.chat_welcome_message,
            "chat_enabled": True
        },
        "device_context": device_context,
        "knowledge_base": [
            {
                "question": item.question,
                "answer": item.answer,
                "category": item.category
            }
            for item in knowledge_items
        ],
        "suggested_questions": [
            "What are the key features of this device?",
            "Is training available for this equipment?",
            "How can I request a demo?",
            "What support options are available?",
            "Can I get pricing information?"
        ]
    }


@router.post("/{url_slug}/message")
async def send_vendor_chat_message(
    url_slug: str,
    session_id: str,
    message: str,
    device_id: Optional[int] = None,
    visitor_email: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Process chat message in vendor context.
    Uses vendor-specific knowledge and device information.
    """
    
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile).where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True,
                VendorProfile.chat_enabled == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor chat not available"
        )
    
    # Track question if lead exists
    if visitor_email:
        lead_result = await db.execute(
            select(VendorLead).where(
                and_(
                    VendorLead.vendor_profile_id == vendor_profile.id,
                    VendorLead.email == visitor_email
                )
            )
        )
        lead = lead_result.scalar_one_or_none()
        
        if lead:
            # Add question to lead's chat history
            if not lead.chat_questions:
                lead.chat_questions = []
            
            lead.chat_questions.append({
                "timestamp": datetime.utcnow().isoformat(),
                "question": message,
                "device_id": device_id
            })
            
            # Update lead score based on engagement
            lead.lead_score = min(lead.lead_score + 5, 100)
            
            await db.commit()
    
    # Search vendor knowledge base
    knowledge_results = await db.execute(
        select(VendorChatKnowledge).where(
            and_(
                VendorChatKnowledge.vendor_profile_id == vendor_profile.id,
                VendorChatKnowledge.is_active == True,
                or_(
                    VendorChatKnowledge.question.ilike(f"%{message}%"),
                    VendorChatKnowledge.keywords.contains([word.lower() for word in message.split()])
                )
            )
        ).order_by(
            VendorChatKnowledge.usage_count.desc()
        ).limit(3)
    )
    knowledge_matches = knowledge_results.scalars().all()
    
    # Build context for response
    context = {
        "vendor_name": vendor_profile.display_name,
        "vendor_specialties": vendor_profile.specialties,
        "device_context": None,
        "knowledge_matches": []
    }
    
    # Add device context if available
    if device_id:
        device_result = await db.execute(
            select(VendorDevice).where(
                and_(
                    VendorDevice.id == device_id,
                    VendorDevice.organization_id == vendor_profile.organization_id
                )
            ).options(selectinload(VendorDevice.gudid_device))
        )
        device = device_result.scalar_one_or_none()
        
        if device:
            context["device_context"] = {
                "name": device.display_name,
                "manufacturer": device.manufacturer_name,
                "features": device.get_features_list(),
                "specifications": device.get_specifications_list() if device.access_level == 'public' else None,
                "training_required": device.training_required,
                "fda_info": {
                    "class": device.gudid_device.device_class if device.gudid_device else None,
                    "description": device.gudid_device.device_description if device.gudid_device else None,
                    "mri_safety": device.gudid_device.mri_safety if device.gudid_device else None
                } if device.gudid_device else None
            }
    
    # Add knowledge matches
    for match in knowledge_matches:
        context["knowledge_matches"].append({
            "question": match.question,
            "answer": match.answer,
            "confidence": 0.9  # High confidence for exact matches
        })
        
        # Update usage count
        match.usage_count += 1
        match.last_used_at = datetime.utcnow()
    
    await db.commit()
    
    # Generate response based on context
    # In production, this would call OpenAI with the context
    # For now, return a structured response
    
    response_text = ""
    citations = []
    
    if knowledge_matches:
        # Use the best matching answer
        response_text = knowledge_matches[0].answer
        citations.append({
            "source": "Vendor Knowledge Base",
            "confidence": 0.9
        })
    elif "pricing" in message.lower() or "cost" in message.lower():
        response_text = (
            f"For pricing information on {vendor_profile.display_name} products, "
            "please submit your contact information and a representative will provide "
            "you with detailed pricing based on your specific needs."
        )
        citations.append({
            "source": "Standard Response",
            "confidence": 0.8
        })
    elif "demo" in message.lower() or "trial" in message.lower():
        response_text = (
            f"I'd be happy to help you schedule a demo of {vendor_profile.display_name} products. "
            "Please provide your contact information and preferred dates, and our team will "
            "coordinate with you directly."
        )
        citations.append({
            "source": "Standard Response",
            "confidence": 0.8
        })
    elif "support" in message.lower() or "help" in message.lower():
        response_text = (
            f"For support with {vendor_profile.display_name} products, you can:\n"
            f"- Email: {vendor_profile.support_email or 'support@' + url_slug + '.com'}\n"
            f"- Phone: {vendor_profile.support_phone or 'Contact us for phone support'}\n"
            "- Submit a service request through the portal"
        )
        citations.append({
            "source": "Vendor Information",
            "confidence": 1.0
        })
    else:
        # Generic response with device context
        if context.get("device_context"):
            device_name = context["device_context"]["name"]
            response_text = (
                f"Thank you for your interest in the {device_name}. "
                "This device is part of our comprehensive medical device portfolio. "
                "How can I help you learn more about this specific device?"
            )
        else:
            response_text = (
                f"Thank you for contacting {vendor_profile.display_name}. "
                "I'm here to help you with information about our medical devices. "
                "Could you please be more specific about what you'd like to know?"
            )
        
        citations.append({
            "source": "General Response",
            "confidence": 0.6
        })
    
    # Check if this might generate a lead
    lead_trigger = any(keyword in message.lower() for keyword in [
        "pricing", "quote", "demo", "trial", "purchase", "buy", "contact"
    ])
    
    return {
        "session_id": session_id,
        "response": response_text,
        "citations": citations,
        "suggestions": [
            "Request a demo",
            "Get pricing information",
            "View technical specifications",
            "Schedule training",
            "Contact support"
        ],
        "lead_capture_suggested": lead_trigger and not visitor_email,
        "context_used": {
            "vendor_knowledge": len(knowledge_matches) > 0,
            "device_specific": device_id is not None,
            "fda_data": bool(context.get("device_context", {}).get("fda_info"))
        }
    }


@router.post("/{url_slug}/feedback")
async def submit_chat_feedback(
    url_slug: str,
    session_id: str,
    message_id: Optional[str] = None,
    helpful: bool = True,
    feedback: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Submit feedback on chat response quality.
    Helps improve vendor-specific responses.
    """
    
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile).where(
            VendorProfile.url_slug == url_slug
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )
    
    # Log feedback (in production, this would update the knowledge base effectiveness)
    logger.info(
        f"Chat feedback for vendor {url_slug}: "
        f"Session {session_id}, Helpful: {helpful}, Feedback: {feedback}"
    )
    
    return {"message": "Thank you for your feedback"}


@router.get("/{url_slug}/suggested-topics")
async def get_suggested_chat_topics(
    url_slug: str,
    device_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get suggested topics for chat based on popular questions.
    """
    
    # Get vendor profile
    result = await db.execute(
        select(VendorProfile).where(
            and_(
                VendorProfile.url_slug == url_slug,
                VendorProfile.is_active == True
            )
        )
    )
    vendor_profile = result.scalar_one_or_none()
    
    if not vendor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )
    
    # Get popular questions from knowledge base
    query = select(VendorChatKnowledge).where(
        and_(
            VendorChatKnowledge.vendor_profile_id == vendor_profile.id,
            VendorChatKnowledge.is_active == True,
            VendorChatKnowledge.is_public == True
        )
    )
    
    if device_id:
        query = query.where(
            or_(
                VendorChatKnowledge.device_id == device_id,
                VendorChatKnowledge.device_id.is_(None)
            )
        )
    
    query = query.order_by(
        VendorChatKnowledge.usage_count.desc(),
        VendorChatKnowledge.helpful_count.desc()
    ).limit(10)
    
    result = await db.execute(query)
    popular_questions = result.scalars().all()
    
    topics = []
    categories = {}
    
    for question in popular_questions:
        category = question.category or "General"
        if category not in categories:
            categories[category] = []
        
        categories[category].append({
            "question": question.question,
            "popularity": question.usage_count,
            "effectiveness": question.effectiveness_score
        })
    
    # Format by category
    for category, questions in categories.items():
        topics.append({
            "category": category,
            "questions": questions[:3]  # Limit to 3 per category
        })
    
    # Add default topics if none found
    if not topics:
        topics = [
            {
                "category": "Product Information",
                "questions": [
                    {"question": "What are the key features of this device?", "popularity": 0, "effectiveness": 0},
                    {"question": "What training is available?", "popularity": 0, "effectiveness": 0},
                    {"question": "Is this FDA approved?", "popularity": 0, "effectiveness": 0}
                ]
            },
            {
                "category": "Support & Services",
                "questions": [
                    {"question": "How do I request a demo?", "popularity": 0, "effectiveness": 0},
                    {"question": "What support options are available?", "popularity": 0, "effectiveness": 0},
                    {"question": "How do I report an issue?", "popularity": 0, "effectiveness": 0}
                ]
            }
        ]
    
    return topics
