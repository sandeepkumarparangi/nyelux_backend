#!/usr/bin/env python
"""
Create S3 buckets for Nyelux.
Ensures all required buckets exist with proper configuration.
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.s3_service import s3_service
from src.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Create S3 buckets"""
    try:
        logger.info("Creating S3 buckets...")
        logger.info(f"AWS Region: {settings.AWS_REGION}")
        logger.info(f"Bucket name: {settings.S3_BUCKET_NAME}")
        
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            logger.error("AWS credentials not configured in environment")
            return 1
        
        if not s3_service:
            logger.error("S3 service not initialized")
            return 1
        
        await s3_service.ensure_buckets_exist()
        logger.info("S3 buckets created/verified successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Failed to create buckets: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
