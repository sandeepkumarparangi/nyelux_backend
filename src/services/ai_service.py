"""
Production-ready AI Service with OpenAI v1.0+ API
Handles medical device Q&A with proper error handling and monitoring
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from enum import Enum

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class AIModel(Enum):
    """Available AI models"""
    GPT_35_TURBO = "gpt-3.5-turbo"
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo-preview"


class AIService:
    """
    Production AI service using OpenAI v1.0+ API.
    Provides medical device Q&A with FDA context.
    """
    
    def __init__(self):
        """Initialize OpenAI client with production configuration."""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")
        
        if not settings.OPENAI_API_KEY.startswith('sk-'):
            raise ValueError("Invalid OpenAI API key format")
        
        # Initialize OpenAI client (v1.0+ syntax)
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=30.0,
            max_retries=3
        )
        
        self.model = settings.OPENAI_MODEL or AIModel.GPT_35_TURBO.value
        self.max_tokens = settings.OPENAI_MAX_TOKENS or 500
        self.temperature = settings.OPENAI_TEMPERATURE or 0.3
        
        logger.info(f"AI Service initialized with model: {self.model}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_device_answer(
        self,
        question: str,
        device_context: Optional[Dict[str, Any]] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get AI response about medical device with FDA context.
        
        Args:
            question: User's question
            device_context: Device information from FDA GUDID
            citations: Document citations for RAG
            user_context: User role and organization for personalized response
            
        Returns:
            AI response with confidence score and token usage
        """
        try:
            # Build system context
            system_prompt = self._build_system_prompt(user_context)
            
            # Build user context with device information
            user_prompt = self._build_user_prompt(question, device_context, citations)
            
            # Track timing
            start_time = datetime.utcnow()
            
            # Make API call with new v1.0+ syntax
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=0.9,
                frequency_penalty=0.0,
                presence_penalty=0.0
            )
            
            # Extract response
            answer = response.choices[0].message.content
            
            # Calculate metrics
            tokens_used = response.usage.total_tokens if response.usage else 0
            response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Estimate cost (GPT-3.5: $0.001/1K tokens, GPT-4: $0.03/1K tokens)
            cost_per_1k = 0.001 if "gpt-3.5" in self.model else 0.03
            estimated_cost = (tokens_used / 1000) * cost_per_1k
            
            # Log metrics
            logger.info(
                f"AI response generated: {tokens_used} tokens, "
                f"${estimated_cost:.4f}, {response_time_ms}ms"
            )
            
            return {
                "answer": answer,
                "confidence": self._calculate_confidence(answer, citations),
                "tokens_used": tokens_used,
                "cost": estimated_cost,
                "model": self.model,
                "response_time_ms": response_time_ms,
                "citations_used": len(citations) if citations else 0,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"AI service error: {str(e)}", exc_info=True)
            
            # Specific error handling
            if "rate_limit" in str(e).lower():
                raise ExternalServiceError(
                    "OpenAI",
                    "Rate limit exceeded. Please try again in a moment."
                )
            elif "api_key" in str(e).lower():
                raise ExternalServiceError(
                    "OpenAI",
                    "Invalid API key configuration."
                )
            elif "timeout" in str(e).lower():
                raise ExternalServiceError(
                    "OpenAI",
                    "Request timed out. Please try again."
                )
            else:
                raise ExternalServiceError(
                    "OpenAI",
                    f"AI service temporarily unavailable: {str(e)}"
                )
    
    def _build_system_prompt(self, user_context: Optional[Dict[str, Any]] = None) -> str:
        """Build system prompt based on user context."""
        base_prompt = """You are a medical device expert assistant for the Nyelux platform.
        You have access to FDA GUDID data for over 4.8 million medical devices.
        
        Guidelines:
        - Provide accurate, factual information based on FDA data
        - Always cite your sources when available
        - Never provide medical diagnosis or treatment advice
        - Be clear about device classifications and safety information
        - If you're not certain, say so clearly
        - Keep responses concise and professional
        """
        
        if user_context:
            role = user_context.get('role', 'healthcare_professional')
            if role == 'vendor_rep':
                base_prompt += "\nThe user is a vendor representative. Focus on technical specifications and sales information."
            elif role == 'physician':
                base_prompt += "\nThe user is a physician. Provide clinical context and usage information."
            elif role == 'nurse':
                base_prompt += "\nThe user is a nurse. Focus on practical usage and safety procedures."
        
        return base_prompt
    
    def _build_user_prompt(
        self,
        question: str,
        device_context: Optional[Dict[str, Any]] = None,
        citations: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Build user prompt with device context."""
        prompt = ""
        
        if device_context:
            prompt += "Device Information from FDA GUDID:\n"
            prompt += f"- Name: {device_context.get('device_name', 'Unknown')}\n"
            prompt += f"- Manufacturer: {device_context.get('manufacturer_name', 'Unknown')}\n"
            prompt += f"- FDA Class: {device_context.get('device_class', 'Unknown')}\n"
            prompt += f"- GMDN: {device_context.get('gmdn_terms', 'Unknown')}\n"
            
            if device_context.get('mri_safety'):
                prompt += f"- MRI Safety: {device_context['mri_safety']}\n"
            if device_context.get('sterile'):
                prompt += f"- Sterile: {'Yes' if device_context['sterile'] else 'No'}\n"
            if device_context.get('single_use'):
                prompt += f"- Single Use: {'Yes' if device_context['single_use'] else 'No'}\n"
            if device_context.get('implantable'):
                prompt += f"- Implantable: {'Yes' if device_context['implantable'] else 'No'}\n"
            
            prompt += "\n"
        
        if citations:
            prompt += "Additional Documentation:\n"
            for citation in citations[:3]:  # Limit to top 3 citations
                prompt += f"- {citation.get('title', 'Document')}: {citation.get('excerpt', '')}\n"
            prompt += "\n"
        
        prompt += f"Question: {question}"
        
        return prompt
    
    def _calculate_confidence(
        self,
        answer: str,
        citations: Optional[List[Dict[str, Any]]] = None
    ) -> float:
        """Calculate confidence score based on answer and citations."""
        confidence = 0.7  # Base confidence
        
        # Increase confidence if we have citations
        if citations:
            confidence += min(0.2, len(citations) * 0.05)
        
        # Decrease confidence for uncertain language
        uncertain_phrases = [
            "might", "possibly", "perhaps", "may", "could be",
            "not certain", "unclear", "depends"
        ]
        for phrase in uncertain_phrases:
            if phrase.lower() in answer.lower():
                confidence -= 0.1
                break
        
        # Ensure confidence is between 0 and 1
        return max(0.1, min(1.0, confidence))
    
    async def generate_embeddings(
        self,
        text: str,
        model: str = "text-embedding-ada-002"
    ) -> List[float]:
        """
        Generate embeddings for text using OpenAI.
        
        Args:
            text: Text to embed
            model: Embedding model to use
            
        Returns:
            List of embedding values
        """
        try:
            response = self.client.embeddings.create(
                input=text,
                model=model
            )
            return response.data[0].embedding
            
        except Exception as e:
            logger.error(f"Embedding generation error: {str(e)}")
            raise ExternalServiceError(
                "OpenAI",
                f"Failed to generate embeddings: {str(e)}"
            )
    
    async def moderate_content(self, text: str) -> Dict[str, Any]:
        """
        Check content for policy violations using OpenAI moderation.
        
        Args:
            text: Content to moderate
            
        Returns:
            Moderation results
        """
        try:
            response = self.client.moderations.create(input=text)
            return {
                "flagged": response.results[0].flagged,
                "categories": response.results[0].categories.model_dump(),
                "scores": response.results[0].category_scores.model_dump()
            }
            
        except Exception as e:
            logger.error(f"Content moderation error: {str(e)}")
            # Don't fail if moderation fails - just log
            return {"flagged": False, "categories": {}, "scores": {}}


# Singleton instance
_ai_service_instance = None


def get_ai_service() -> AIService:
    """
    Get AI service singleton instance.
    
    Returns:
        AIService instance
        
    Raises:
        ExternalServiceError: If AI service cannot be initialized
    """
    global _ai_service_instance
    
    if _ai_service_instance is None:
        _ai_service_instance = AIService()
    
    return _ai_service_instance
