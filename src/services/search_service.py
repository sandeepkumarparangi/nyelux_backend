"""
Optimized search service for GUDID devices - OPTIONAL SUPABASE VERSION
Works with or without Supabase connection
"""
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter

import redis.asyncio as redis

from src.core.config import settings

logger = logging.getLogger(__name__)

# Try to initialize Supabase, but make it optional
supabase_client = None
try:
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        import os
        # Disable proxy to avoid the error
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        
        from supabase import create_client, Client
        try:
            from supabase._sync.client import SyncClient
            from supabase.lib.client_options import ClientOptions
            
            options = ClientOptions()
            supabase_client = SyncClient.create(
                supabase_url=settings.SUPABASE_URL,
                supabase_key=settings.SUPABASE_SERVICE_KEY,
                options=options
            )
            logger.info("Search service: Supabase client initialized")
        except Exception as e:
            logger.warning(f"Search service: Could not initialize Supabase: {e}")
except Exception as e:
    logger.warning(f"Search service: Supabase not available: {e}")


class SearchRanker:
    """
    Intelligent search ranking system for medical devices
    """
    
    @staticmethod
    def calculate_relevance_score(
        device: Dict[str, Any],
        query: str,
        match_field: str
    ) -> float:
        """
        Calculate relevance score for a device based on query match
        """
        query_lower = query.lower()
        score = 0.0
        
        # Base score by match field
        field_scores = {
            'device_name': 1.0,
            'manufacturer_name': 0.9,
            'brand_name': 0.85,
            'model_number': 0.8,
            'gmdn_terms': 0.7,
        }
        score = field_scores.get(match_field, 0.5)
        
        # Boost for exact match
        field_value = str(device.get(match_field, '')).lower()
        if field_value == query_lower:
            score *= 2.0
        # Boost for starts with
        elif field_value.startswith(query_lower):
            score *= 1.5
        # Boost for word boundary match
        elif re.search(r'\b' + re.escape(query_lower), field_value):
            score *= 1.2
        
        # Boost for popular manufacturers
        popular_manufacturers = [
            'medtronic', 'abbott', 'boston scientific', 'johnson & johnson',
            'stryker', 'ge healthcare', 'siemens', 'philips'
        ]
        manufacturer = str(device.get('manufacturer_name', '')).lower()
        if any(mfr in manufacturer for mfr in popular_manufacturers):
            score *= 1.1
        
        # Boost for Class II and III devices (more regulated)
        device_class = device.get('device_class', '')
        if device_class in ['II', 'III']:
            score *= 1.05
        
        # Penalize if no description
        if not device.get('device_description'):
            score *= 0.95
        
        return min(score, 1.0)  # Cap at 1.0


