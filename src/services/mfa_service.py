"""
MFA (Multi-Factor Authentication) Service
Handles TOTP generation, verification, and backup codes
"""
import pyotp
import secrets
import string
from typing import List, Tuple, Optional
import json
from datetime import datetime, timedelta

from src.services.encryption_service import EncryptionService


class MFAService:
    """Service for handling MFA operations"""
    
    def __init__(self):
        self.encryption_service = EncryptionService()
        
    def generate_secret(self) -> str:
        """Generate a new TOTP secret"""
        return pyotp.random_base32()
    
    def generate_provisioning_uri(self, secret: str, email: str, issuer: str = "Nyelux") -> str:
        """Generate provisioning URI for QR code"""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)
    
    def verify_totp(self, token: str, secret: str, window: int = 1) -> bool:
        """
        Verify a TOTP token
        
        Args:
            token: The 6-digit token from the user
            secret: The user's TOTP secret
            window: Number of time periods to check before/after current
            
        Returns:
            True if token is valid, False otherwise
        """
        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(token, valid_window=window)
        except Exception:
            return False
    
    def generate_backup_codes(self, count: int = 10) -> List[str]:
        """Generate backup codes for account recovery"""
        codes = []
        # Use a character set that's easy to read and type
        alphabet = string.ascii_uppercase + string.digits
        # Remove confusing characters
        alphabet = alphabet.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
        
        for _ in range(count):
            # Generate 8-character codes in format XXXX-XXXX
            code_parts = []
            for _ in range(2):
                part = ''.join(secrets.choice(alphabet) for _ in range(4))
                code_parts.append(part)
            code = '-'.join(code_parts)
            codes.append(code)
        
        return codes
    
    def hash_backup_codes(self, codes: List[str]) -> str:
        """
        Hash backup codes for storage
        Returns JSON string of hashed codes
        """
        hashed_codes = []
        for code in codes:
            # Remove any formatting
            clean_code = code.replace('-', '').upper()
            hashed = self.encryption_service.hash_value(clean_code)
            hashed_codes.append(hashed)
        
        return json.dumps(hashed_codes)
    
    def verify_backup_code(self, code: str, hashed_codes_json: str) -> Tuple[bool, List[str]]:
        """
        Verify a backup code and remove it if valid
        
        Returns:
            Tuple of (is_valid, remaining_hashed_codes)
        """
        # Clean the input code
        clean_code = code.replace('-', '').upper()
        
        # Parse the hashed codes
        try:
            hashed_codes = json.loads(hashed_codes_json)
        except (json.JSONDecodeError, TypeError):
            return False, []
        
        # Check each hashed code
        remaining_codes = []
        code_found = False
        
        for hashed_code in hashed_codes:
            if not code_found and self.encryption_service.verify_hash(clean_code, hashed_code):
                code_found = True
                # Don't add this code to remaining (it's been used)
            else:
                remaining_codes.append(hashed_code)
        
        return code_found, remaining_codes
    
    def encrypt_secret(self, secret: str) -> bytes:
        """Encrypt MFA secret for storage"""
        return self.encryption_service.encrypt(secret)
    
    def decrypt_secret(self, encrypted_secret: bytes) -> str:
        """Decrypt MFA secret for use"""
        return self.encryption_service.decrypt(encrypted_secret)
