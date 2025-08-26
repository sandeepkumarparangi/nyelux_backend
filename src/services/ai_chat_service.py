"""
AI-Powered Chat Service with RAG - PRODUCTION READY
Implements context-aware Q&A using GPT-4 with real document retrieval.
NO FAKE RESPONSES. All answers come from real AI or documents.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
import asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import openai
import tiktoken
from supabase import create_client, Client
import numpy as np
from scipy.spatial.distance import cosine

from src.core.config import settings
from src.db.models.chat import ChatConversation, ChatMessage, ChatCitation
from src.db.models.document_chunk import DocumentChunk
from src.db.models.device_document import DeviceDocument
from src.schemas.chat import (
    ChatRequest, 
    ChatResponse, 
    ConversationCreate,
    Citation
)

logger = logging.getLogger(__name__)

class AIChat:
    """
    Production AI chat service with RAG.
    Uses real OpenAI API and document retrieval.
    """
    
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for AI chat features")
        
        openai.api_key = settings.OPENAI_API_KEY
        self.model = "gpt-4"
        self.embedding_model = "text-embedding-ada-002"
        self.max_tokens = 2000
        self.temperature = 0.3  # Lower for factual responses
        self.max_context_tokens = 6000
        
        # Token counter
        self.encoding = tiktoken.encoding_for_model(self.model)
        
        # Initialize Supabase for vector search (if configured)
        if settings.SUPABASE_URL:
            self.supabase = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_KEY
            )
        else:
            self.supabase = None
        
        # System prompts for different contexts
        self.system_prompts = {
            'general': """You are a medical device expert assistant for Nyelux.
Your role is to provide accurate, helpful information about medical devices.
Always base your answers on the provided context and cite your sources.
Never provide medical diagnosis or treatment advice.
If you don't have information to answer a question, say so clearly.
Be concise but thorough in your responses.""",
            
            'device_specific': """You are an expert on the specific medical device being discussed.
Provide detailed technical information, usage instructions, and safety information.
Always cite the source documents when available.
Focus on practical, actionable information for healthcare professionals.""",
            
            'troubleshooting': """You are a technical support specialist for medical devices.
Help users diagnose and resolve issues with their devices.
Provide step-by-step troubleshooting instructions.
Always emphasize safety and proper procedures.
If an issue seems serious, recommend contacting the manufacturer.""",
            
            'training': """You are a medical device trainer.
