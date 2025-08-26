"""
Security utilities for encryption and decryption.
"""
import base64
import secrets
from typing import Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.core.config import settings


class SecurityManager:
    """Handles field-level encryption and other security operations"""
    
    def __init__(self):
        # Use the secret key from settings to derive encryption key
        self._fernet = self._get_fernet_instance()
    
    def _get_fernet_instance(self) -> Fernet:
        """Create Fernet instance from settings secret key"""
        # Derive a proper encryption key from the secret key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'nyelux-salt-2024',  # In production, use a proper salt
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(
            kdf.derive(settings.SECRET_KEY.encode()[:32].ljust(32, b'0'))
        )
        return Fernet(key)
    
    def encrypt_field(self, value: Union[str, bytes]) -> str:
        """Encrypt a field value"""
        if value is None:
            return None
            
        if isinstance(value, str):
            value = value.encode()
            
        encrypted = self._fernet.encrypt(value)
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt_field(self, encrypted_value: str) -> str:
        """Decrypt a field value"""
        if encrypted_value is None:
            return None
            
        try:
            # Decode from base64
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
            # Decrypt
            decrypted = self._fernet.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception:
            # If decryption fails, return None or raise based on requirements
            return None
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(length)
    
    def hash_password(self, password: str) -> str:
        """Hash a password (placeholder - use passlib in auth service)"""
        # This is just for the interface - actual password hashing
        # should be done by the auth service using passlib
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password (placeholder - use passlib in auth service)"""
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.verify(plain_password, hashed_password)


# Global instance
security_manager = SecurityManager()

# Export functions for backward compatibility
def encrypt_field(value: Union[str, bytes]) -> str:
    """Encrypt a field value"""
    return security_manager.encrypt_field(value)


def decrypt_field(encrypted_value: str) -> str:
    """Decrypt a field value"""
    return security_manager.decrypt_field(encrypted_value)
