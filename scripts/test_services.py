#!/usr/bin/env python
"""
Test all external service configurations
Run this to ensure everything is properly set up
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings


async def test_services():
    print("🔍 Testing External Services Configuration")
    print("=" * 50)
    
    results = {
        "PostgreSQL": False,
        "Redis": False,
        "OpenAI": False,
        "S3": False,
        "Email": False,
        "Elasticsearch": False,
    }
    
    # Test Database
    print("\n1. Testing PostgreSQL...")
    try:
        from src.db.session import engine
        from sqlalchemy import text
        
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"   ✅ Connected - {version}")
            results["PostgreSQL"] = True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Test Redis
    print("\n2. Testing Redis...")
    try:
        from src.core.redis_manager import RedisManager
        redis = RedisManager()
        if await redis.health_check():
            # Test set/get
            await redis.set("test_key", "test_value", expire=10)
            value = await redis.get("test_key")
            if value == "test_value":
                print("   ✅ Connected and working")
                results["Redis"] = True
            else:
                print("   ⚠️  Connected but set/get failed")
        else:
            print("   ❌ Not connected")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Test OpenAI
    print("\n3. Testing OpenAI API...")
    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "sk-...your-openai-api-key-here":
        try:
            import openai
            openai.api_key = settings.OPENAI_API_KEY
            
            # Test with a minimal request
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",  # Use 3.5 for testing (cheaper)
                messages=[{"role": "user", "content": "Say 'test'"}],
                max_tokens=5
            )
            print(f"   ✅ Connected - Response: {response.choices[0].message.content}")
            results["OpenAI"] = True
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            if "invalid_api_key" in str(e):
                print("      → API key is invalid")
            elif "quota" in str(e):
                print("      → API quota exceeded")
    else:
        print("   ⚠️  Not configured (add OPENAI_API_KEY to .env)")
    
    # Test S3
    print("\n4. Testing S3/Storage...")
    if settings.has_s3_configured():
        try:
            from src.services.s3_service import get_s3_service
            s3 = get_s3_service()
            
            # Test by listing buckets (lightweight operation)
            if s3.s3_client:
                response = s3.s3_client.list_buckets()
                print(f"   ✅ Connected - Found {len(response.get('Buckets', []))} buckets")
                results["S3"] = True
            else:
                print("   ❌ S3 client not initialized")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            if "InvalidAccessKeyId" in str(e):
                print("      → Invalid AWS access key")
            elif "SignatureDoesNotMatch" in str(e):
                print("      → Invalid AWS secret key")
    else:
        print("   ⚠️  Not configured (add AWS credentials to .env)")
    
    # Test Email
    print("\n5. Testing Email Service...")
    if settings.SENDGRID_API_KEY and settings.SENDGRID_API_KEY != "SG.your-sendgrid-api-key-here":
        try:
            from src.services.email_wrapper import email_wrapper
            if email_wrapper.is_available():
                print("   ✅ SendGrid configured")
                results["Email"] = True
                # Note: Not sending actual email to avoid spam
            else:
                print("   ❌ Email service not available")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    elif settings.SMTP_HOST:
        print("   ✅ SMTP configured")
        results["Email"] = True
    else:
        print("   ⚠️  Not configured (add SENDGRID_API_KEY or SMTP settings to .env)")
    
    # Test Elasticsearch
    print("\n6. Testing Elasticsearch...")
    if settings.ELASTICSEARCH_URL:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{settings.ELASTICSEARCH_URL}/_cluster/health")
                if response.status_code == 200:
                    health = response.json()
                    print(f"   ✅ Connected - Cluster status: {health['status']}")
                    results["Elasticsearch"] = True
                else:
                    print(f"   ❌ Failed: HTTP {response.status_code}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    else:
        print("   ⚠️  Not configured (optional - add ELASTICSEARCH_URL to .env)")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 CONFIGURATION SUMMARY")
    print("=" * 50)
    
    critical_services = ["PostgreSQL", "Redis"]
    optional_services = ["OpenAI", "S3", "Email", "Elasticsearch"]
    
    print("\n🔴 Critical Services (Required):")
    all_critical_ok = True
    for service in critical_services:
        status = "✅ Ready" if results[service] else "❌ Not Ready"
        print(f"   {service}: {status}")
        if not results[service]:
            all_critical_ok = False
    
    print("\n🟡 Optional Services (Recommended):")
    for service in optional_services:
        status = "✅ Ready" if results[service] else "⚠️  Not Configured"
        print(f"   {service}: {status}")
    
    print("\n" + "=" * 50)
    
    if all_critical_ok:
        print("✅ All critical services are ready!")
        print("🚀 You can now run: python run.py")
    else:
        print("❌ Some critical services are not ready.")
        print("Please fix the issues above before running the server.")
        return False
    
    # Feature availability
    print("\n📋 Feature Availability:")
    print(f"   AI Chat: {'✅ Enabled' if results['OpenAI'] else '⚠️  Disabled (no OpenAI)'}")
    print(f"   File Upload: {'✅ Enabled' if results['S3'] else '⚠️  Disabled (no S3)'}")
    print(f"   Email Notifications: {'✅ Enabled' if results['Email'] else '⚠️  Disabled (no email)'}")
    print(f"   Advanced Search: {'✅ Enabled' if results['Elasticsearch'] else '⚠️  Basic search only'}")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_services())
    sys.exit(0 if success else 1)
