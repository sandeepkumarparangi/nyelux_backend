from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
import platform
import psutil
import os
from datetime import datetime

from src.db.session import get_db, db_manager
from src.core.cache import CacheService
from src.core.config import settings

router = APIRouter()

# Create cache service instance
cache_service = CacheService()

@router.get("/", response_model=Dict[str, Any])
async def health_check():
    """
    Basic health check endpoint.
    Returns service status without detailed information.
    """
    return {
        "status": "healthy",
        "service": "Nyelux Medical Device Intelligence API",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/detailed", response_model=Dict[str, Any])
async def detailed_health_check(
    db: AsyncSession = Depends(get_db)
):
    """
    Detailed health check for monitoring.
    Requires authentication in production.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0",
        "checks": {}
    }
    
    # Database check
    try:
        if db_manager:
            db_health = await db_manager.health_check()
            health_status["checks"]["database"] = {
                "status": "healthy" if db_health["primary"] else "unhealthy",
                "message": "Database connection successful" if db_health["primary"] else "Database connection failed",
                "details": db_health
            }
        else:
            health_status["status"] = "unhealthy"
            health_status["checks"]["database"] = {
                "status": "unhealthy",
                "message": "Database manager not initialized"
            }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": str(e)
        }
    
    # Cache check
    try:
        cache_healthy = await cache_service.health_check()
        health_status["checks"]["cache"] = {
            "status": "healthy" if cache_healthy else "degraded",
            "message": "Redis connection successful" if cache_healthy else "Redis unavailable - using degraded mode"
        }
    except Exception as e:
        health_status["checks"]["cache"] = {
            "status": "degraded",
            "message": f"Cache check failed: {str(e)}"
        }
    
    # System resources
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health_status["checks"]["system"] = {
            "status": "healthy",
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "load_average": os.getloadavg() if platform.system() != "Windows" else None
        }
        
        # Warn if resources are high
        if cpu_percent > 80 or memory.percent > 80 or disk.percent > 80:
            health_status["checks"]["system"]["status"] = "warning"
            
    except Exception as e:
        health_status["checks"]["system"] = {
            "status": "unknown",
            "message": f"System check failed: {str(e)}"
        }
    
    # External services check (if configured)
    if settings.OPENAI_API_KEY:
        health_status["checks"]["openai"] = {
            "status": "configured",
            "message": "OpenAI API key present"
        }
    else:
        health_status["checks"]["openai"] = {
            "status": "not_configured",
            "message": "OpenAI API key not configured"
        }
    
    if settings.AWS_ACCESS_KEY_ID:
        health_status["checks"]["aws"] = {
            "status": "configured",
            "message": "AWS credentials present"
        }
    else:
        health_status["checks"]["aws"] = {
            "status": "not_configured",
            "message": "AWS credentials not configured"
        }
    
    # Overall status
    if any(check.get("status") == "unhealthy" for check in health_status["checks"].values()):
        health_status["status"] = "unhealthy"
    elif any(check.get("status") in ["degraded", "warning"] for check in health_status["checks"].values()):
        health_status["status"] = "degraded"
    
    return health_status

@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Kubernetes readiness probe.
    Returns 200 if service is ready to accept traffic.
    """
    try:
        # Check database
        if db_manager:
            db_health = await db_manager.health_check()
            if not db_health["primary"]:
                return {
                    "ready": False,
                    "error": "Database not available"
                }
        else:
            return {
                "ready": False,
                "error": "Database manager not initialized"
            }
        
        # Check cache
        cache_healthy = await cache_service.health_check()
        
        # Service is ready even if cache is down (degraded mode)
        return {"ready": True}
        
    except Exception as e:
        # Not ready if database is down
        return {
            "ready": False,
            "error": str(e)
        }

@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """
    Kubernetes liveness probe.
    Returns 200 if service is alive.
    """
    return {"alive": True}
