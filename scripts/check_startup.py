#!/usr/bin/env python3
"""
Startup checker script that provides clear guidance on fixing issues.
NO FAKE FIXES - Only real solutions.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.startup import StartupChecker
from src.core.config import settings


async def main():
    """Run startup checks and provide actionable feedback."""
    print("=" * 60)
    print("NYELUX BACKEND STARTUP CHECK")
    print("=" * 60)
    print()
    
    # Run all checks
    results = await StartupChecker.run_all_checks()
    
    # Determine what's required
    required_services = {
        "PostgreSQL": True,  # Always required
        "Redis": True,       # Always required
        "OpenAI": settings.FEATURE_AI_CHAT and bool(settings.OPENAI_API_KEY),
        "AWS S3": bool(settings.S3_BUCKET_NAME),
    }
    
    all_passed = True
    has_errors = False
    
    # Display results
    for service, (passed, message) in results.items():
        is_required = required_services.get(service, False)
        
        if passed:
            print(f"✅ {service}: {message}")
        else:
            if is_required:
                print(f"❌ {service}: {message} [REQUIRED]")
                all_passed = False
                has_errors = True
            else:
                print(f"⚠️  {service}: {message} [OPTIONAL]")
    
    print()
    print("-" * 60)
    
    if not all_passed:
        print("❌ STARTUP FAILED - Required services are not available")
        print()
        print("TO FIX THESE ISSUES:")
        print()
        
        # PostgreSQL issues
        if not results["PostgreSQL"][0]:
            print("1. PostgreSQL:")
            print("   - Make sure PostgreSQL is installed and running")
            print("   - Check your DATABASE_URL in .env")
            print("   - Create the database: createdb nyelux_development")
            print("   - Run migrations: alembic upgrade head")
            print()
        
        # Redis issues
        if not results["Redis"][0]:
            print("2. Redis:")
            print("   - Install Redis: brew install redis (macOS) or apt install redis-server (Ubuntu)")
            print("   - Start Redis: redis-server")
            print("   - Check your REDIS_URL in .env")
            print()
        
        # OpenAI issues
        if required_services["OpenAI"] and not results["OpenAI"][0]:
            print("3. OpenAI:")
            print("   - Get API key from: https://platform.openai.com/api-keys")
            print("   - Add to .env: OPENAI_API_KEY=sk-...")
            print("   - Check model access at: https://platform.openai.com/account/limits")
            print("   - Valid models: gpt-3.5-turbo, gpt-4-turbo (if you have access)")
            print("   - Current model in config:", settings.OPENAI_MODEL)
            if "model_not_found" in results["OpenAI"][1]:
                print("   ⚠️  Your API key doesn't have access to the configured model!")
                print("   ⚠️  Either change OPENAI_MODEL to gpt-3.5-turbo or upgrade your API access")
            print()
        
        # S3 issues
        if required_services["AWS S3"] and not results["AWS S3"][0]:
            print("4. AWS S3:")
            print("   - Create an AWS account and get credentials")
            print("   - Create S3 bucket: nyelux-development")
            print("   - Add to .env:")
            print("     AWS_ACCESS_KEY_ID=...")
            print("     AWS_SECRET_ACCESS_KEY=...")
            print("     S3_BUCKET_NAME=nyelux-development")
            print()
        
        print("REMEMBER: NO FAKE SERVICES OR WORKAROUNDS!")
        print("Fix these issues before starting the application.")
        
    else:
        print("✅ ALL CHECKS PASSED - Ready to start!")
        print()
        print("Start the application with:")
        print("  uvicorn src.main:app --reload")
    
    print()
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
