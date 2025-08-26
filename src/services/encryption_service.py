"""
Encryption service for sensitive data.

Provides encryption and decryption for sensitive fields like MFA secrets
using Fernet symmetric encryption.
"""
from cryptography.fernet import Fernet
from typing import Optional, List
import base64
import logging

from src.core.config import settings
from src.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Service for encrypting and decrypting sensitive data.
    Uses Fernet symmetric encryption (AES-128 in CBC mode).
    """
    
    def __init__(self, key: Optional[str] = None):
        """
        Initialize encryption service with key.
        
        Args:
            key: Base64 encoded encryption key. If not provided, uses settings.
        """
        if not key:
            key = settings.ENCRYPTION_KEY
            
        if not key:
            raise ExternalServiceError(
                "Encryption", 
                "Encryption key not configured. Please set ENCRYPTION_KEY in environment."
            )
        
        try:
            # Ensure key is properly formatted
            if isinstance(key, str):
                key_bytes = key.encode('utf-8')
            else:
                key_bytes = key
                
            self.cipher = Fernet(key_bytes)
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise ExternalServiceError(
                "Encryption",
                f"Invalid encryption key format: {str(e)}"
            )
    
    def encrypt(self, data: str) -> bytes:
        """
        Encrypt a string value.
        
        Args:
            data: Plain text string to encrypt
            
        Returns:
            Encrypted bytes
        """
        if not data:
            return b''
            
        try:
            return self.cipher.encrypt(data.encode('utf-8'))
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ExternalServiceError("Encryption", f"Failed to encrypt data: {str(e)}")
    
    def decrypt(self, encrypted_data: bytes) -> str:
        """
        Decrypt encrypted data back to string.
        
        Args:
            encrypted_data: Encrypted bytes
            
        Returns:
            Decrypted string
        """
        if not encrypted_data:
            return ''
            
        try:
            return self.cipher.decrypt(encrypted_data).decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ExternalServiceError("Encryption", f"Failed to decrypt data: {str(e)}")
    
    def encrypt_list(self, items: List[str]) -> List[str]:
        """
        Encrypt a list of strings.
        
        Args:
            items: List of plain text strings
            
        Returns:
            List of base64 encoded encrypted strings
        """
        encrypted_items = []
        for item in items:
            encrypted = self.encrypt(item)
            # Convert to base64 for storage
            encrypted_b64 = base64.b64encode(encrypted).decode('utf-8')
            encrypted_items.append(encrypted_b64)
        return encrypted_items
    
    def decrypt_list(self, encrypted_items: List[str]) -> List[str]:
        """
        Decrypt a list of encrypted strings.
        
        Args:
            encrypted_items: List of base64 encoded encrypted strings
            
        Returns:
            List of decrypted strings
        """
        decrypted_items = []
        for item in encrypted_items:
            # Decode from base64
            encrypted = base64.b64decode(item.encode('utf-8'))
            decrypted = self.decrypt(encrypted)
            decrypted_items.append(decrypted)
        return decrypted_items
    
    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.
        
        Returns:
            Base64 encoded encryption key
        """
        return Fernet.generate_key().decode('utf-8')


# Dependency function for FastAPI
def get_encryption_service() -> EncryptionService:
    """
    Get encryption service instance for dependency injection.
    
    Returns:
        EncryptionService instance
        
    Raises:
        ExternalServiceError: If encryption key not configured
    """
    return EncryptionService()


# Utility function to generate a new key (for setup)
def generate_encryption_key():
    """Generate and print a new encryption key for setup."""
    key = EncryptionService.generate_key()
    print(f"Generated encryption key: {key}")
    print("Add this to your .env file as ENCRYPTION_KEY")
    return key
