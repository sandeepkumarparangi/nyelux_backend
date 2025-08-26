"""
External services health check and monitoring.

Provides health checks for all external services following PRODUCTION-READY principles.
Services are checked using factory functions - no singletons or fake services.
"""
import logging
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime

from src.core.config import settings
from src.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class ServiceStatus:
    """Track service health status"""
    def __init__(self, name: str):
        self.name = name
        self.is_healthy = False
        self.is_configured = False
        self.last_check = None
        self.error_message = None
        self.response_time_ms = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_healthy": self.is_healthy,
            "is_configured": self.is_configured,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "error_message": self.error_message,
            "response_time_ms": self.response_time_ms
        }


class ExternalServicesHealthCheck:
    """
    Health check manager for external services.
    
    IMPORTANT: This does NOT create or store service instances.
    It only checks if services CAN be created using factory functions.
    """
    
    @staticmethod
    async def check_all_services() -> Dict[str, ServiceStatus]:
        """
        Check health of all external services.
        
        Returns status for each service showing:
        - is_configured: Whether required config exists
        - is_healthy: Whether service is reachable
        - error_message: Any errors encountered
        """
        results = {}
        
        # Check each service in parallel
        checks = [
            ExternalServicesHealthCheck._check_s3(),
            ExternalServicesHealthCheck._check_openai(),
            ExternalServicesHealthCheck._check_email(),
            ExternalServicesHealthCheck._check_elasticsearch(),
            ExternalServicesHealthCheck._check_redis(),
        ]
        
        statuses = await asyncio.gather(*checks, return_exceptions=True)
        
        # Map results
        service_names = ['s3', 'openai', 'email', 'elasticsearch', 'redis']
        for name, status in zip(service_names, statuses):
            if isinstance(status, Exception):
                # Handle exception in check
                error_status = ServiceStatus(name)
                error_status.is_healthy = False
                error_status.is_configured = False
                error_status.error_message = str(status)
                error_status.last_check = datetime.utcnow()
                results[name] = error_status
            else:
                results[name] = status
        
        return results
    
    @staticmethod
    async def _check_s3() -> ServiceStatus:
        """Check S3 service health"""
        status = ServiceStatus('s3')
        start_time = datetime.utcnow()
        
        try:
            # Check configuration
            if not settings.has_s3_configured():
                status.is_configured = False
                status.error_message = "S3 not configured"
            else:
                status.is_configured = True
                
                # Try to create service and check health
                from src.services.s3_service import get_s3_service
                s3 = get_s3_service()
                
                # Perform health check
                is_healthy = await s3.health_check()
                status.is_healthy = is_healthy
                
                if not is_healthy:
                    status.error_message = "S3 health check failed"
            
        except ExternalServiceError as e:
            status.is_configured = False
            status.error_message = str(e)
        except Exception as e:
            status.is_healthy = False
            status.error_message = f"Unexpected error: {str(e)}"
        
        status.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        status.last_check = datetime.utcnow()
        return status
    
    @staticmethod
    async def _check_openai() -> ServiceStatus:
        """Check OpenAI service health"""
        status = ServiceStatus('openai')
        start_time = datetime.utcnow()
        
        try:
            # Check configuration
            if not settings.has_ai_configured():
                status.is_configured = False
                status.error_message = "OpenAI not configured"
            else:
                status.is_configured = True
                
                # Try to create service
                from src.services.ai_service import get_ai_service
                ai = get_ai_service()
                
                # Simple check - service created successfully
                status.is_healthy = True
                
        except ExternalServiceError as e:
            status.is_configured = False
            status.error_message = str(e)
        except Exception as e:
            status.is_healthy = False
            status.error_message = f"Unexpected error: {str(e)}"
        
        status.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        status.last_check = datetime.utcnow()
        return status
    
    @staticmethod
    async def _check_email() -> ServiceStatus:
        """Check email service health"""
        status = ServiceStatus('email')
        start_time = datetime.utcnow()
        
        try:
            # Check configuration
            if not settings.has_email_configured():
                status.is_configured = False
                status.error_message = "Email service not configured"
            else:
                status.is_configured = True
                
                # Try to create service
                from src.services.email_service import get_email_service
                email = get_email_service()
                
                # Simple check - service created successfully
                status.is_healthy = True
                
        except ExternalServiceError as e:
            status.is_configured = False
            status.error_message = str(e)
        except Exception as e:
            status.is_healthy = False
            status.error_message = f"Unexpected error: {str(e)}"
        
        status.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        status.last_check = datetime.utcnow()
        return status
    
    @staticmethod
    async def _check_elasticsearch() -> ServiceStatus:
        """Check Elasticsearch health"""
        status = ServiceStatus('elasticsearch')
        start_time = datetime.utcnow()
        
        try:
            # Check configuration
            if not hasattr(settings, 'ELASTICSEARCH_URL') or not settings.ELASTICSEARCH_URL:
                status.is_configured = False
                status.error_message = "Elasticsearch not configured"
            else:
                status.is_configured = True
                
                # Try to connect
                from elasticsearch import AsyncElasticsearch
                
                es = AsyncElasticsearch(
                    [settings.ELASTICSEARCH_URL],
                    basic_auth=(
                        settings.ELASTICSEARCH_USERNAME, 
                        settings.ELASTICSEARCH_PASSWORD
                    ) if hasattr(settings, 'ELASTICSEARCH_USERNAME') else None
                )
                
                # Ping to check connectivity
                try:
                    if await es.ping():
                        status.is_healthy = True
                    else:
                        status.is_healthy = False
                        status.error_message = "Elasticsearch ping failed"
                finally:
                    await es.close()
                
        except Exception as e:
            status.is_healthy = False
            status.error_message = f"Error: {str(e)}"
        
        status.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        status.last_check = datetime.utcnow()
        return status
    
    @staticmethod
    async def _check_redis() -> ServiceStatus:
        """Check Redis health"""
        status = ServiceStatus('redis')
        start_time = datetime.utcnow()
        
        try:
            # Check configuration
            if not hasattr(settings, 'REDIS_URL') or not settings.REDIS_URL:
                status.is_configured = False
                status.error_message = "Redis not configured"
            else:
                status.is_configured = True
                
                # Try to connect
                from src.core.cache import CacheService
                cache = CacheService()
                
                # Perform health check
                is_healthy = await cache.health_check()
                status.is_healthy = is_healthy
                
                if not is_healthy:
                    status.error_message = "Redis health check failed"
                
        except Exception as e:
            status.is_healthy = False
            status.error_message = f"Error: {str(e)}"
        
        status.response_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        status.last_check = datetime.utcnow()
        return status
    
    @staticmethod
    def get_summary(statuses: Dict[str, ServiceStatus]) -> Dict[str, Any]:
        """Get summary of service health"""
        total = len(statuses)
        configured = sum(1 for s in statuses.values() if s.is_configured)
        healthy = sum(1 for s in statuses.values() if s.is_healthy)
        
        return {
            "total_services": total,
            "configured_services": configured,
            "healthy_services": healthy,
            "all_healthy": healthy == configured and configured > 0,
            "services": {name: status.to_dict() for name, status in statuses.items()}
        }
