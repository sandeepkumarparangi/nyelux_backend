#!/usr/bin/env python3
"""Simple test to check if app starts without import errors"""
import os
import sys

# Set test environment
os.environ['ENVIRONMENT'] = 'test'
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:password@localhost:5432/nyelux_test'
os.environ['SECRET_KEY'] = 'test-secret-key'

try:
    print("Importing FastAPI app...")
    from src.main import app
    print("✓ App imported successfully")
    
    print("\nChecking app configuration...")
    print(f"  App title: {app.title}")
    print(f"  App version: {app.version}")
    print(f"  Routes registered: {len(app.routes)}")
    
    print("\nChecking key services...")
    from src.services.notification_service import notification_service
    print("✓ Notification service loaded")
    
    from src.services.auth_service import AuthService
    print("✓ Auth service loaded")
    
    print("\nAll imports successful! Application is ready.")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
