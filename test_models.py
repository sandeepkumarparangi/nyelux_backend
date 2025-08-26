#!/usr/bin/env python
"""
Test script to verify all database models and relationships are properly configured.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

# Import all models to trigger relationship configuration
from src.db.models import *
from src.db.base_class import Base
from src.core.config import settings

def test_models():
    """Test that all models and relationships are properly configured."""
    
    print("Testing model configuration...")
    
    # Create a test engine (in-memory SQLite for quick testing)
    engine = create_engine("sqlite:///:memory:")
    
    try:
        # This will fail if there are relationship issues
        Base.metadata.create_all(bind=engine)
        print("✅ All models created successfully!")
        
        # Get all table names
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"\n📊 Created {len(tables)} tables:")
        for table in sorted(tables):
            print(f"  - {table}")
        
        # Test specific relationships
        print("\n🔗 Testing relationships:")
        
        # Check VendorDevice relationships
        vendor_device_mapper = VendorDevice.__mapper__
        relationships = vendor_device_mapper.relationships
        print(f"\nVendorDevice relationships:")
        for rel in relationships:
            print(f"  - {rel.key}: {rel.mapper.class_.__name__}")
        
        # Check ChatConversation relationships  
        chat_mapper = ChatConversation.__mapper__
        relationships = chat_mapper.relationships
        print(f"\nChatConversation relationships:")
        for rel in relationships:
            print(f"  - {rel.key}: {rel.mapper.class_.__name__}")
        
        # Check User relationships
        user_mapper = User.__mapper__
        relationships = user_mapper.relationships
        print(f"\nUser relationships ({len(relationships)} total):")
        for rel in list(relationships)[:5]:  # Show first 5
            print(f"  - {rel.key}: {rel.mapper.class_.__name__}")
        print("  ...")
        
        print("\n✅ All relationship tests passed!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = test_models()
    sys.exit(0 if success else 1)
