#!/usr/bin/env python3
"""Generate a new valid encryption key"""
from cryptography.fernet import Fernet

# Generate a new key
key = Fernet.generate_key()
key_str = key.decode('utf-8')

print("New encryption key generated:")
print("="*60)
print(key_str)
print("="*60)
print("\nAdd this to your .env file:")
print(f'ENCRYPTION_KEY={key_str}')
print("\nThis key is properly formatted for Fernet encryption.")
