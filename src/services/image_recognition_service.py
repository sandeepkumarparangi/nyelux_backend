"""
Image Recognition Service for medical device identification.
Uses computer vision and ML to identify devices from photos.
"""
import logging
from typing import Dict, List, Optional, Tuple, Any
import io
import base64
from datetime import datetime
from PIL import Image
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from src.db.models.vendor_device import VendorDevice
from src.db.models.gudid_device import GUDIDDevice
from src.core.config import settings

logger = logging.getLogger(__name__)


class DeviceRecognitionResult:
    """Result from device recognition"""
    def __init__(self, device_id: str, device_name: str, confidence: float, 
                 device_type: str = "vendor", metadata: Dict = None):
        self.device_id = device_id
        self.device_name = device_name
        self.confidence = confidence
        self.device_type = device_type  # "vendor" or "gudid"
        self.metadata = metadata or {}
        
    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "confidence": round(self.confidence, 2),
            "device_type": self.device_type,
            "metadata": self.metadata
        }


class ImageRecognitionService:
    """
    Service for identifying medical devices from images.
    Uses ML models for visual recognition and text extraction.
    """
    
    def __init__(self):
        self.max_image_size = 10 * 1024 * 1024  # 10MB
        self.supported_formats = {'JPEG', 'PNG', 'BMP', 'GIF', 'WEBP'}
        self.min_confidence_threshold = 0.3
        
    async def recognize_device(
        self, 
        image_data: bytes, 
        db: AsyncSession,
        include_similar: bool = True,
        max_results: int = 5
    ) -> List[DeviceRecognitionResult]:
        """
        Identify medical device from image.
        Returns list of possible matches with confidence scores.
        """
        try:
            # Validate image
            image = self._validate_and_load_image(image_data)
            
            # Extract features (simplified for now)
            results = []
            
            # In a real implementation, this would:
            # 1. Use a trained CNN model for device classification
            # 2. Extract text using OCR
            # 3. Match against device database
            # 4. Use visual similarity search
            
            # For now, return mock results based on image properties
            # This is where you'd integrate with a real ML model
            
            # Simulate text extraction
            extracted_text = await self._extract_text_from_image(image)
            
            if extracted_text:
                # Search devices by extracted text
                device_results = await self._search_devices_by_text(
                    db, extracted_text, max_results
                )
                results.extend(device_results)
            
            # If no text found or need more results, use visual similarity
            if include_similar and len(results) < max_results:
                # This would use image embeddings in production
                similar_results = await self._find_visually_similar_devices(
                    db, image, max_results - len(results)
                )
                results.extend(similar_results)
            
            # Sort by confidence
            results.sort(key=lambda x: x.confidence, reverse=True)
            
            return results[:max_results]
            
        except Exception as e:
            logger.error(f"Error in device recognition: {e}")
            raise
    
    def _validate_and_load_image(self, image_data: bytes) -> Image.Image:
        """Validate and load image data"""
        # Check size
        if len(image_data) > self.max_image_size:
            raise ValueError(f"Image size exceeds {self.max_image_size} bytes")
        
        # Load image
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # Check format
            if image.format not in self.supported_formats:
                raise ValueError(f"Unsupported image format: {image.format}")
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
                
            return image
            
        except Exception as e:
            raise ValueError(f"Invalid image data: {e}")
    
    async def _extract_text_from_image(self, image: Image.Image) -> Optional[str]:
        """Extract text from image using OCR"""
        try:
            # In production, this would use Tesseract or cloud OCR service
            # For now, return None to simulate no text found
            # This is where pytesseract would be integrated
            
            # Example of what this would look like:
            # import pytesseract
            # text = pytesseract.image_to_string(image)
            # return text.strip() if text else None
            
            return None
            
        except Exception as e:
            logger.error(f"Error in OCR: {e}")
            return None
    
    async def _search_devices_by_text(
        self, 
        db: AsyncSession, 
        text: str, 
        max_results: int
    ) -> List[DeviceRecognitionResult]:
        """Search devices by extracted text"""
        results = []
        
        # Clean and prepare search text
        search_terms = text.lower().split()
        
        # Search in vendor devices
        query = select(VendorDevice).where(
            VendorDevice.is_active == True
        )
        
        # Add text search conditions
        for term in search_terms[:3]:  # Limit search terms
            query = query.where(
                (VendorDevice.custom_name.ilike(f"%{term}%")) |
                (VendorDevice.internal_sku.ilike(f"%{term}%"))
            )
        
        query = query.limit(max_results)
        
        result = await db.execute(query)
        devices = result.scalars().all()
        
        for device in devices:
            # Calculate confidence based on text match
            confidence = self._calculate_text_match_confidence(
                text, device.custom_name or ""
            )
            
            if confidence >= self.min_confidence_threshold:
                results.append(DeviceRecognitionResult(
                    device_id=str(device.id),
                    device_name=device.custom_name or "Unknown Device",
                    confidence=confidence,
                    device_type="vendor",
                    metadata={"match_type": "text"}
                ))
        
        return results
    
    async def _find_visually_similar_devices(
        self, 
        db: AsyncSession, 
        image: Image.Image, 
        max_results: int
    ) -> List[DeviceRecognitionResult]:
        """Find visually similar devices"""
        # In production, this would:
        # 1. Generate image embedding using a pre-trained model
        # 2. Search vector database for similar embeddings
        # 3. Return matched devices
        
        # For now, return some mock results
        # This is where you'd integrate with a vector similarity search
        
        results = []
        
        # Simulate finding some devices
        query = select(VendorDevice).where(
            VendorDevice.is_active == True
        ).limit(max_results)
        
        result = await db.execute(query)
        devices = result.scalars().all()
        
        for i, device in enumerate(devices):
            # Mock confidence based on position
            confidence = 0.8 - (i * 0.1)
            
            if confidence >= self.min_confidence_threshold:
                results.append(DeviceRecognitionResult(
                    device_id=str(device.id),
                    device_name=device.custom_name or "Unknown Device",
                    confidence=confidence,
                    device_type="vendor",
                    metadata={"match_type": "visual"}
                ))
        
        return results
    
    def _calculate_text_match_confidence(self, extracted: str, device_name: str) -> float:
        """Calculate confidence score for text match"""
        if not extracted or not device_name:
            return 0.0
            
        extracted_lower = extracted.lower()
        device_lower = device_name.lower()
        
        # Simple matching algorithm
        # In production, use more sophisticated string matching
        
        if device_lower in extracted_lower:
            return 0.9
        
        # Check word overlap
        extracted_words = set(extracted_lower.split())
        device_words = set(device_lower.split())
        
        if not device_words:
            return 0.0
            
        overlap = len(extracted_words & device_words)
        return min(overlap / len(device_words), 0.8)
    
    async def process_barcode(
        self, 
        barcode_data: str, 
        barcode_type: str,
        db: AsyncSession
    ) -> Optional[DeviceRecognitionResult]:
        """Process barcode and identify device"""
        try:
            # Parse barcode based on type
            device_info = self._parse_barcode(barcode_data, barcode_type)
            
            if not device_info:
                return None
            
            # Search for device by identifier
            device = await self._find_device_by_identifier(
                db, 
                device_info.get("di"), 
                device_info.get("serial")
            )
            
            if device:
                return DeviceRecognitionResult(
                    device_id=device.primary_di if hasattr(device, 'primary_di') else str(device.id),
                    device_name=device.device_name if hasattr(device, 'device_name') else device.custom_name,
                    confidence=1.0,  # Exact match
                    device_type="gudid" if hasattr(device, 'primary_di') else "vendor",
                    metadata={
                        "match_type": "barcode",
                        "barcode_type": barcode_type,
                        **device_info
                    }
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing barcode: {e}")
            return None
    
    def _parse_barcode(self, data: str, barcode_type: str) -> Optional[Dict[str, str]]:
        """Parse barcode data based on type"""
        result = {}
        
        if barcode_type == "UDI" or barcode_type == "GS1-128":
            # Parse FDA UDI format
            # Format: (01)DI(17)EXPIRY(10)LOT(21)SERIAL
            
            if data.startswith("(01)"):
                # Extract DI
                di_start = data.find("(01)") + 4
                di_end = data.find("(", di_start)
                if di_end == -1:
                    di_end = len(data)
                result["di"] = data[di_start:di_end]
                
                # Extract other identifiers
                if "(17)" in data:
                    exp_start = data.find("(17)") + 4
                    exp_end = data.find("(", exp_start)
                    if exp_end == -1:
                        exp_end = len(data)
                    result["expiry"] = data[exp_start:exp_end]
                
                if "(10)" in data:
                    lot_start = data.find("(10)") + 4
                    lot_end = data.find("(", lot_start)
                    if lot_end == -1:
                        lot_end = len(data)
                    result["lot"] = data[lot_start:lot_end]
                
                if "(21)" in data:
                    serial_start = data.find("(21)") + 4
                    serial_end = data.find("(", serial_start)
                    if serial_end == -1:
                        serial_end = len(data)
                    result["serial"] = data[serial_start:serial_end]
        else:
            # For other barcode types, use the raw data
            result["raw"] = data
        
        return result if result else None
    
    async def _find_device_by_identifier(
        self, 
        db: AsyncSession, 
        di: Optional[str], 
        serial: Optional[str]
    ) -> Optional[Any]:
        """Find device by DI or serial number"""
        if di:
            # Search GUDID devices
            result = await db.execute(
                select(GUDIDDevice).where(GUDIDDevice.primary_di == di)
            )
            device = result.scalar_one_or_none()
            if device:
                return device
        
        # If not found in GUDID or searching by serial, check vendor devices
        if serial:
            result = await db.execute(
                select(VendorDevice).where(
                    VendorDevice.internal_sku == serial,
                    VendorDevice.is_active == True
                )
            )
            device = result.scalar_one_or_none()
            if device:
                return device
        
        return None
    
    def validate_image_file(self, filename: str, content_type: str) -> bool:
        """Validate uploaded image file"""
        # Check content type
        valid_types = {
            'image/jpeg', 'image/png', 'image/gif', 
            'image/webp', 'image/bmp'
        }
        
        if content_type not in valid_types:
            return False
        
        # Check file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        
        return f".{ext}" in valid_extensions
