"""
Dynamic Vendor Public Pages from FDA/Supabase Data
Using manufacturer name as unique identifier - much faster!
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import List, Dict, Any, Optional
import logging
import re
import hashlib
import base64
from urllib.parse import quote, unquote
import os

from src.core.config import settings
from src.core.redis_manager import RedisManager

router = APIRouter(prefix="/vendor", tags=["vendor-public-dynamic"])
logger = logging.getLogger(__name__)

# Initialize Supabase client - Make it optional
supabase = None
try:
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        # Disable proxy to avoid the error
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        
        from supabase import create_client, Client
        try:
            from supabase._sync.client import SyncClient
            from supabase.lib.client_options import ClientOptions
            
            options = ClientOptions()
            supabase = SyncClient.create(
                supabase_url=settings.SUPABASE_URL,
                supabase_key=settings.SUPABASE_SERVICE_KEY,
                options=options
            )
            logger.info("Vendor dynamic: Supabase initialized")
        except Exception as e:
            logger.warning(f"Vendor dynamic: Could not initialize Supabase: {e}")
    else:
        logger.warning("Vendor dynamic: Supabase not configured")
except Exception as e:
    logger.warning(f"Vendor dynamic: Supabase setup failed: {e}")

# Initialize Redis for caching
try:
    redis_manager = RedisManager() if settings.REDIS_URL else None
except:
    redis_manager = None
    logger.warning("Redis not available - running without cache")


def generate_manufacturer_id(manufacturer_name: str) -> str:
    """Generate a unique ID for a manufacturer using hash."""
    # Create a short hash of the manufacturer name
    hash_obj = hashlib.md5(manufacturer_name.encode())
    return hash_obj.hexdigest()[:12]


@router.get("/search")
async def search_manufacturers(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Search for medical device manufacturers from FDA data.
    Returns manufacturer names with their unique IDs.
    """
    if not supabase:
        # Return mock data if Supabase not available
        mock_manufacturers = [
            {'name': 'Medtronic', 'device_count': 100},
            {'name': 'Abbott', 'device_count': 80},
            {'name': 'Johnson & Johnson', 'device_count': 60}
        ]
        filtered = [m for m in mock_manufacturers if q.lower() in m['name'].lower()]
        
        return {
            'manufacturers': [
                {
                    'id': generate_manufacturer_id(m['name']),
                    'name': m['name'],
                    'encoded_name': base64.b64encode(m['name'].encode()).decode(),
                    'device_count': m['device_count'],
                    'url': f'/vendor/by-id/{generate_manufacturer_id(m["name"])}'
                }
                for m in filtered[:limit]
            ],
            'total': len(filtered)
        }
    
    try:
        # Get unique manufacturers matching the search
        response = supabase.table('gudid_devices').select(
            'manufacturer_name'
        ).ilike('manufacturer_name', f'%{q}%').limit(100).execute()
        
        # Process to get unique manufacturers
        manufacturers_dict = {}
        for row in response.data:
            name = row.get('manufacturer_name')
            if name:
                manufacturers_dict[name] = manufacturers_dict.get(name, 0) + 1
        
        # Convert to list
        manufacturers = []
        for name, count in sorted(manufacturers_dict.items(), key=lambda x: x[1], reverse=True)[:limit]:
            manufacturers.append({
                'id': generate_manufacturer_id(name),
                'name': name,
                'encoded_name': base64.b64encode(name.encode()).decode(),  # Safe encoding
                'device_count': count,
                'url': f'/vendor/by-id/{generate_manufacturer_id(name)}'
            })
        
        return {
            'manufacturers': manufacturers,
            'total': len(manufacturers)
        }
        
    except Exception as e:
        logger.error(f"Manufacturer search error: {e}")
        return {'manufacturers': [], 'total': 0}


