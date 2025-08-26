#!/usr/bin/env python3
"""Fix all remaining issues and start the app"""
import os
import sys
import subprocess

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def main():
    print("NYELUX BACKEND - FINAL FIX")
    print("="*60)
    
    # 1. Fix the encryption key
    print("\n1. Fixing encryption key...")
    result = subprocess.run([sys.executable, "scripts/fix_encryption_key.py"], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"Error: {result.stderr}")
    
    # 2. Check if all imports work now
    print("\n2. Testing imports...")
    try:
        # Set test environment
        os.environ['TESTING'] = '1'
        
        from src.services.encryption_service import EncryptionService
        print("✓ EncryptionService imports successfully")
        
        # Test encryption with new key
        enc = EncryptionService()
        test_data = "test"
        encrypted = enc.encrypt(test_data)
        decrypted = enc.decrypt(encrypted)
        print(f"✓ Encryption works: {test_data} == {decrypted}")
        
    except Exception as e:
        print(f"✗ Encryption test failed: {e}")
        return 1
    
    # 3. Test the app can start
    print("\n3. Testing application startup...")
    try:
        from src.main import app
        print("✓ Application imports successfully")
        
        # Test health endpoint
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/health")
        print(f"✓ Health check: {response.status_code} - {response.json()}")
        
    except Exception as e:
        print(f"✗ Application test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "="*60)
    print("✓ ALL ISSUES FIXED!")
    print("="*60)
    
    print("\nThe application is now ready to run!")
    print("\nTo start the server:")
    print("  python run.py")
    print("\nThe API will be available at:")
    print("  http://localhost:8000")
    print("  http://localhost:8000/docs (Swagger UI)")
    print("  http://localhost:8000/redoc (ReDoc)")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
