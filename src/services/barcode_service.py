"""
Barcode and UDI Scanning Service.
Handles FDA UDI parsing, barcode recognition, and device identification.
REAL implementation for medical device barcodes.
"""
import re
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from pyzbar import pyzbar
from PIL import Image
import io
import base64
from dataclasses import dataclass

from src.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


@dataclass
class UDIComponents:
    """Parsed UDI components"""
    di: str  # Device Identifier
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    expiration_date: Optional[datetime] = None
    manufacturing_date: Optional[datetime] = None
    distinct_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "device_identifier": self.di,
            "lot_number": self.lot_number,
            "serial_number": self.serial_number,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "manufacturing_date": self.manufacturing_date.isoformat() if self.manufacturing_date else None,
            "distinct_id": self.distinct_id
        }


class BarcodeService:
    """
    Service for barcode scanning and UDI parsing.
    Supports GS1-128, HIBCC, ICCBBA formats.
    """
    
    def __init__(self):
        # GS1 Application Identifiers (AIs)
        self.gs1_ais = {
            "01": ("gtin", 14, "fixed"),  # Global Trade Item Number
            "10": ("lot_number", None, "variable"),  # Batch/Lot Number
            "11": ("production_date", 6, "fixed"),  # Production Date
            "17": ("expiration_date", 6, "fixed"),  # Expiration Date
            "21": ("serial_number", None, "variable"),  # Serial Number
            "240": ("additional_id", None, "variable"),  # Additional Product ID
            "8020": ("payment_reference", None, "variable"),  # Payment Reference
        }
        
        # Group separator character
        self.gs = chr(29)  # ASCII GS character
        
        # Date format patterns
        self.date_patterns = {
            6: "%y%m%d",  # YYMMDD
            8: "%Y%m%d",  # YYYYMMDD
        }
    
    async def scan_barcode_image(self, image_data: bytes) -> List[Dict[str, Any]]:
        """
        Scan barcodes from image data.
        Returns list of detected barcodes with decoded information.
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to grayscale for better detection
            if image.mode != 'L':
                image = image.convert('L')
            
            # Detect barcodes
            barcodes = pyzbar.decode(image)
            
            results = []
            for barcode in barcodes:
                # Get barcode data
                data = barcode.data.decode('utf-8', errors='ignore')
                
                # Parse based on format
                result = {
                    "type": barcode.type,
                    "data": data,
                    "rect": {
                        "left": barcode.rect.left,
                        "top": barcode.rect.top,
                        "width": barcode.rect.width,
                        "height": barcode.rect.height
                    },
                    "quality": barcode.quality if hasattr(barcode, 'quality') else None
                }
                
                # Try to parse as UDI
                if barcode.type in ['CODE128', 'DATAMATRIX', 'QRCODE']:
                    udi_result = self.parse_udi(data)
                    if udi_result:
                        result["udi"] = udi_result.to_dict()
                        result["format"] = "FDA_UDI"
                
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Barcode scanning error: {e}")
            raise ValidationError(f"Failed to scan barcode: {str(e)}")
    
    def parse_udi(self, udi_string: str) -> Optional[UDIComponents]:
        """
        Parse FDA UDI string.
        Supports GS1, HIBCC, and ICCBBA formats.
        """
        # Clean input
        udi_string = udi_string.strip()
        
        # Try different parsers
        parsers = [
            self._parse_gs1_udi,
            self._parse_hibcc_udi,
            self._parse_iccbba_udi
        ]
        
        for parser in parsers:
            try:
                result = parser(udi_string)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Parser {parser.__name__} failed: {e}")
                continue
        
        # If no parser succeeded, try basic extraction
        return self._parse_basic_udi(udi_string)
    
    def _parse_gs1_udi(self, udi: str) -> Optional[UDIComponents]:
        """
        Parse GS1-128 format UDI.
        Example: (01)00889842001234(17)250131(10)LOT123(21)SER456
        """
        # Remove parentheses if present (human readable)
        udi_clean = re.sub(r'[()]', '', udi)
        
        # Initialize components
        components = UDIComponents(di="")
        
        # Parse Application Identifiers
        position = 0
        while position < len(udi_clean):
            # Try to find AI
            ai_found = False
            
            for ai_length in [2, 3, 4]:  # AI can be 2-4 digits
                if position + ai_length <= len(udi_clean):
                    potential_ai = udi_clean[position:position + ai_length]
                    
                    if potential_ai in self.gs1_ais:
                        ai_info = self.gs1_ais[potential_ai]
                        field_name = ai_info[0]
                        field_length = ai_info[1]
                        
                        # Move past AI
                        position += ai_length
                        
                        # Extract value
                        if field_length:  # Fixed length
                            value = udi_clean[position:position + field_length]
                            position += field_length
                        else:  # Variable length - read until GS or end
                            gs_pos = udi_clean.find(self.gs, position)
                            if gs_pos != -1:
                                value = udi_clean[position:gs_pos]
                                position = gs_pos + 1
                            else:
                                # Read until next AI or end
                                next_ai_pos = len(udi_clean)
                                for next_ai in self.gs1_ais:
                                    ai_pos = udi_clean.find(next_ai, position)
                                    if ai_pos != -1 and ai_pos < next_ai_pos:
                                        next_ai_pos = ai_pos
                                value = udi_clean[position:next_ai_pos]
                                position = next_ai_pos
                        
                        # Process value based on field
                        if field_name == "gtin":
                            components.di = value
                        elif field_name == "lot_number":
                            components.lot_number = value
                        elif field_name == "serial_number":
                            components.serial_number = value
                        elif field_name == "expiration_date":
                            components.expiration_date = self._parse_date(value)
                        elif field_name == "production_date":
                            components.manufacturing_date = self._parse_date(value)
                        
                        ai_found = True
                        break
            
            if not ai_found:
                position += 1
        
        # Validate we got at least DI
        if components.di:
            return components
        
        return None
    
    def _parse_hibcc_udi(self, udi: str) -> Optional[UDIComponents]:
        """
        Parse HIBCC format UDI.
        Format: +$$AAABBBCCCDDDEEF/$$GHHHHHJJKKKYYLLLLL
        """
        if not udi.startswith('+'):
            return None
        
        # Split primary and secondary data
        parts = udi.split('/')
        if not parts:
            return None
        
        primary = parts[0]
        secondary = parts[1] if len(parts) > 1 else ""
        
        # Parse primary (DI)
        if len(primary) < 8:
            return None
        
        components = UDIComponents(di=primary[1:])  # Remove + prefix
        
        # Parse secondary data if present
        if secondary and secondary.startswith('$$'):
            # Extract lot and expiration
            if len(secondary) >= 13:
                # Lot number (5 chars)
                components.lot_number = secondary[7:12].strip()
                
                # Expiration date (YYDDD format)
                if len(secondary) >= 15:
                    exp_str = secondary[12:17]
                    try:
                        year = 2000 + int(exp_str[:2])
                        day_of_year = int(exp_str[2:5])
                        components.expiration_date = datetime(year, 1, 1) + timedelta(days=day_of_year - 1)
                    except:
                        pass
        
        return components
    
    def _parse_iccbba_udi(self, udi: str) -> Optional[UDIComponents]:
        """
        Parse ICCBBA 128 format (blood/tissue products).
        Format: =)>800PPPPPPPPPPPPYYYYDDDSSSSSS
        """
        if not udi.startswith('='):
            return None
        
        # Remove data identifier
        data = udi[2:] if udi.startswith('=>') else udi[1:]
        
        if len(data) < 13:
            return None
        
        # Extract components
        components = UDIComponents(di=data[:13])
        
        # Parse additional data if present
        if len(data) >= 20:
            # Year and day of year
            try:
                year = int(data[13:17])
                day = int(data[17:20])
                components.expiration_date = datetime(year, 1, 1) + timedelta(days=day - 1)
            except:
                pass
        
        # Serial number if present
        if len(data) >= 26:
            components.serial_number = data[20:26]
        
        return components
    
    def _parse_basic_udi(self, udi: str) -> Optional[UDIComponents]:
        """
        Basic UDI parsing for unknown formats.
        Attempts to extract DI at minimum.
        """
        # Remove common prefixes/suffixes
        udi_clean = udi.strip().upper()
        
        # Try to identify DI (usually 14 digits for GTIN)
        di_match = re.search(r'\b\d{14}\b', udi_clean)
        if di_match:
            return UDIComponents(di=di_match.group())
        
        # If no standard DI found, use whole string if reasonable length
        if 8 <= len(udi_clean) <= 30:
            return UDIComponents(di=udi_clean)
        
        return None
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from various formats."""
        if not date_str or not date_str.isdigit():
            return None
        
        # Try different date formats
        for length, format_str in self.date_patterns.items():
            if len(date_str) == length:
                try:
                    return datetime.strptime(date_str, format_str)
                except ValueError:
                    continue
        
        return None
    
    def validate_gtin(self, gtin: str) -> bool:
        """
        Validate GTIN checksum.
        Supports GTIN-8, GTIN-12, GTIN-13, GTIN-14.
        """
        if not gtin.isdigit():
            return False
        
        if len(gtin) not in [8, 12, 13, 14]:
            return False
        
        # Calculate check digit
        total = 0
        for i, digit in enumerate(gtin[:-1]):
            if i % 2 == 0:
                total += int(digit)
            else:
                total += int(digit) * 3
        
        check_digit = (10 - (total % 10)) % 10
        
        return check_digit == int(gtin[-1])
    
    def format_udi_human_readable(self, udi_components: UDIComponents) -> str:
        """
        Format UDI components for human readable display.
        """
        parts = [f"DI: {udi_components.di}"]
        
        if udi_components.lot_number:
            parts.append(f"LOT: {udi_components.lot_number}")
        
        if udi_components.serial_number:
            parts.append(f"SN: {udi_components.serial_number}")
        
        if udi_components.expiration_date:
            parts.append(f"EXP: {udi_components.expiration_date.strftime('%Y-%m-%d')}")
        
        if udi_components.manufacturing_date:
            parts.append(f"MFG: {udi_components.manufacturing_date.strftime('%Y-%m-%d')}")
        
        return " | ".join(parts)
    
    async def generate_barcode(
        self, 
        udi_components: UDIComponents,
        format: str = "GS1-128"
    ) -> bytes:
        """
        Generate barcode image from UDI components.
        Returns PNG image data.
        """
        try:
            import barcode
            from barcode.writer import ImageWriter
            
            # Format UDI string based on type
            if format == "GS1-128":
                udi_string = self._format_gs1_string(udi_components)
                code = barcode.get('code128', udi_string, writer=ImageWriter())
            elif format == "DATAMATRIX":
                udi_string = self._format_gs1_string(udi_components, human_readable=False)
                code = barcode.get('datamatrix', udi_string, writer=ImageWriter())
            else:
                raise ValueError(f"Unsupported barcode format: {format}")
            
            # Generate image
            output = io.BytesIO()
            code.write(output)
            output.seek(0)
            
            return output.read()
            
        except Exception as e:
            logger.error(f"Barcode generation error: {e}")
            raise ValidationError(f"Failed to generate barcode: {str(e)}")
    
    def _format_gs1_string(self, components: UDIComponents, human_readable: bool = True) -> str:
        """Format UDI components as GS1 string."""
        parts = []
        
        # Add DI (GTIN)
        if human_readable:
            parts.append(f"(01){components.di}")
        else:
            parts.append(f"01{components.di}")
        
        # Add other components
        if components.expiration_date:
            exp_str = components.expiration_date.strftime("%y%m%d")
            if human_readable:
                parts.append(f"(17){exp_str}")
            else:
                parts.append(f"17{exp_str}")
        
        if components.lot_number:
            if human_readable:
                parts.append(f"(10){components.lot_number}")
            else:
                parts.append(f"10{components.lot_number}{self.gs}")
        
        if components.serial_number:
            if human_readable:
                parts.append(f"(21){components.serial_number}")
            else:
                parts.append(f"21{components.serial_number}")
        
        return "".join(parts)


# Create singleton instance
barcode_service = BarcodeService()
