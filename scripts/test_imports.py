#!/usr/bin/env python3
"""Quick test to see what's failing"""
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Python path:", sys.path[0])
print("Current directory:", os.getcwd())

# Test imports one by one
try:
    from src.services.encryption_service import EncryptionService
    print("✓ EncryptionService imported successfully")
except Exception as e:
    print(f"✗ EncryptionService import failed: {e}")

try:
    from src.services.mfa_service import MFAService
    print("✓ MFAService imported successfully")
except Exception as e:
    print(f"✗ MFAService import failed: {e}")

try:
    from src.services.email_service import EmailService
    print("✓ EmailService imported successfully")
except Exception as e:
    print(f"✗ EmailService import failed: {e}")

try:
    from src.services.auth_service import AuthService
    print("✓ AuthService imported successfully")
except Exception as e:
    print(f"✗ AuthService import failed: {e}")

print("\nTrying to start the app...")
try:
    from src.main import app
    print("✓ App imported successfully")
except Exception as e:
    print(f"✗ App import failed: {e}")
    import traceback
    traceback.print_exc()
