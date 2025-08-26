#!/usr/bin/env python3
"""
Clear rate limit for a specific IP address
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.cache import CacheService

async def clear_rate_limit():
    """Clear rate limits for testing"""
    cache = CacheService()
    
    # Clear all auth rate limits
    pattern = "auth:*"
    
    try:
        # Get all keys matching pattern
        keys = []
        async for key in cache.redis.scan_iter(match=pattern):
            keys.append(key)
        
        if keys:
            # Delete all matching keys
            await cache.redis.delete(*keys)
            print(f"✅ Cleared {len(keys)} rate limit entries")
        else:
            print("No rate limit entries found")
            
        # Also clear specific IP if needed
        specific_key = "auth:POST:/api/v1/auth/register:127.0.0.1"
        await cache.redis.delete(specific_key)
        print(f"✅ Cleared rate limit for local registration")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await cache.redis.close()

if __name__ == "__main__":
    asyncio.run(clear_rate_limit())
