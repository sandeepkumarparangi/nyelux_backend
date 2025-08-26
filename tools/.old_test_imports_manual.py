#!/usr/bin/env python3
"""Quick test script to check for import errors"""
import sys

print("Testing imports...")

try:
    from src.main import app
    print("✓ Main app imports successfully")
except Exception as e:
    print(f"✗ Error importing main app: {e}")
    sys.exit(1)

try:
    from src.db import base
    print("✓ Database models import successfully")
except Exception as e:
    print(f"✗ Error importing database models: {e}")
    sys.exit(1)

try:
    from src.db.models.notification_delivery import NotificationDelivery
    from src.db.models.notification_preferences import NotificationPreferences
    print("✓ Notification models import without conflict")
except Exception as e:
    print(f"✗ Error with notification models: {e}")
    sys.exit(1)

print("\nAll imports successful! Ready to run tests.")
