#!/usr/bin/env python3
"""
Production-grade dependency fix for Nyelux backend
Removes Supabase issues and ensures all dependencies are compatible
"""

import subprocess
import sys
import os

def run_command(cmd, description):
    """Run command with error handling"""
    print(f"\n🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Error: {result.stderr}")
            return False
        print(f"✅ {description} completed")
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def main():
    print("=" * 60)
    print("NYELUX BACKEND - PRODUCTION DEPENDENCY FIX")
    print("=" * 60)
    
    # Step 1: Uninstall problematic packages
    print("\n📦 Step 1: Removing problematic packages...")
    packages_to_remove = [
        "supabase",
        "realtime",
        "websockets",  # Will reinstall correct version
    ]
    
    for package in packages_to_remove:
        run_command(f"pip uninstall -y {package}", f"Removing {package}")
    
    # Step 2: Create fixed requirements file
    print("\n📝 Step 2: Creating fixed requirements file...")
    
    fixed_requirements = """# Core Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
python-multipart==0.0.6

# Database
sqlalchemy==2.0.23
asyncpg==0.29.0
alembic==1.13.0
psycopg2-binary==2.9.9
pgvector==0.2.4

# Redis Cache
redis==5.0.1

# Authentication
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-oauth2==1.1.1
pysaml2==7.4.1

# AI/ML
openai==1.6.0
langchain==0.1.0
chromadb==0.4.22
sentence-transformers==2.3.1
tiktoken==0.5.2

# File Processing
pypdf2==3.0.1
pillow==10.1.0
python-magic==0.4.27
openpyxl==3.1.2
python-docx==1.1.0

# Cloud Services
boto3==1.34.0

# Communication
httpx==0.25.2
python-socketio==5.10.0
sendgrid==6.11.0
twilio==8.11.0

# WebSocket - FIXED VERSION
websockets==12.0

# Search
elasticsearch==8.11.0

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0

# Development
black==23.12.0
flake8==6.1.0
mypy==1.7.1
pre-commit==3.6.0

# Utilities
python-dateutil==2.8.2
pytz==2023.3
pycron==3.0.0
pyyaml==6.0.1
"""
    
    with open("requirements_fixed.txt", "w") as f:
        f.write(fixed_requirements)
    print("✅ Fixed requirements file created")
    
    # Step 3: Install fixed requirements
    print("\n📥 Step 3: Installing fixed dependencies...")
    if not run_command("pip install -r requirements_fixed.txt", "Installing dependencies"):
        print("⚠️  Some dependencies failed to install, continuing...")
    
    # Step 4: Verify imports
    print("\n🔍 Step 4: Verifying critical imports...")
    
    test_imports = """
import fastapi
import sqlalchemy
import redis
import openai
import asyncpg
print("✅ All critical imports successful")
"""
    
    result = subprocess.run([sys.executable, "-c", test_imports], capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ Import verification passed")
    else:
        print(f"⚠️  Import issues: {result.stderr}")
    
    print("\n" + "=" * 60)
    print("✅ DEPENDENCY FIX COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Remove any Supabase imports from your code")
    print("2. Use PostgreSQL directly for FDA data")
    print("3. Restart your application")

if __name__ == "__main__":
    main()