class OptimizedSearchService:
    """
    Production-optimized search service that works with or without Supabase
    """
    
    def __init__(self):
        """Initialize with optional Supabase connection"""
        self.supabase = supabase_client
        if not self.supabase:
            logger.warning("Search service running without Supabase - using mock data")
        
        self.ranker = SearchRanker()
        self.redis_client = None
        self._init_redis()
        
        # Cache configuration
        self.cache_ttl = {
            'hot': 300,      # 5 minutes for hot queries
            'warm': 1800,    # 30 minutes for warm queries
            'cold': 3600,    # 1 hour for cold queries
        }
        
        # Track query frequency for intelligent caching
        self.query_counter = Counter()
        
        logger.info("Search service initialized")
    
    def _init_redis(self):
        """Initialize Redis connection if available"""
        try:
            if settings.REDIS_URL:
                self.redis_client = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                logger.info("Redis cache enabled for search")
        except Exception as e:
            logger.warning(f"Redis not available for caching: {e}")
            self.redis_client = None
    
    async def _get_cache_tier(self, query: str) -> str:
        """Determine cache tier based on query frequency"""
        count = self.query_counter[query.lower()]
        if count > 10:
            return 'hot'
        elif count > 3:
            return 'warm'
        else:
            return 'cold'
    
    async def _get_cached_result(self, cache_key: str) -> Optional[Dict]:
        """Get cached result if available"""
        if not self.redis_client:
            return None
        
        try:
            cached = await self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.debug(f"Cache get failed (non-critical): {e}")
        
        return None
    
    async def _set_cached_result(
        self, 
        cache_key: str, 
        data: Dict, 
        ttl: int
    ):
        """Cache result with appropriate TTL"""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(data, default=str)
            )
        except Exception as e:
            logger.debug(f"Cache set failed (non-critical): {e}")
    
    def _get_mock_devices(self, query: str, limit: int) -> List[Dict]:
        """Return mock devices when Supabase is not available"""
        mock_devices = [
            {
                'primary_di': '00889842001234',
                'device_name': 'Infusion Pump Model X200',
                'manufacturer_name': 'Medtronic',
                'brand_name': 'MiniMed',
                'model_number': 'X200',
                'device_class': 'II',
                'device_description': 'Programmable infusion pump',
                'gmdn_terms': 'Infusion pump',
                'mri_safety': 'MR Conditional',
                'sterile': False,
                'single_use': False,
                'life_supporting': True
            },
            {
                'primary_di': '00889842001235',
                'device_name': 'Cardiac Monitor Pro',
                'manufacturer_name': 'Abbott',
                'brand_name': 'CardioView',
                'model_number': 'CM-500',
                'device_class': 'II',
                'device_description': 'Multi-parameter cardiac monitoring',
                'gmdn_terms': 'Cardiac monitor',
                'mri_safety': 'MR Unsafe',
                'sterile': False,
                'single_use': False,
                'life_supporting': True
            }
        ]
        
        # Filter by query
        query_lower = query.lower()
        filtered = []
        for device in mock_devices:
            if (query_lower in device.get('device_name', '').lower() or
                query_lower in device.get('manufacturer_name', '').lower() or
                query_lower in device.get('brand_name', '').lower()):
                filtered.append(device)
        
        return filtered[:limit]
    
    async def advanced_search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Advanced search with intelligent ranking and caching
        Works with or without Supabase
        """
        start_time = datetime.utcnow()
        
        # Track query frequency
        self.query_counter[query.lower()] += 1
        
        # Check cache
        cache_key = f"search:v3:{hashlib.md5(f'{query}:{limit}:{filters}'.encode()).hexdigest()}"
        cached_result = await self._get_cached_result(cache_key)
        if cached_result:
            cached_result['cached'] = True
            cached_result['response_time_ms'] = (datetime.utcnow() - start_time).total_seconds() * 1000
            return cached_result
        
        # Get devices (from Supabase or mock)
        if self.supabase:
            try:
                # Prepare search patterns
                query_clean = query.strip()
                search_pattern = f"{query_clean}%"
                
                # Query Supabase
                query_builder = self.supabase.table('gudid_devices').select(
                    'primary_di, device_name, manufacturer_name, brand_name, '
                    'model_number, device_class, device_description, gmdn_terms, '
                    'mri_safety, sterile, single_use, life_supporting'
                )
                
                # Add search conditions
                query_builder = query_builder.or_(
                    f"device_name.ilike.{search_pattern},"
                    f"manufacturer_name.ilike.{search_pattern},"
                    f"brand_name.ilike.{search_pattern},"
                    f"model_number.ilike.{search_pattern},"
                    f"gmdn_terms.ilike.{search_pattern}"
                )
                
                # Apply filters if provided
                if filters:
                    if filters.get('device_class'):
                        query_builder = query_builder.eq('device_class', filters['device_class'])
                    if filters.get('mri_safety'):
                        query_builder = query_builder.eq('mri_safety', filters['mri_safety'])
                    if filters.get('sterile') is not None:
                        query_builder = query_builder.eq('sterile', filters['sterile'])
                
                # Execute query
                response = query_builder.limit(limit * 3).execute()
                devices = response.data if response.data else []
            except Exception as e:
                logger.error(f"Supabase search error: {e}")
                devices = self._get_mock_devices(query, limit)
        else:
            # Use mock devices
            devices = self._get_mock_devices(query, limit)
        
        # Rank and process results
        ranked_results = await self._rank_results(devices, query, limit)
        
        # Prepare response
        result = {
            'query': query,
            'results': ranked_results,
            'total_found': len(ranked_results),
            'filters_applied': filters or {},
            'response_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000,
            'cached': False,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Cache based on query frequency
        cache_tier = await self._get_cache_tier(query)
        ttl = self.cache_ttl[cache_tier]
        await self._set_cached_result(cache_key, result, ttl)
        
        return result
    
    async def _rank_results(
        self,
        raw_results: List[Dict],
        query: str,
        limit: int
    ) -> List[Dict]:
        """
        Rank search results intelligently
        """
        ranked = []
        seen_ids = set()
        
        for device in raw_results:
            # Skip duplicates
            if device['primary_di'] in seen_ids:
                continue
            seen_ids.add(device['primary_di'])
            
            # Determine which field matched
            query_lower = query.lower()
            match_field = 'other'
            
            if device.get('device_name') and query_lower in str(device['device_name']).lower():
                match_field = 'device_name'
            elif device.get('manufacturer_name') and query_lower in str(device['manufacturer_name']).lower():
                match_field = 'manufacturer_name'
            elif device.get('brand_name') and query_lower in str(device['brand_name']).lower():
                match_field = 'brand_name'
            elif device.get('model_number') and query_lower in str(device['model_number']).lower():
                match_field = 'model_number'
            elif device.get('gmdn_terms') and query_lower in str(device['gmdn_terms']).lower():
                match_field = 'gmdn_terms'
            
            # Calculate relevance score
            score = self.ranker.calculate_relevance_score(
                device,
                query,
                match_field
            )
            
            # Format result
            formatted = {
                'id': device['primary_di'],
                'device_name': device.get('device_name') or 'Unknown Device',
                'manufacturer': device.get('manufacturer_name') or 'Unknown',
                'brand': device.get('brand_name'),
                'model': device.get('model_number'),
                'class': device.get('device_class'),
                'description': (device.get('device_description') or '')[:200],
                'gmdn_terms': device.get('gmdn_terms'),
                'mri_safety': device.get('mri_safety'),
                'sterile': device.get('sterile'),
                'single_use': device.get('single_use'),
                'life_supporting': device.get('life_supporting'),
                'match_field': match_field,
                'relevance_score': score
            }
            
            ranked.append(formatted)
        
        # Sort by relevance score
        ranked.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return ranked[:limit]
    
    async def get_popular_searches(self, limit: int = 10) -> List[Dict]:
        """Get most popular search queries"""
        top_queries = self.query_counter.most_common(limit)
        
        return [
            {
                'query': query,
                'count': count,
                'cache_tier': 'hot' if count > 10 else 'warm' if count > 3 else 'cold'
            }
            for query, count in top_queries
        ]
    
    async def get_search_analytics(self) -> Dict:
        """Get search analytics and performance metrics"""
        return {
            'total_unique_queries': len(self.query_counter),
            'total_searches': sum(self.query_counter.values()),
            'top_queries': await self.get_popular_searches(10),
            'cache_stats': {
                'redis_available': self.redis_client is not None,
                'hot_cache_ttl': self.cache_ttl['hot'],
                'warm_cache_ttl': self.cache_ttl['warm'],
                'cold_cache_ttl': self.cache_ttl['cold'],
            },
            'supabase_available': self.supabase is not None
        }


# Global instance - will work with or without Supabase
try:
    search_service = OptimizedSearchService()
except Exception as e:
    logger.error(f"Failed to initialize search service: {e}")
    search_service = None
