"""
Public Q&A Chat API endpoints with REAL FDA device data
REAL ANSWERS - NO GENERIC RESPONSES
Production-grade implementation with PostgreSQL
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime
from openai import OpenAI
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.db.session import get_db
from src.db.models.gudid_device import GUDIDDevice
from src.core.cache import CacheService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
cache_service = CacheService() if settings.REDIS_URL else None

# Configure OpenAI with new SDK
client = None
if settings.PUBLIC_OPENAI_API_KEY:
    client = OpenAI(api_key=settings.PUBLIC_OPENAI_API_KEY)
    logger.info("Public OpenAI API key configured for Q&A chat")
elif settings.OPENAI_API_KEY:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    logger.info("Default OpenAI API key configured for Q&A chat")
else:
    logger.warning("No OpenAI API key configured - fallback mode only")

# Session storage using Redis if available, else in-memory
sessions_store: Dict[str, Dict[str, Any]] = {}

class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500, description="The question about medical devices")
    device_id: Optional[str] = Field(None, description="FDA Device Identifier (DI)")
    session_id: str = Field(..., description="Session identifier for tracking")

class QuestionResponse(BaseModel):
    status: str
    answer: Optional[str] = None
    device: Optional[Dict[str, Any]] = None
    citations: Optional[List[Dict[str, str]]] = None
    questions_remaining: Optional[int] = None
    questions_asked: Optional[int] = None
    session_id: str
    message: Optional[str] = None
    action_required: Optional[str] = None
    limit: Optional[int] = None
    ai_powered: Optional[bool] = False
    device_data_used: Optional[bool] = False

class SessionStatus(BaseModel):
    status: str
    questions_asked: int
    questions_remaining: int
    limit: int
    session_id: str
    requires_signup: bool

async def get_or_create_session(session_id: str) -> Dict[str, Any]:
    """Get existing session or create new one - uses Redis if available"""
    if cache_service:
        # Try to get from Redis
        session = await cache_service.get(f"qa_session:{session_id}")
        if not session:
            session = {
                "questions_asked": 0,
                "created_at": datetime.utcnow().isoformat(),
                "questions": [],
                "devices_queried": []
            }
            await cache_service.set(f"qa_session:{session_id}", session, expire=3600)
        return session
    else:
        # Fallback to in-memory
        if session_id not in sessions_store:
            sessions_store[session_id] = {
                "questions_asked": 0,
                "created_at": datetime.utcnow(),
                "questions": [],
                "devices_queried": []
            }
        return sessions_store[session_id]

async def save_session(session_id: str, session: Dict[str, Any]):
    """Save session to Redis if available"""
    if cache_service:
        await cache_service.set(f"qa_session:{session_id}", session, expire=3600)
    else:
        sessions_store[session_id] = session

async def get_device_from_database(
    device_id: str, 
    db: AsyncSession
) -> Optional[Dict[str, Any]]:
    """Fetch REAL device data from PostgreSQL database"""
    try:
        # Query the actual GUDID device table
        result = await db.execute(
            select(GUDIDDevice).where(GUDIDDevice.primary_di == device_id)
        )
        device = result.scalar_one_or_none()
        
        if device:
            # Convert to dict for response
            device_data = {
                "primary_di": device.primary_di,
                "device_name": device.device_name,
                "manufacturer_name": device.manufacturer_name,
                "manufacturer_di": device.manufacturer_di,
                "brand_name": device.brand_name,
                "model_number": device.model_number,
                "catalog_number": device.catalog_number,
                "device_class": device.device_class,
                "device_class_name": device.device_class_name,
                "gmdn_terms": device.gmdn_terms,
                "gmdn_codes": device.gmdn_codes,
                "product_code": device.product_code,
                "regulation_number": device.regulation_number,
                "mri_safety": device.mri_safety,
                "device_description": device.device_description,
                "device_size_text": device.device_size_text,
                "sterile": device.sterile,
                "single_use": device.single_use,
                "implantable": device.implantable,
                "life_supporting": device.life_supporting,
                "rx_required": device.rx_required,
                "otc": device.otc,
                "device_comm_distribution_status": getattr(device, 'device_comm_distribution_status', 'In Commercial Distribution')
            }
            
            logger.info(f"Found device: {device_data['device_name']}")
            return device_data
        
        logger.info(f"Device not found: {device_id}")
        return None
        
    except Exception as e:
        logger.error(f"Database error fetching device: {str(e)}")
        return None

async def search_relevant_devices(
    question: str, 
    db: AsyncSession,
    limit: int = 3
) -> List[Dict[str, Any]]:
    """Search for devices relevant to the question using PostgreSQL full-text search"""
    try:
        # Extract key terms from question for search
        search_terms = question.lower().replace('?', '').replace('.', '').strip()
        
        # Use PostgreSQL full-text search
        query = text("""
            SELECT 
                primary_di,
                device_name,
                manufacturer_name,
                device_description,
                gmdn_terms,
                device_class,
                mri_safety,
                ts_rank(search_vector, plainto_tsquery('english', :search_terms)) as rank
            FROM gudid_devices
            WHERE search_vector @@ plainto_tsquery('english', :search_terms)
            ORDER BY rank DESC
            LIMIT :limit
        """)
        
        result = await db.execute(
            query,
            {"search_terms": search_terms, "limit": limit}
        )
        
        devices = []
        for row in result:
            devices.append({
                "primary_di": row.primary_di,
                "device_name": row.device_name,
                "manufacturer_name": row.manufacturer_name,
                "device_description": row.device_description,
                "gmdn_terms": row.gmdn_terms,
                "device_class": row.device_class,
                "mri_safety": row.mri_safety,
                "relevance_score": float(row.rank)
            })
        
        logger.info(f"Found {len(devices)} relevant devices for query")
        return devices
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return []

async def get_openai_response_with_real_data(
    question: str, 
    device_data: Optional[Dict[str, Any]] = None,
    related_devices: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Get response from OpenAI using REAL device data"""
    if not client:
        return None
        
    try:
        # Build context from REAL device data
        context_parts = []
        
        if device_data:
            device_name = device_data.get('device_name', 'Unknown device')
            manufacturer = device_data.get('manufacturer_name', 'Unknown manufacturer')
            
            context_parts.append(f"DEVICE: {device_name}")
            context_parts.append(f"MANUFACTURER: {manufacturer}")
            context_parts.append("")
            
            if device_data.get('device_description'):
                context_parts.append(f"DESCRIPTION: {device_data.get('device_description')}")
            
            context_parts.append("\nKEY FACTS:")
            device_class_name = f"({device_data.get('device_class_name')})" if device_data.get('device_class_name') else ''
            context_parts.append(f"- FDA Class: {device_data.get('device_class') or 'Not classified'} {device_class_name}")
            context_parts.append(f"- MRI Safety: {device_data.get('mri_safety', 'Not specified')}")
            context_parts.append(f"- Requires Prescription: {'Yes' if device_data.get('rx_required') else 'No'}")
            context_parts.append(f"- Sterile: {'Yes' if device_data.get('sterile') else 'No'}")
            context_parts.append(f"- Single Use: {'Yes' if device_data.get('single_use') else 'No'}")
            
            if device_data.get('model_number'):
                context_parts.append(f"- Model: {device_data.get('model_number')}")
        
        elif related_devices:
            context_parts.append("RELATED DEVICES FOUND:")
            for device in related_devices[:3]:
                context_parts.append(f"\n• {device['device_name']} by {device['manufacturer_name']}")
                if device.get('device_description'):
                    context_parts.append(f"  {device['device_description'][:100]}...")
        
        context = "\n".join(context_parts)
        
        system_prompt = """You are a friendly medical device expert helping healthcare professionals.

RULES:
1. Give SHORT, CONVERSATIONAL answers (2-3 sentences)
2. NEVER share DI numbers, serial numbers, or contact info - say "Sign up for complete details"
3. Be helpful and natural
4. Ask a follow-up question to continue conversation

Answer the question briefly, then ask what else they'd like to know."""
        
        user_prompt = f"""Device Information:
{context}

Question: {question}

Give a brief, helpful answer. If they want contact info or IDs, tell them to sign up. End with a follow-up question."""
        
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        
        answer = response.choices[0].message.content.strip()
        
        return {
            "answer": answer,
            "citations": [{
                "source": "FDA GUDID Database",
                "type": "official",
                "device_di": device_data.get('primary_di') if device_data else None,
                "device_name": device_data.get('device_name') if device_data else None
            }],
            "ai_powered": True,
            "device_data_used": bool(device_data or related_devices),
            "tokens_used": response.usage.total_tokens
        }
        
    except Exception as e:
        logger.error(f"OpenAI error: {str(e)}")
        return None

