"""
Startup checks for external services.
Ensures all required services are available before starting.
"""
import asyncio
import logging
from typing import Dict, Tuple

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
# Import these conditionally in the check methods

from src.core.config import settings
from src.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class StartupChecker:
    """Check external service availability on startup."""
    
    @staticmethod
    async def check_database() -> Tuple[bool, str]:
        """Check PostgreSQL connection."""
        try:
            engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                await conn.commit()
            await engine.dispose()
            
            # Also validate models
            from src.db.validate_models import validate_models
            validate_models()
            
            return True, "Connected and models validated"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    async def check_redis() -> Tuple[bool, str]:
        """Check Redis connection."""
        try:
            r = redis.from_url(settings.REDIS_URL)
            await r.ping()
            await r.close()
            return True, "Connected"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    async def check_s3() -> Tuple[bool, str]:
        """Check S3 bucket access."""
        if not settings.AWS_ACCESS_KEY_ID:
            return False, "AWS credentials not configured"
        
        try:
            import boto3
            s3 = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            return True, f"Bucket '{settings.S3_BUCKET_NAME}' accessible"
        except ImportError:
            return False, "boto3 not installed"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    async def check_openai() -> Tuple[bool, str]:
        """Check OpenAI API."""
        if not settings.OPENAI_API_KEY:
            return False, "OpenAI API key not configured"
        
        try:
            from openai import AsyncOpenAI
            
            # Create client with API key
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            # Test with a minimal request
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            return True, "API accessible"
        except Exception as e:
            return False, str(e)
    
    @classmethod
    async def run_all_checks(cls) -> Dict[str, Tuple[bool, str]]:
        """Run all startup checks."""
        # In test mode, only check essential services
        if settings.is_testing():
            checks = {
                "PostgreSQL": cls.check_database(),
                "Redis": cls.check_redis(),
            }
        else:
            checks = {
                "PostgreSQL": cls.check_database(),
                "Redis": cls.check_redis(),
                "AWS S3": cls.check_s3(),
                "OpenAI": cls.check_openai(),
            }
        
        results = {}
        for service, check_coro in checks.items():
            try:
                results[service] = await check_coro
            except Exception as e:
                results[service] = (False, f"Check failed: {str(e)}")
        
        return results
    
    @classmethod
    async def verify_startup(cls) -> bool:
        """
        Verify all required services are available.
        Returns True if all required services pass.
        """
        logger.info("Running startup checks...")
        results = await cls.run_all_checks()
        
        # Only PostgreSQL and Redis are truly required
        # Everything else is optional based on configuration
        required_services = ["PostgreSQL", "Redis"]
        optional_services = ["AWS S3", "OpenAI"]
        
        required_passed = True
        
        for service, (passed, message) in results.items():
            if passed:
                logger.info(f"✅ {service}: {message}")
            else:
                if service in required_services:
                    logger.error(f"❌ {service}: {message}")
                    required_passed = False
                elif service in optional_services:
                    # Optional services - just warn
                    logger.warning(f"⚠️  {service}: {message} (optional)")
                else:
                    # Unknown service
                    logger.warning(f"⚠️  {service}: {message}")
        
        if not required_passed:
            logger.error("Required services are not available. Cannot start.")
        else:
            logger.info("All required services are available. Starting application...")
            
        return required_passed


# Run checks if called directly
if __name__ == "__main__":
    async def main():
        checker = StartupChecker()
        results = await checker.run_all_checks()
        
        print("\nStartup Check Results:")
        print("-" * 50)
        for service, (passed, message) in results.items():
            status = "✅" if passed else "❌"
            print(f"{status} {service}: {message}")
        print("-" * 50)
        
        all_passed = await checker.verify_startup()
        print(f"\nOverall: {'✅ Ready to start' if all_passed else '❌ Not ready'}")
    
    asyncio.run(main())