@router.get("/by-name/{manufacturer_name}")
async def get_manufacturer_by_name(
    manufacturer_name: str,
    request: Request
):
    """
    Get vendor page using exact manufacturer name.
    Much faster than slug matching!
    """
    if not supabase:
        # Return mock data
        decoded_name = unquote(manufacturer_name)
        return {
            'id': generate_manufacturer_id(decoded_name),
            'manufacturer_name': decoded_name,
            'display_name': decoded_name,
            'tagline': f'Medical Devices by {decoded_name}',
            'description': f'{decoded_name} medical devices (Demo mode - Supabase not connected)',
            'statistics': {
                'total_devices': 50,
                'device_classes': {'II': 30, 'III': 20},
                'mri_safety_breakdown': {'MR Safe': 20, 'MR Conditional': 30},
                'sample_size': 50
            },
            'features': {
                'chat_enabled': True,
                'fda_data_available': False,
                'lead_capture_enabled': True
            },
            'featured_devices': []
        }
    
    try:
        # Decode the manufacturer name if it was URL encoded
        decoded_name = unquote(manufacturer_name)
        
        # Try to get from cache first
        cache_key = f"vendor:name:{decoded_name}"
        if redis_manager:
            cached = await redis_manager.get(cache_key)
            if cached:
                return cached
        
        # Get total device count - SINGLE QUERY
        count_response = supabase.table('gudid_devices').select(
            'primary_di',
            count='exact'
        ).eq('manufacturer_name', decoded_name).limit(1).execute()
        
        if not count_response.count or count_response.count == 0:
            # Try case-insensitive match
            count_response = supabase.table('gudid_devices').select(
                'primary_di',
                count='exact'
            ).ilike('manufacturer_name', decoded_name).limit(1).execute()
            
            if not count_response.count or count_response.count == 0:
                raise HTTPException(status_code=404, detail="Manufacturer not found")
        
        total_devices = count_response.count
        
        # Get sample of devices for statistics - SINGLE QUERY with limit
        sample_response = supabase.table('gudid_devices').select(
            'device_class, mri_safety, sterile, life_supporting, device_name, primary_di, brand_name, model_number, gmdn_terms'
        ).eq('manufacturer_name', decoded_name).limit(100).execute()
        
        # Calculate statistics from sample
        device_classes = {}
        mri_safety_stats = {}
        sterile_count = 0
        life_supporting_count = 0
        featured_devices = []
        
        for idx, device in enumerate(sample_response.data):
            # Stats
            if device.get('device_class'):
                device_classes[device['device_class']] = device_classes.get(device['device_class'], 0) + 1
            if device.get('mri_safety'):
                mri_safety_stats[device['mri_safety']] = mri_safety_stats.get(device['mri_safety'], 0) + 1
            if device.get('sterile'):
                sterile_count += 1
            if device.get('life_supporting'):
                life_supporting_count += 1
            
            # Featured devices (first 10)
            if idx < 10:
                featured_devices.append({
                    'id': device['primary_di'],
                    'name': device['device_name'],
                    'brand': device.get('brand_name'),
                    'model': device.get('model_number'),
                    'category': device.get('gmdn_terms')
                })
        
        # Build response
        vendor_profile = {
            'id': generate_manufacturer_id(decoded_name),
            'manufacturer_name': decoded_name,
            'display_name': decoded_name,
            'tagline': f'Medical Devices by {decoded_name}',
            'description': f'{decoded_name} has {total_devices} FDA-registered medical devices.',
            
            'statistics': {
                'total_devices': total_devices,
                'device_classes': device_classes,
                'mri_safety_breakdown': mri_safety_stats,
                'sample_size': len(sample_response.data)
            },
            
            'features': {
                'chat_enabled': True,
                'fda_data_available': True,
                'lead_capture_enabled': True
            },
            
            'featured_devices': featured_devices
        }
        
        # Cache for 1 hour
        if redis_manager:
            await redis_manager.set(cache_key, vendor_profile, expire=3600)
        
        return vendor_profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get manufacturer by name error: {e}")
        raise HTTPException(status_code=500, detail="Error loading manufacturer")


@router.get("/by-id/{manufacturer_id}")
async def get_manufacturer_by_id(
    manufacturer_id: str,
    request: Request
):
    """
    Get vendor page using manufacturer ID (hash).
    Need to lookup the name first, then get data.
    """
    try:
        # For now, return an error saying to use the name endpoint
        # In production, you'd maintain an ID->name mapping
        raise HTTPException(
            status_code=400,
            detail="Please use /vendor/by-name/{manufacturer_name} endpoint instead"
        )
    except Exception as e:
        logger.error(f"Get by ID error: {e}")
        raise


