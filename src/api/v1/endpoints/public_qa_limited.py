"""
Public Q&A endpoint with query limits
After 5 questions, prompts user to sign up
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from datetime import datetime, timedelta
import json

from src.db.session import get_db
from src.services.gudid_cloud_service import GUDIDCloudService
from src.core.redis_manager import RedisManager

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize services
cloud_service = GUDIDCloudService()
redis_manager = RedisManager()

@router.post("/ask")
async def ask_device_question(
    question_data: Dict[str, Any],
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Public Q&A endpoint with rate limiting.
    After 5 questions, requires sign-up.
    """
    try:
        question = question_data.get('question', '').strip()
        device_id = question_data.get('device_id')
        session_id = question_data.get('session_id')
        
        if not question:
            raise HTTPException(status_code=400, detail="Question is required")
        
        # Track question count per session/IP
        client_ip = request.client.host if request else "unknown"
        tracking_key = session_id if session_id else f"ip_{client_ip}"
        
        # Get question count from Redis or memory
        count_key = f"qa_count:{tracking_key}"
        
        # Try to get count from Redis
        try:
            current_count = await redis_manager.get(count_key)
            if current_count is None:
                current_count = 0
            else:
                current_count = int(current_count)
        except:
            # Fallback to in-memory if Redis not available
            current_count = 0
        
        # Check if limit reached
        if current_count >= 5:
            return {
                "status": "limit_reached",
                "message": "You've reached your free question limit",
                "action_required": "sign_up",
                "sign_up_message": "Sign up now to get unlimited access and free credits!",
                "sign_up_options": [
                    {
                        "type": "healthcare_professional",
                        "title": "Healthcare Professional",
                        "benefits": [
                            "Unlimited device searches",
                            "AI-powered Q&A with citations",
                            "Access to 4.8M+ FDA devices",
                            "Save and compare devices",
                            "Team collaboration features"
                        ],
                        "cta": "Sign Up as HCP",
                        "url": "/signup/hcp"
                    },
                    {
                        "type": "vendor",
                        "title": "Medical Device Vendor",
                        "benefits": [
                            "List your devices",
                            "Direct channel to healthcare workers",
                            "Usage analytics",
                            "Support ticket management",
                            "Marketing opportunities"
                        ],
                        "cta": "Sign Up as Vendor",
                        "url": "/signup/vendor"
                    }
                ],
                "questions_asked": current_count,
                "limit": 5
            }
        
        # Process the question
        # For now, return a simple response
        # In production, this would use OpenAI or similar
        
        # Get device info if device_id provided
        device_info = None
        if device_id:
            device_info = cloud_service.get_device_details(device_id)
        
        # Increment question count
        new_count = current_count + 1
        try:
            await redis_manager.set(count_key, str(new_count), expire=86400)  # 24 hour expiry
        except:
            pass  # Continue even if Redis fails
        
        # Generate response (simplified for now)
        response = {
            "status": "success",
            "answer": f"Based on FDA data, here's information about your question: {question[:100]}...",
            "device": device_info if device_info else None,
            "citations": [
                {
                    "source": "FDA GUDID Database",
                    "type": "official",
                    "url": "https://accessgudid.nlm.nih.gov/"
                }
            ],
            "questions_remaining": 5 - new_count,
            "questions_asked": new_count,
            "session_id": tracking_key
        }
        
        # Add sign-up prompt if approaching limit
        if new_count >= 3:
            response["reminder"] = {
                "message": f"You have {5 - new_count} free question(s) remaining",
                "suggestion": "Sign up for unlimited access",
                "show_benefits": True
            }
        
        # Log the question for analytics
        logger.info(f"Q&A: session={tracking_key}, question={new_count}/5")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Q&A error: {e}")
        return {
            "status": "error",
            "message": "Unable to process your question",
            "error": str(e)
        }

@router.get("/remaining")
async def get_remaining_questions(
    session_id: Optional[str] = Query(None),
    request: Request = None
):
    """
    Check how many questions remain for a session/IP
    """
    try:
        client_ip = request.client.host if request else "unknown"
        tracking_key = session_id if session_id else f"ip_{client_ip}"
        count_key = f"qa_count:{tracking_key}"
        
        # Get current count
        try:
            current_count = await redis_manager.get(count_key)
            if current_count is None:
                current_count = 0
            else:
                current_count = int(current_count)
        except:
            current_count = 0
        
        remaining = max(0, 5 - current_count)
        
        return {
            "status": "success",
            "questions_asked": current_count,
            "questions_remaining": remaining,
            "limit": 5,
            "session_id": tracking_key,
            "requires_signup": remaining == 0
        }
        
    except Exception as e:
        logger.error(f"Remaining check error: {e}")
        return {
            "status": "error",
            "questions_remaining": 5
        }

@router.post("/reset")
async def reset_question_count(
    reset_data: Dict[str, Any]
):
    """
    Reset question count (admin only in production)
    For testing purposes
    """
    session_id = reset_data.get('session_id')
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID required")
    
    count_key = f"qa_count:{session_id}"
    
    try:
        await redis_manager.delete(count_key)
        return {"status": "success", "message": "Question count reset"}
    except:
        return {"status": "success", "message": "Count reset (Redis not available)"}
