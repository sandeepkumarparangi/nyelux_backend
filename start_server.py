#!/usr/bin/env python
"""
Simple server startup for development/testing.
Starts the Nyelux backend with minimal checks.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment to bypass strict checks
os.environ["ENVIRONMENT"] = "test"

if __name__ == "__main__":
    print("🚀 Starting Nyelux Backend API...")
    print("📍 API will be available at: http://localhost:8000")
    print("📚 Documentation at: http://localhost:8000/docs")
    print("🔍 Health check at: http://localhost:8000/health")
    print("\nPress Ctrl+C to stop the server\n")
    
    import uvicorn
    
    try:
        uvicorn.run(
            "src.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