@router.get("/by-name/{manufacturer_name}/devices")
async def get_manufacturer_devices(
    manufacturer_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    device_class: Optional[str] = None
):
    """
    Get paginated devices for a manufacturer.
    Using exact name for fast queries.
    """
    if not supabase:
        # Return mock data
        decoded_name = unquote(manufacturer_name)
        return {
            'manufacturer': decoded_name,
            'devices': [],
            'total_count': 0,
            'page': page,
            'limit': limit,
            'total_pages': 0
        }
    
    try:
        decoded_name = unquote(manufacturer_name)
        
        # Build base query
        query = supabase.table('gudid_devices').select(
            'primary_di, device_name, brand_name, model_number, catalog_number, '
            'device_class, device_description, gmdn_terms, mri_safety, '
            'sterile, single_use, implantable, life_supporting, rx_required',
            count='exact'
        ).eq('manufacturer_name', decoded_name)
        
        # Apply filters
        if device_class:
            query = query.eq('device_class', device_class)
        
        if search:
            # Search in device name, brand, or model
            query = query.or_(
                f'device_name.ilike.%{search}%,'
                f'brand_name.ilike.%{search}%,'
                f'model_number.ilike.%{search}%'
            )
        
        # Get total count first
        total_response = query.execute()
        total_count = total_response.count or 0
        
        # Apply pagination
        offset = (page - 1) * limit
        paginated_query = query.range(offset, offset + limit - 1)
        
        # Get paginated results
        response = paginated_query.execute()
        
        devices = []
        for device in (response.data or []):
            devices.append({
                'id': device['primary_di'],
                'name': device['device_name'],
                'brand': device.get('brand_name'),
                'model': device.get('model_number'),
                'catalog': device.get('catalog_number'),
                'class': device.get('device_class'),
                'description': device.get('device_description', '')[:200] + '...' if device.get('device_description') and len(device.get('device_description', '')) > 200 else device.get('device_description'),
                'category': device.get('gmdn_terms'),
                'mri_safety': device.get('mri_safety'),
                'characteristics': {
                    'sterile': device.get('sterile'),
                    'single_use': device.get('single_use'),
                    'implantable': device.get('implantable'),
                    'life_supporting': device.get('life_supporting'),
                    'prescription_required': device.get('rx_required')
                }
            })
        
        return {
            'manufacturer': decoded_name,
            'devices': devices,
            'total_count': total_count,
            'page': page,
            'limit': limit,
            'total_pages': (total_count + limit - 1) // limit if total_count > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"Get devices error: {e}")
        raise HTTPException(status_code=500, detail="Error loading devices")


@router.get("/device/{device_id}/info")
async def get_device_info(device_id: str):
    """
    Get complete device information for display and chat context.
    Single endpoint for all device data needs.
    """
    if not supabase:
        # Return mock device
        return {
            'id': device_id,
            'name': 'Sample Device',
            'manufacturer': 'Sample Manufacturer',
            'fda_class': 'II',
            'description': 'Demo device - Supabase not connected',
            'ai_context': {
                'device_type': 'medical device',
                'safety_profile': {},
                'regulatory': {}
            }
        }
    
    try:
        # Get device from FDA database
        response = supabase.table('gudid_devices').select('*').eq(
            'primary_di', device_id
        ).single().execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Device not found")
        
        device = response.data
        
        # Format for frontend and AI
        device_info = {
            # Basic Information
            'id': device['primary_di'],
            'name': device.get('device_name', 'Unknown Device'),
            'manufacturer': device.get('manufacturer_name', 'Unknown'),
            'brand': device.get('brand_name'),
            'model': device.get('model_number'),
            'catalog': device.get('catalog_number'),
            
            # Classification
            'fda_class': device.get('device_class'),
            'class_name': device.get('device_class_name'),
            'gmdn_terms': device.get('gmdn_terms'),
            'product_code': device.get('product_code'),
            'regulation_number': device.get('regulation_number'),
            
            # Description
            'description': device.get('device_description'),
            'size_text': device.get('device_size_text'),
            
            # Safety Information
            'mri_safety': device.get('mri_safety'),
            'mri_safety_status': device.get('mri_safety_status'),
            
            # Usage Characteristics
            'sterile': device.get('sterile', False),
            'single_use': device.get('single_use', False),
            'implantable': device.get('implantable', False),
            'life_supporting': device.get('life_supporting', False),
            'prescription_required': device.get('rx_required', False),
            'over_the_counter': device.get('otc', False),
            
            # Additional Properties
            'kit': device.get('kit', False),
            'combination_product': device.get('combination_product', False),
            'human_cell_tissue': device.get('human_cell_tissue', False),
            'labeled_contains_nrl': device.get('device_labeled_contains_nrl', False),
            'labeled_no_nrl': device.get('device_labeled_no_nrl', False),
            
            # For AI Context
            'ai_context': {
                'device_type': device.get('gmdn_terms', 'medical device'),
                'safety_profile': {
                    'mri': device.get('mri_safety', 'Not specified'),
                    'sterile': 'Yes' if device.get('sterile') else 'No',
                    'single_use': 'Yes' if device.get('single_use') else 'No',
                    'implantable': 'Yes' if device.get('implantable') else 'No',
                    'life_supporting': 'Yes' if device.get('life_supporting') else 'No'
                },
                'regulatory': {
                    'fda_class': device.get('device_class'),
                    'prescription': 'Required' if device.get('rx_required') else 'Not required',
                    'otc': 'Yes' if device.get('otc') else 'No'
                }
            }
        }
        
        return device_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get device info error: {e}")
        raise HTTPException(status_code=500, detail="Error loading device information")


@router.post("/device/{device_id}/chat")
async def chat_about_device(
    device_id: str,
    request: Dict[str, Any]
):
    """
    Chat about a device using OpenAI with real FDA data.
    Simplified endpoint that gets device info internally.
    """
    try:
        message = request.get('message')
        session_id = request.get('session_id')
        
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Get device info
        device_info = await get_device_info(device_id)
        
        # Check if OpenAI is configured
        if not settings.OPENAI_API_KEY:
            # Return a helpful response without AI
            return {
                'session_id': session_id or f"chat-{device_id}-no-ai",
                'device_id': device_id,
                'device_name': device_info['name'],
                'user_message': message,
                'ai_response': f"I have information about the {device_info['name']} from {device_info['manufacturer']}. "
                               f"This is a FDA Class {device_info.get('fda_class', 'unknown')} device. "
                               f"(Note: AI service not configured, showing basic FDA data only)",
                'sources': ['FDA GUDID Database'],
                'ai_available': False
            }
        
        # Use OpenAI
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Create context-aware prompt
        system_prompt = f"""You are a medical device expert providing information about FDA-registered medical devices.

Current Device: {device_info['name']}
Manufacturer: {device_info['manufacturer']}
FDA Class: {device_info.get('fda_class', 'Not specified')}
Description: {device_info.get('description', 'No description available')}

Important: Provide accurate information based on the FDA data. Do not provide medical advice. 
Always recommend consulting healthcare professionals for medical decisions."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
        
        # Get response from OpenAI
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview" if "gpt-4" in settings.OPENAI_MODEL else "gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        return {
            'session_id': session_id or f"chat-{device_id}-{hash(message)}",
            'device_id': device_id,
            'device_name': device_info['name'],
            'user_message': message,
            'ai_response': ai_response,
            'sources': ['FDA GUDID Database'],
            'ai_available': True,
            'tokens_used': response.usage.total_tokens if hasattr(response, 'usage') else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        # Fallback response
        return {
            'session_id': session_id or f"chat-{device_id}-error",
            'device_id': device_id,
            'user_message': message,
            'ai_response': "I apologize, but I'm having trouble processing your request. Please try again or contact support.",
            'sources': ['FDA GUDID Database'],
            'ai_available': False,
            'error': str(e)
        }


@router.post("/lead")
async def capture_lead(request: Dict[str, Any]):
    """
    Simple lead capture endpoint.
    """
    try:
        email = request.get('email')
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Log the lead (you can add database storage later)
        logger.info(f"Lead captured: {email} for {request.get('manufacturer_name', 'unknown')}")
        
        return {
            'success': True,
            'message': 'Thank you for your interest! We will contact you soon.',
            'lead_id': f"lead-{hash(email)}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lead capture error: {e}")
        raise HTTPException(status_code=500, detail="Error capturing lead")
