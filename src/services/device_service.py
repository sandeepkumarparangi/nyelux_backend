"""
Production Device Service
Integrates FDA GUDID data with vendor content
Real implementation - no fakes
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, text
from sqlalchemy.orm import selectinload
import logging
from datetime import datetime
from openai import OpenAI

from src.db.models.device_models import (
    GUDIDDevice, 
    VendorDevice, 
    DeviceDocument, 
    DocumentChunk,
    DeviceVideo
)
from src.core.config import settings
from src.core.cache import CacheService

logger = logging.getLogger(__name__)

class DeviceService:
    """
    Production device service that combines:
    1. PUBLIC FDA GUDID data (available to everyone)
    2. VENDOR content (manuals, videos - controlled access)
    3. AI-powered Q&A using both data sources
    """
    
    def __init__(self):
        self.cache = CacheService() if settings.REDIS_URL else None
        self.openai_client = None
        if settings.OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def search_devices(
        self,
        db: AsyncSession,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        limit: int = 10,
        offset: int = 0,
        include_vendor_content: bool = False
    ) -> Dict[str, Any]:
        """
        Search devices combining FDA and vendor data
        
        Access Rules:
        - FDA GUDID data: Always public
        - Vendor pricing/contact: Based on vendor settings
        - Documents/videos: Based on access level
        """
        
        # Check cache first
        cache_key = f"device_search:{query}:{limit}:{offset}"
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for search: {query}")
                return cached
        
        # Build base query for FDA devices
        base_query = select(GUDIDDevice)
        
        # Apply full-text search
        if query:
            # Use PostgreSQL full-text search
            search_condition = text("""
                search_vector @@ plainto_tsquery('english', :query)
                OR device_name ILIKE :pattern
                OR manufacturer_name ILIKE :pattern
                OR model_number ILIKE :pattern
            """)
            base_query = base_query.where(search_condition).params(
                query=query,
                pattern=f"%{query}%"
            )
        
        # Apply filters
        if filters:
            if filters.get('device_class'):
                base_query = base_query.where(GUDIDDevice.device_class.in_(filters['device_class']))
            if filters.get('mri_safety'):
                base_query = base_query.where(GUDIDDevice.mri_safety == filters['mri_safety'])
            if filters.get('sterile') is not None:
                base_query = base_query.where(GUDIDDevice.sterile == filters['sterile'])
            if filters.get('manufacturer'):
                base_query = base_query.where(GUDIDDevice.manufacturer_name.in_(filters['manufacturer']))
        
        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total_count = total_result.scalar()
        
        # Apply pagination and get results
        base_query = base_query.limit(limit).offset(offset)
        
        # Include vendor data if requested and user has access
        if include_vendor_content:
            base_query = base_query.options(
                selectinload(GUDIDDevice.vendor_devices).selectinload(VendorDevice.documents),
                selectinload(GUDIDDevice.vendor_devices).selectinload(VendorDevice.videos)
            )
        
        result = await db.execute(base_query)
        devices = result.scalars().all()
        
        # Format results
        formatted_results = []
        for device in devices:
            device_data = self._format_device_data(
                device, 
                user_id=user_id,
                organization_id=organization_id,
                include_vendor_content=include_vendor_content
            )
            formatted_results.append(device_data)
        
        response = {
            "results": formatted_results,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "query": query
        }
        
        # Cache the results
        if self.cache:
            await self.cache.set(cache_key, response, expire=300)  # 5 minutes
        
        return response
    
    def _format_device_data(
        self,
        device: GUDIDDevice,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        include_vendor_content: bool = False
    ) -> Dict[str, Any]:
        """
        Format device data with appropriate access control
        
        PUBLIC (always shown):
        - FDA device information
        - Basic vendor presence indicator
        
        CONDITIONAL (based on vendor settings):
        - Pricing
        - Contact information
        - Documents
        - Videos
        """
        
        # Always include FDA public data
        data = {
            "primary_di": device.primary_di,
            "device_name": device.device_name,
            "manufacturer_name": device.manufacturer_name,
            "brand_name": device.brand_name,
            "model_number": device.model_number,
            "device_class": device.device_class,
            "device_class_name": device.device_class_name,
            "mri_safety": device.mri_safety,
            "device_description": device.device_description,
            "sterile": device.sterile,
            "single_use": device.single_use,
            "implantable": device.implantable,
            "life_supporting": device.life_supporting,
            "rx_required": device.rx_required,
            "has_vendor_content": False,
            "vendor_content": []
        }
        
        # Add vendor content if available and accessible
        if include_vendor_content and device.vendor_devices:
            vendor_content = []
            
            for vendor_device in device.vendor_devices:
                # Check access level
                can_access = self._check_vendor_access(
                    vendor_device,
                    user_id=user_id,
                    organization_id=organization_id
                )
                
                if can_access:
                    vendor_info = {
                        "vendor_id": vendor_device.id,
                        "organization_name": vendor_device.organization.name if vendor_device.organization else None,
                        "custom_name": vendor_device.custom_name,
                    }
                    
                    # Add price if visible
                    if vendor_device.visibility_settings.get('show_price', False):
                        vendor_info["list_price"] = float(vendor_device.list_price) if vendor_device.list_price else None
                        vendor_info["currency"] = vendor_device.currency_code
                    
                    # Add contact if visible
                    if vendor_device.visibility_settings.get('show_contact', False):
                        vendor_info["support_contact"] = vendor_device.support_contact
                        vendor_info["support_email"] = vendor_device.support_email
                        vendor_info["support_phone"] = vendor_device.support_phone
                    
                    # Add document count
                    if vendor_device.visibility_settings.get('show_documents', True):
                        vendor_info["document_count"] = len([
                            doc for doc in vendor_device.documents 
                            if self._check_document_access(doc, user_id, organization_id)
                        ])
                    
                    # Add video count
                    if vendor_device.visibility_settings.get('show_videos', True):
                        vendor_info["video_count"] = len([
                            vid for vid in vendor_device.videos
                            if self._check_video_access(vid, user_id, organization_id)
                        ])
                    
                    vendor_content.append(vendor_info)
            
            if vendor_content:
                data["has_vendor_content"] = True
                data["vendor_content"] = vendor_content
        
        return data
    
    def _check_vendor_access(
        self,
        vendor_device: VendorDevice,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None
    ) -> bool:
        """Check if user can access vendor device content"""
        
        # Public access
        if vendor_device.access_level == 'public':
            return True
        
        # Registered users only
        if vendor_device.access_level == 'registered' and user_id:
            return True
        
        # Organization members only
        if vendor_device.access_level == 'organization':
            if organization_id and vendor_device.organization_id == organization_id:
                return True
        
        # Private - only vendor org members
        if vendor_device.access_level == 'private':
            if organization_id and vendor_device.organization_id == organization_id:
                return True
        
        return False
    
    def _check_document_access(
        self,
        document: DeviceDocument,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None
    ) -> bool:
        """Check if user can access document"""
        
        # Document can override vendor settings
        if document.access_level != 'inherit':
            if document.access_level == 'public':
                return True
            if document.access_level == 'registered' and user_id:
                return True
            if document.access_level == 'organization' and organization_id == document.organization_id:
                return True
            if document.access_level == 'private' and organization_id == document.organization_id:
                return True
            return False
        
        # Otherwise inherit from vendor device
        return self._check_vendor_access(
            document.vendor_device,
            user_id=user_id,
            organization_id=organization_id
        )
    
    def _check_video_access(
        self,
        video: DeviceVideo,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None
    ) -> bool:
        """Check if user can access video"""
        
        if video.access_level == 'public':
            return True
        if video.access_level == 'registered' and user_id:
            return True
        if video.access_level == 'organization' and organization_id == video.organization_id:
            return True
        if video.access_level == 'private' and organization_id == video.organization_id:
            return True
        
        return False
    
    async def get_device_for_chat(
        self,
        db: AsyncSession,
        device_di: str,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get device data optimized for AI chat
        Includes FDA data + accessible vendor content
        """
        
        # Get device with all relationships
        query = select(GUDIDDevice).where(GUDIDDevice.primary_di == device_di).options(
            selectinload(GUDIDDevice.vendor_devices).selectinload(VendorDevice.documents).selectinload(DeviceDocument.document_chunks),
            selectinload(GUDIDDevice.vendor_devices).selectinload(VendorDevice.videos)
        )
        
        result = await db.execute(query)
        device = result.scalar_one_or_none()
        
        if not device:
            return None
        
        # Build comprehensive data for AI
        device_data = self._format_device_data(
            device,
            user_id=user_id,
            organization_id=organization_id,
            include_vendor_content=True
        )
        
        # Add document content for RAG if user has access
        accessible_chunks = []
        for vendor_device in device.vendor_devices:
            if self._check_vendor_access(vendor_device, user_id, organization_id):
                for document in vendor_device.documents:
                    if self._check_document_access(document, user_id, organization_id):
                        for chunk in document.document_chunks:
                            accessible_chunks.append({
                                "document_title": document.title,
                                "document_type": document.document_type,
                                "chunk_text": chunk.chunk_text,
                                "page_number": chunk.page_number,
                                "section": chunk.section_heading
                            })
        
        device_data["rag_chunks"] = accessible_chunks[:10]  # Limit to top 10 most relevant
        
        return device_data
    
    async def answer_device_question(
        self,
        db: AsyncSession,
        question: str,
        device_di: Optional[str] = None,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Answer questions using FDA data + vendor content
        Uses OpenAI with RAG from accessible documents
        """
        
        if not self.openai_client:
            return {
                "answer": "AI service not available. Please try again later.",
                "sources": [],
                "ai_used": False
            }
        
        # Get device data if specified
        device_context = None
        if device_di:
            device_context = await self.get_device_for_chat(
                db, device_di, user_id, organization_id
            )
        
        # Build context for AI
        context_parts = []
        sources = []
        
        if device_context:
            # Add FDA information
            context_parts.append(f"DEVICE: {device_context['device_name']}")
            context_parts.append(f"MANUFACTURER: {device_context['manufacturer_name']}")
            context_parts.append(f"FDA CLASS: {device_context['device_class']}")
            context_parts.append(f"DESCRIPTION: {device_context.get('device_description', 'N/A')}")
            sources.append({
                "type": "FDA GUDID",
                "name": device_context['device_name']
            })
            
            # Add vendor document chunks if available
            if device_context.get('rag_chunks'):
                context_parts.append("\nFROM VENDOR DOCUMENTATION:")
                for chunk in device_context['rag_chunks'][:5]:  # Use top 5 chunks
                    context_parts.append(f"- {chunk['chunk_text'][:200]}...")
                    if chunk['document_title'] not in [s['name'] for s in sources]:
                        sources.append({
                            "type": "Vendor Document",
                            "name": chunk['document_title']
                        })
        
        # Create prompt
        context = "\n".join(context_parts)
        
        system_prompt = """You are a medical device expert assistant. 
        Provide accurate, helpful information based on the provided context.
        Always distinguish between FDA official data and vendor-provided information.
        If you don't have specific information, say so clearly.
        Never provide medical advice or diagnosis."""
        
        user_prompt = f"""Context:
{context}

Question: {question}

Provide a clear, accurate answer based on the available information."""
        
        try:
            # Get AI response
            response = self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.3  # Lower temperature for factual responses
            )
            
            answer = response.choices[0].message.content
            
            return {
                "answer": answer,
                "sources": sources,
                "ai_used": True,
                "tokens_used": response.usage.total_tokens,
                "device_di": device_di
            }
            
        except Exception as e:
            logger.error(f"OpenAI error: {str(e)}")
            return {
                "answer": "I encountered an error processing your question. Please try again.",
                "sources": sources,
                "ai_used": False,
                "error": str(e)
            }


class PublicDeviceService:
    """
    Service for public/unauthenticated access
    Only shows FDA public data + public vendor content
    """
    
    def __init__(self):
        self.device_service = DeviceService()
    
    async def public_search(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Public search - FDA data + public vendor indicators only
        Limited to 10 results for lead generation
        """
        
        return await self.device_service.search_devices(
            db=db,
            query=query,
            user_id=None,
            organization_id=None,
            limit=min(limit, 10),  # Max 10 for public
            include_vendor_content=True  # Will only show public content
        )
    
    async def public_device_detail(
        self,
        db: AsyncSession,
        device_di: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get public device details for SEO/sharing
        Shows FDA data + public vendor content indicators
        """
        
        device_data = await self.device_service.get_device_for_chat(
            db=db,
            device_di=device_di,
            user_id=None,
            organization_id=None
        )
        
        if device_data:
            # Remove any sensitive data
            device_data.pop('rag_chunks', None)
            
            # Add SEO metadata
            device_data['seo'] = {
                "title": f"{device_data['device_name']} - {device_data['manufacturer_name']}",
                "description": device_data.get('device_description', '')[:160],
                "keywords": [
                    device_data['device_name'],
                    device_data['manufacturer_name'],
                    f"FDA Class {device_data['device_class']}",
                    "medical device"
                ]
            }
        
        return device_data