@router.post("/ask", response_model=QuestionResponse)
async def ask_question(
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Ask questions about medical devices using REAL FDA data
    Production-grade implementation with proper database access
    """
    try:
        # Get or create session
        session = await get_or_create_session(request.session_id)
        questions_asked = session["questions_asked"]
        
        # Check limit
        if questions_asked >= 5:
            return QuestionResponse(
                status="limit_reached",
                message="You've reached your free question limit",
                action_required="sign_up",
                questions_asked=5,
                limit=5,
                session_id=request.session_id
            )
        
        # Store question
        session["questions"].append({
            "question": request.question,
            "device_id": request.device_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Get REAL device data
        device_data = None
        if request.device_id:
            device_data = await get_device_from_database(request.device_id, db)
            if device_data:
                session["devices_queried"].append(request.device_id)
        
        # Search for relevant devices
        related_devices = []
        if not device_data:
            related_devices = await search_relevant_devices(request.question, db)
        
        # Get AI response
        response_data = None
        if settings.ENABLE_PUBLIC_AI and client:
            response_data = await get_openai_response_with_real_data(
                request.question, 
                device_data,
                related_devices
            )
        
        # Fallback if AI not available
        if not response_data:
            if device_data:
                device_name = device_data.get('device_name', 'this device')
                answer = f"I have information about {device_name}. It's classified as FDA Class {device_data.get('device_class', 'N/A')} with MRI safety: {device_data.get('mri_safety', 'Not specified')}. What specific details would you like to know?"
            else:
                answer = "I can help you with medical device information. Could you provide a device name or ID?"
            
            response_data = {
                "answer": answer,
                "citations": [{"source": "FDA GUDID Database", "type": "official"}],
                "ai_powered": False,
                "device_data_used": bool(device_data)
            }
        
        # Update session
        session["questions_asked"] += 1
        await save_session(request.session_id, session)
        
        return QuestionResponse(
            status="success",
            answer=response_data["answer"],
            device=device_data,
            citations=response_data["citations"],
            questions_remaining=5 - session["questions_asked"],
            questions_asked=session["questions_asked"],
            session_id=request.session_id,
            ai_powered=response_data.get("ai_powered", False),
            device_data_used=response_data.get("device_data_used", False)
        )
        
    except Exception as e:
        logger.error(f"Q&A error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process question")

@router.get("/remaining", response_model=SessionStatus)
async def check_remaining_questions(session_id: str):
    """Check remaining questions for session"""
    session = await get_or_create_session(session_id)
    questions_asked = session["questions_asked"]
    
    return SessionStatus(
        status="success",
        questions_asked=questions_asked,
        questions_remaining=max(0, 5 - questions_asked),
        limit=5,
        session_id=session_id,
        requires_signup=questions_asked >= 5
    )

@router.get("/status")
async def get_qa_status(db: AsyncSession = Depends(get_db)):
    """Get Q&A system status"""
    
    # Check database connection
    db_connected = False
    device_count = 0
    try:
        result = await db.execute(select(func.count(GUDIDDevice.primary_di)))
        device_count = result.scalar()
        db_connected = True
    except:
        pass
    
    # Check Redis
    redis_connected = False
    if cache_service:
        redis_connected = await cache_service.health_check()
    
    return {
        "status": "operational",
        "mode": "ai_powered" if client else "fallback_mode",
        "ai_enabled": bool(client),
        "database_connected": db_connected,
        "redis_connected": redis_connected,
        "device_count": device_count,
        "model": settings.OPENAI_MODEL if client else None,
        "session_limit": 5,
        "features": {
            "real_device_data": db_connected,
            "ai_chat": bool(client),
            "caching": redis_connected,
            "full_text_search": db_connected
        }
    }
