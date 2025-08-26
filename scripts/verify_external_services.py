#!/usr/bin/env python
"""
Verify all external services are properly configured and accessible.
Run this before deploying to ensure all integrations work.
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime
from typing import Dict, Any

# Import all services
from src.core.config import settings
from src.db.session import test_database_connection
from src.core.cache import cache_service
from src.services.email_service import email_service
from src.services.s3_service import s3_service
from src.services.ai_service import ai_service
from src.services.search_service import search_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServiceVerifier:
    """Verify external service configurations"""
    
    def __init__(self):
        self.results = {}
    
    async def verify_all(self) -> Dict[str, Any]:
        """Run all verification checks"""
        logger.info("Starting external service verification...")
        logger.info(f"Environment: {settings.ENVIRONMENT}")
        logger.info("-" * 50)
        
        # Database
        await self.verify_database()
        
        # Redis
        await self.verify_redis()
        
        # Elasticsearch
        await self.verify_elasticsearch()
        
        # S3
        await self.verify_s3()
        
        # SendGrid
        await self.verify_sendgrid()
        
        # OpenAI
        await self.verify_openai()
        
        # Twilio (if configured)
        await self.verify_twilio()
        
        # Summary
        self.print_summary()
        
        return self.results
    
    async def verify_database(self):
        """Verify PostgreSQL connection"""
        logger.info("Checking PostgreSQL...")
        try:
            await test_database_connection()
            self.results["postgresql"] = {
                "status": "✅ Connected",
                "url": settings.DATABASE_URL.split("@")[1] if "@" in settings.DATABASE_URL else "local"
            }
        except Exception as e:
            self.results["postgresql"] = {
                "status": "❌ Failed",
                "error": str(e)
            }
    
    async def verify_redis(self):
        """Verify Redis connection"""
        logger.info("Checking Redis...")
        try:
            if await cache_service.health_check():
                # Test set/get
                test_key = f"test_key_{datetime.utcnow().timestamp()}"
                await cache_service.set(test_key, "test_value", expire=60)
                value = await cache_service.get(test_key)
                await cache_service.delete(test_key)
                
                if value == "test_value":
                    self.results["redis"] = {
                        "status": "✅ Connected",
                        "url": settings.REDIS_URL
                    }
                else:
                    self.results["redis"] = {
                        "status": "⚠️  Connected but read/write failed",
                        "url": settings.REDIS_URL
                    }
            else:
                self.results["redis"] = {
                    "status": "❌ Failed",
                    "error": "Health check failed"
                }
        except Exception as e:
            self.results["redis"] = {
                "status": "❌ Failed",
                "error": str(e)
            }
    
    async def verify_elasticsearch(self):
        """Verify Elasticsearch connection"""
        logger.info("Checking Elasticsearch...")
        if not settings.ELASTICSEARCH_URL:
            self.results["elasticsearch"] = {
                "status": "⚠️  Not configured",
                "note": "Search will use PostgreSQL only"
            }
            return
        
        try:
            if search_service.es_client:
                info = await search_service.es_client.info()
                self.results["elasticsearch"] = {
                    "status": "✅ Connected",
                    "version": info["version"]["number"],
                    "cluster": info["cluster_name"]
                }
            else:
                self.results["elasticsearch"] = {
                    "status": "❌ Failed",
                    "error": "Client not initialized"
                }
        except Exception as e:
            self.results["elasticsearch"] = {
                "status": "❌ Failed",
                "error": str(e)
            }
    
    async def verify_s3(self):
        """Verify S3 connection"""
        logger.info("Checking AWS S3...")
        if not settings.AWS_ACCESS_KEY_ID:
            self.results["s3"] = {
                "status": "⚠️  Not configured",
                "note": "File storage will not work"
            }
            return
        
        try:
            if s3_service:
                # Try to list buckets
                response = s3_service.client.list_buckets()
                bucket_names = [b['Name'] for b in response['Buckets']]
                
                self.results["s3"] = {
                    "status": "✅ Connected",
                    "region": settings.AWS_REGION,
                    "bucket": settings.S3_BUCKET_NAME,
                    "bucket_exists": settings.S3_BUCKET_NAME in bucket_names
                }
            else:
                self.results["s3"] = {
                    "status": "❌ Failed",
                    "error": "Service not initialized"
                }
        except Exception as e:
            self.results["s3"] = {
                "status": "❌ Failed",
                "error": str(e)
            }
    
    async def verify_sendgrid(self):
        """Verify SendGrid configuration"""
        logger.info("Checking SendGrid...")
        if not settings.SENDGRID_API_KEY:
            self.results["sendgrid"] = {
                "status": "⚠️  Not configured",
                "note": "Email sending will not work"
            }
            return
        
        try:
            if await email_service.verify_configuration():
                self.results["sendgrid"] = {
                    "status": "✅ Connected",
                    "from_email": "noreply@nyelux.com"
                }
            else:
                self.results["sendgrid"] = {
                    "status": "❌ Failed",
                    "error": "API key validation failed"
                }
        except Exception as e:
            self.results["sendgrid"] = {
                "status": "❌ Failed",
                "error": str(e)
            }
    
    async def verify_openai(self):
        """Verify OpenAI configuration"""
        logger.info("Checking OpenAI...")
        if not settings.OPENAI_API_KEY:
            self.results["openai"] = {
                "status": "⚠️  Not configured",
                "note": "AI features will not work"
            }
            return
        
        try:
            if ai_service:
                # Try a simple embedding
                embedding = await ai_service.get_embedding("test")
                if len(embedding) == 1536:  # Expected dimension
                    self.results["openai"] = {
                        "status": "✅ Connected",
                        "model": ai_service.chat_model,
                        "embedding_model": ai_service.embedding_model
                    }
                else:
                    self.results["openai"] = {
                        "status": "⚠️  Connected but unexpected response",
                        "embedding_dims": len(embedding)
                    }
            else:
                self.results["openai"] = {
                    "status": "❌ Failed",
                    "error": "Service not initialized"
                }
        except Exception as e:
            self.results["openai"] = {
                "status": "❌ Failed",
                "error": str(e)
            }
    
    async def verify_twilio(self):
        """Verify Twilio configuration"""
        logger.info("Checking Twilio...")
        if not settings.TWILIO_ACCOUNT_SID:
            self.results["twilio"] = {
                "status": "⚠️  Not configured",
                "note": "SMS features will not work"
            }
            return
        
        # TODO: Implement Twilio verification
        self.results["twilio"] = {
            "status": "⚠️  Not implemented",
            "note": "Twilio verification not yet implemented"
        }
    
    def print_summary(self):
        """Print verification summary"""
        logger.info("\n" + "=" * 50)
        logger.info("VERIFICATION SUMMARY")
        logger.info("=" * 50)
        
        all_good = True
        critical_services = ["postgresql", "redis", "s3", "sendgrid"]
        
        for service, result in self.results.items():
            logger.info(f"\n{service.upper()}:")
            for key, value in result.items():
                logger.info(f"  {key}: {value}")
            
            if service in critical_services and "❌" in result.get("status", ""):
                all_good = False
        
        logger.info("\n" + "=" * 50)
        
        if all_good:
            logger.info("✅ All critical services are operational!")
        else:
            logger.error("❌ Some critical services are not working!")
            logger.error("Please fix the issues before deploying to production.")


async def main():
    """Run verification"""
    verifier = ServiceVerifier()
    results = await verifier.verify_all()
    
    # Return non-zero exit code if any critical service failed
    critical_services = ["postgresql", "redis", "s3", "sendgrid"]
    for service in critical_services:
        if service in results and "❌" in results[service].get("status", ""):
            return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