Provide clear, step-by-step instructions for device operation.
Emphasize best practices and safety procedures.
Break down complex procedures into manageable steps.
Confirm understanding with summary points."""
        }
    
    async def create_conversation(
        self,
        db: AsyncSession,
        user_id: int,
        request: ConversationCreate
    ) -> ChatConversation:
        """Create a new chat conversation."""
        conversation = ChatConversation(
            user_id=user_id,
            device_id=request.device_id,
            title=request.title or "New Conversation",
            context_type=request.context_type or 'general',
            status='active'
        )
        
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        
        logger.info(f"Created conversation {conversation.id} for user {user_id}")
        return conversation
    
    async def get_response(
        self,
        db: AsyncSession,
        conversation_id: int,
        request: ChatRequest,
        user_id: int
    ) -> ChatResponse:
        """
        Get AI response with RAG from real documents.
        NO FAKE RESPONSES - uses real OpenAI API.
        """
        start_time = datetime.utcnow()
        
        # Get conversation
        result = await db.execute(
            select(ChatConversation)
            .where(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id
            )
        )
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise ValueError("Conversation not found")
        
        # Get conversation history
        history = await self._get_conversation_history(db, conversation_id)
        
        # Retrieve relevant documents (RAG)
        relevant_chunks, citations = await self._retrieve_relevant_documents(
            db,
            request.message,
            conversation.device_id
        )
        
        # Build context
        context = self._build_context(
            relevant_chunks,
            conversation,
            history
        )
        
        # Create messages for OpenAI
        messages = self._prepare_messages(
            context,
            history,
            request.message,
            conversation.context_type
        )
        
        # Make OpenAI API call
        try:
            response = await self._call_openai(messages)
            
            # Extract answer and calculate metrics
            answer = response['choices'][0]['message']['content']
            tokens_used = response['usage']['total_tokens']
            confidence_score = self._calculate_confidence(answer, relevant_chunks)
            
            # Save message to database
            user_message = ChatMessage(
                conversation_id=conversation_id,
                role='user',
                content=request.message,
                tokens_used=self._count_tokens(request.message)
            )
            
            assistant_message = ChatMessage(
                conversation_id=conversation_id,
                role='assistant',
                content=answer,
                tokens_used=tokens_used,
                model_used=self.model,
                has_citations=len(citations) > 0,
                confidence_score=confidence_score
            )
            
            db.add(user_message)
            db.add(assistant_message)
            
            # Update conversation stats
            conversation.total_messages += 2
            conversation.total_tokens_used += tokens_used
            conversation.last_message_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(assistant_message)
            
            # Save citations
            if citations:
                await self._save_citations(db, assistant_message.id, citations)
            
            # Calculate cost
            cost = self._calculate_cost(tokens_used)
            
            # Log metrics
            response_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Chat response generated: conversation={conversation_id}, "
                f"tokens={tokens_used}, cost=${cost:.4f}, time={response_time:.2f}s"
            )
            
            return ChatResponse(
                message=answer,
                message_id=assistant_message.id,
                citations=[
                    Citation(
                        source_type=c['type'],
                        source_title=c['title'],
                        excerpt=c.get('excerpt'),
                        page_number=c.get('page'),
                        relevance_score=c.get('score', 0.0)
                    )
                    for c in citations
                ],
                confidence_score=confidence_score,
                tokens_used=tokens_used,
                cost=cost,
                response_time_ms=int(response_time * 1000)
            )
            
        except openai.error.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise Exception("AI service temporarily unavailable. Please try again.")
    
    async def _get_conversation_history(
        self,
        db: AsyncSession,
        conversation_id: int,
        limit: int = 10
    ) -> List[Dict]:
        """Get recent conversation history."""
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        
        messages = result.scalars().all()
        
        # Reverse to get chronological order
        return [
            {
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.created_at.isoformat()
            }
            for msg in reversed(messages)
        ]
    
    async def _retrieve_relevant_documents(
        self,
        db: AsyncSession,
        query: str,
        device_id: Optional[int] = None,
        top_k: int = 5
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Retrieve relevant document chunks using vector similarity.
        Returns (chunks, citations).
        """
        # Generate embedding for query
        query_embedding = await self._generate_embedding(query)
        
        if not query_embedding:
            return [], []
        
        relevant_chunks = []
        citations = []
        
        # If we have pgvector extension, use it
        if hasattr(DocumentChunk, 'embedding'):
            # Vector similarity search using pgvector
            result = await db.execute(
                select(DocumentChunk, DeviceDocument)
                .join(DeviceDocument)
                .where(
                    DeviceDocument.device_id == device_id if device_id else True
                )
                .order_by(
                    DocumentChunk.embedding.cosine_distance(query_embedding)
                )
                .limit(top_k)
            )
            
            for chunk, document in result.all():
                relevant_chunks.append({
                    'text': chunk.chunk_text,
                    'page': chunk.page_number,
                    'section': chunk.section_heading,
                    'document_title': document.title,
                    'document_type': document.document_type
                })
                
                citations.append({
                    'type': document.document_type,
                    'title': document.title,
                    'page': chunk.page_number,
                    'section': chunk.section_heading,
                    'excerpt': chunk.chunk_text[:200],
                    'score': 0.9  # Placeholder score
                })
        else:
            # Fallback: keyword search if vector search not available
            keywords = query.lower().split()[:5]
            
            for keyword in keywords:
                result = await db.execute(
                    select(DocumentChunk, DeviceDocument)
                    .join(DeviceDocument)
                    .where(
                        and_(
                            DeviceDocument.device_id == device_id if device_id else True,
                            DocumentChunk.chunk_text.ilike(f'%{keyword}%')
                        )
                    )
                    .limit(top_k // len(keywords) + 1)
                )
                
                for chunk, document in result.all():
                    chunk_data = {
                        'text': chunk.chunk_text,
                        'page': chunk.page_number,
                        'section': chunk.section_heading,
                        'document_title': document.title,
                        'document_type': document.document_type
                    }
                    
                    if chunk_data not in relevant_chunks:
                        relevant_chunks.append(chunk_data)
                        
                        citations.append({
                            'type': document.document_type,
                            'title': document.title,
                            'page': chunk.page_number,
                            'section': chunk.section_heading,
                            'excerpt': chunk.chunk_text[:200],
                            'score': 0.7
                        })
        
        return relevant_chunks[:top_k], citations[:top_k]
    
    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding using OpenAI."""
        try:
            response = await openai.Embedding.acreate(
                input=text,
                model=self.embedding_model
            )
            return response['data'][0]['embedding']
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            return None
    
    def _build_context(
        self,
        relevant_chunks: List[Dict],
        conversation: ChatConversation,
        history: List[Dict]
    ) -> str:
        """Build context from retrieved documents and history."""
        context_parts = []
        
        # Add device information if available
        if conversation.device_id:
            context_parts.append(f"Current device: Device ID {conversation.device_id}")
        
        # Add relevant document chunks
        if relevant_chunks:
            context_parts.append("Relevant Information from Documents:")
            for i, chunk in enumerate(relevant_chunks, 1):
                context_parts.append(
                    f"\n[Source {i}] {chunk['document_title']} "
                    f"(Page {chunk.get('page', 'N/A')}):\n"
                    f"{chunk['text'][:500]}..."
                )
        
        return "\n\n".join(context_parts)
    
    def _prepare_messages(
        self,
        context: str,
        history: List[Dict],
        current_message: str,
        context_type: str
    ) -> List[Dict]:
        """Prepare messages for OpenAI API."""
        messages = []
        
        # System prompt
        system_prompt = self.system_prompts.get(
            context_type, 
            self.system_prompts['general']
        )
        
        if context:
            system_prompt += f"\n\nContext:\n{context}"
        
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # Add conversation history (limit tokens)
        total_tokens = self._count_tokens(system_prompt)
        
        for msg in history[-10:]:  # Last 10 messages
            msg_tokens = self._count_tokens(msg['content'])
            if total_tokens + msg_tokens < self.max_context_tokens - 1000:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
                total_tokens += msg_tokens
        
        # Add current message
        messages.append({
            "role": "user",
            "content": current_message
        })
        
        return messages
    
    async def _call_openai(self, messages: List[Dict]) -> Dict:
        """Make actual OpenAI API call."""
        response = await openai.ChatCompletion.acreate(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            presence_penalty=0.0,
            frequency_penalty=0.0
        )
        return response
    
    def _calculate_confidence(
        self, 
        answer: str, 
        relevant_chunks: List[Dict]
    ) -> float:
        """Calculate confidence score for the answer."""
        if not relevant_chunks:
            return 0.5  # Medium confidence without sources
        
        # Simple heuristic: more sources = higher confidence
        base_confidence = min(0.7 + (len(relevant_chunks) * 0.05), 0.95)
        
        # Adjust based on answer characteristics
        if "I don't have" in answer or "I cannot" in answer:
            base_confidence *= 0.7
        
        if "According to" in answer or "The document states" in answer:
            base_confidence *= 1.1
        
        return min(base_confidence, 1.0)
    
    async def _save_citations(
        self,
        db: AsyncSession,
        message_id: int,
        citations: List[Dict]
    ) -> None:
        """Save citations to database."""
        for citation in citations:
            chat_citation = ChatCitation(
                message_id=message_id,
                source_type=citation['type'],
                source_id=str(citation.get('document_id', '')),
                source_title=citation['title'],
                page_number=citation.get('page'),
                section_reference=citation.get('section'),
                excerpt=citation.get('excerpt', '')[:500],
                relevance_score=citation.get('score', 0.0)
            )
            db.add(chat_citation)
        
        await db.commit()
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        try:
            return len(self.encoding.encode(text))
        except Exception:
            # Fallback estimation
            return len(text) // 4
    
    def _calculate_cost(self, tokens: int) -> float:
        """Calculate cost based on OpenAI pricing."""
        # GPT-4 pricing (as of 2024)
        # $0.03 per 1K input tokens, $0.06 per 1K output tokens
        # Using average for estimation
        cost_per_1k = 0.045
        return (tokens / 1000) * cost_per_1k
    
    async def export_conversation(
        self,
        db: AsyncSession,
        conversation_id: int,
        user_id: int
    ) -> Dict:
        """Export conversation with citations."""
        # Get conversation
        result = await db.execute(
            select(ChatConversation)
            .where(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id
            )
        )
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise ValueError("Conversation not found")
        
        # Get all messages with citations
        messages_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
        )
        messages = messages_result.scalars().all()
        
        # Build export data
        export_data = {
            'conversation': {
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at.isoformat(),
                'total_messages': conversation.total_messages,
                'total_tokens': conversation.total_tokens_used
            },
            'messages': []
        }
        
        for message in messages:
            msg_data = {
                'role': message.role,
                'content': message.content,
                'timestamp': message.created_at.isoformat(),
                'tokens': message.tokens_used
            }
            
            # Get citations if assistant message
            if message.role == 'assistant' and message.has_citations:
                citations_result = await db.execute(
                    select(ChatCitation)
                    .where(ChatCitation.message_id == message.id)
                )
                citations = citations_result.scalars().all()
                
                msg_data['citations'] = [
                    {
                        'source': citation.source_title,
                        'page': citation.page_number,
                        'excerpt': citation.excerpt
                    }
                    for citation in citations
                ]
            
            export_data['messages'].append(msg_data)
        
        return export_data


# Export singleton instance
ai_chat_service = AIChat()
