#!/usr/bin/env python
"""
Create Elasticsearch indices for Nyelux.
Run this script to initialize Elasticsearch with proper mappings.
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.elasticsearch_init import initialize_elasticsearch_indices
from src.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Create Elasticsearch indices"""
    try:
        logger.info("Creating Elasticsearch indices...")
        logger.info(f"Elasticsearch URL: {settings.ELASTICSEARCH_URL}")
        
        if not settings.ELASTICSEARCH_URL:
            logger.error("ELASTICSEARCH_URL not configured in environment")
            return 1
        
        await initialize_elasticsearch_indices()
        logger.info("Elasticsearch indices created successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Failed to create indices: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
