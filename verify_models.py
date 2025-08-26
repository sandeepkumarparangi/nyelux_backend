#!/usr/bin/env python
"""
Fix and verify all database model relationships.
Run this to ensure all models are properly configured.
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def fix_and_verify_models():
    """Fix and verify all model relationships."""
    
    print("🔧 Verifying database models...")
    
    try:
        # Import all models - this will trigger relationship configuration
        from src.db.models import (
            Base, User, Organization, Department,
            GUDIDDevice, VendorDevice,
            ChatConversation, ChatMessage, ChatCitation,
            DeviceDocument, DeviceVideo,
            DeviceIncident, IncidentAttachment, IncidentComment,
            SupportConversation, SupportMessage,
            CalendarEvent, EventAttendee,
            Notification, NotificationDelivery,
            Team, TeamMember, Note,
            # All other models are imported in __init__
        )
        
        # Force SQLAlchemy to configure all mappers
        from sqlalchemy.orm import configure_mappers
        configure_mappers()
        
        print("✅ All models configured successfully!")
        
        # Verify critical relationships
        print("\n🔍 Verifying critical relationships...")
        
        # Check VendorDevice relationships
        vendor_device_rels = VendorDevice.__mapper__.relationships.keys()
        required_vendor_rels = ['chat_conversations', 'incidents', 'support_conversations', 'videos']
        for rel in required_vendor_rels:
            if rel in vendor_device_rels:
                print(f"  ✅ VendorDevice.{rel}")
            else:
                print(f"  ❌ VendorDevice.{rel} - MISSING!")
                return False
        
        # Check ChatConversation relationships
        chat_rels = ChatConversation.__mapper__.relationships.keys()
        required_chat_rels = ['user', 'device', 'messages']
        for rel in required_chat_rels:
            if rel in chat_rels:
                print(f"  ✅ ChatConversation.{rel}")
            else:
                print(f"  ❌ ChatConversation.{rel} - MISSING!")
                return False
        
        # Check User relationships
        user_rels = User.__mapper__.relationships.keys()
        required_user_rels = ['chat_conversations', 'organization', 'department']
        for rel in required_user_rels:
            if rel in user_rels:
                print(f"  ✅ User.{rel}")
            else:
                print(f"  ❌ User.{rel} - MISSING!")
                return False
        
        print("\n✅ All critical relationships verified!")
        
        # Test that we can create tables (in-memory test)
        print("\n🗄️ Testing table creation...")
        from sqlalchemy import create_engine
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        print("✅ All tables created successfully!")
        
        print("\n🎉 SUCCESS: All models are properly configured and ready to use!")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = fix_and_verify_models()
    sys.exit(0 if success else 1)
