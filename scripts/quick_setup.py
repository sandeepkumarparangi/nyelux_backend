#!/usr/bin/env python
"""
Quick setup script for Nyelux Backend
Helps configure external services step by step
"""
import os
import sys
import subprocess
from pathlib import Path


def print_header(text):
    print(f"\n{'=' * 50}")
    print(f"🚀 {text}")
    print('=' * 50)


def check_command(command):
    """Check if a command exists"""
    try:
        subprocess.run([command, "--version"], capture_output=True, check=True)
        return True
    except:
        return False


def main():
    print_header("Nyelux Backend Setup Assistant")
    
    # Check for .env file
    env_path = Path(".env")
    if not env_path.exists():
        print("\n📋 Creating .env file from example...")
        if Path(".env.example").exists():
            env_path.write_text(Path(".env.example").read_text())
            print("✅ Created .env file")
        else:
            print("❌ .env.example not found!")
            return
    else:
        print("✅ .env file exists")
    
    # Check prerequisites
    print_header("Checking Prerequisites")
    
    # PostgreSQL
    if check_command("psql"):
        print("✅ PostgreSQL is installed")
        print("   → To create database: createdb nyelux_development")
    else:
        print("❌ PostgreSQL not found")
        print("   → Install: brew install postgresql (macOS)")
        print("   → Install: sudo apt install postgresql (Ubuntu)")
    
    # Redis
    if check_command("redis-cli"):
        print("✅ Redis is installed")
        # Check if running
        try:
            result = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True)
            if result.stdout.strip() == "PONG":
                print("   → Redis is running")
            else:
                print("   → Start Redis: redis-server")
        except:
            print("   → Start Redis: redis-server")
    else:
        print("❌ Redis not found")
        print("   → Install: brew install redis (macOS)")
        print("   → Install: sudo apt install redis-server (Ubuntu)")
    
    # Python packages
    print("\n📦 Installing Python dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    
    # Service configuration
    print_header("Service Configuration Guide")
    
    print("\n1️⃣  OpenAI API (AI Features)")
    print("   → Get API key: https://platform.openai.com/api-keys")
    print("   → Add to .env: OPENAI_API_KEY=sk-...")
    
    print("\n2️⃣  AWS S3 (File Storage)")
    print("   → Create AWS account: https://aws.amazon.com")
    print("   → Create IAM user with S3 access")
    print("   → Add to .env: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    print("   → OR use MinIO locally: brew install minio")
    
    print("\n3️⃣  SendGrid (Email)")
    print("   → Sign up: https://sendgrid.com")
    print("   → Create API key: https://app.sendgrid.com/settings/api_keys")
    print("   → Add to .env: SENDGRID_API_KEY=SG...")
    
    print("\n4️⃣  Elasticsearch (Advanced Search) - Optional")
    print("   → Run with Docker: docker run -d -p 9200:9200 elasticsearch:8.11.0")
    print("   → Add to .env: ELASTICSEARCH_URL=http://localhost:9200")
    
    # Database setup
    print_header("Database Setup")
    print("Run these commands to set up the database:")
    print("\n# Create database")
    print("createdb nyelux_development")
    print("\n# Run migrations")
    print("alembic upgrade head")
    print("\n# Test configuration")
    print("python scripts/test_services.py")
    print("\n# Start the server")
    print("python run.py")
    
    print("\n✅ Setup guide complete!")
    print("📚 For detailed instructions, see SETUP_GUIDE.md")


if __name__ == "__main__":
    main()
