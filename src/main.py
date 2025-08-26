"""
Main FastAPI application with enhanced database session management.
Production-ready with proper lifecycle management and monitoring.
"""

# CRITICAL: Import httpx patch FIRST before anything else
from src.core.httpx_patch import *  # Fix Supabase proxy issue

from fastapi import FastAPI, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
from typing import Dict, Any
import sys
from sqlalchemy import text

# Add src to Python path
sys.path.append(".")

# Import all models to ensure relationships are configured
import src.db.models  # This imports all models properly

from src.core.config import settings, get_settings, Settings
from src.core.startup import StartupChecker
from src.db import session as db_session
from src.db.session import init_db, close_db, get_db_stats
from src.middleware.rate_limit import RateLimitMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log") if not settings.is_testing() else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Handles startup and shutdown operations.
    """
    # Startup
    logger.info(f"Starting Nyelux Backend - Environment: {settings.ENVIRONMENT}")
    
    # Skip database initialization in test mode - tests handle their own setup
    if settings.is_testing():
        logger.info("Test mode detected - skipping database initialization (handled by test fixtures)")
        yield
        logger.info("Test mode - skipping shutdown procedures")
        return
    
    try:
        # Run startup checks first
        logger.info("Running startup checks...")
        startup_passed = await StartupChecker.verify_startup()
        if not startup_passed:
            logger.error("Startup checks failed. Cannot start application.")
            # FAIL FAST - No fake services, no workarounds
            raise RuntimeError("Required services are not available. Fix the issues before starting.")
        
        # Initialize database with enhanced session management
        logger.info("Initializing database connection pool...")
        await init_db(**settings.get_db_config())
        logger.info("Database initialized successfully")
        
        # Verify external services
        services = settings.validate_external_services()
        logger.info(f"External services status: {services}")
        
        # Warm up connection pool
        if db_session.db_manager:
            logger.info("Warming up database connection pool...")
            for _ in range(min(5, settings.DB_POOL_SIZE)):
                async with db_session.db_manager.get_db_session() as session:
                    await session.execute(text("SELECT 1"))
            logger.info("Connection pool warmed up")
        
        # Log startup metrics
        stats = await get_db_stats()
        logger.info(f"Startup database stats: {stats}")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Nyelux Backend...")
    
    try:
        # Log final metrics
        if db_session.db_manager:
            stats = await get_db_stats()
            logger.info(f"Shutdown database stats: {stats}")
        
        # Close database connections
        await close_db()
        logger.info("Database connections closed")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if not settings.is_production() else None,
    docs_url="/docs" if not settings.is_production() else None,
    redoc_url="/redoc" if not settings.is_production() else None,
    lifespan=lifespan,
)

# Add security middleware
if settings.is_production():
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.nyelux.com", "nyelux.com"]
    )

# Add CORS middleware with enhanced configuration for development
if settings.ENVIRONMENT == "development":
    # In development, allow all localhost origins
    cors_origins = [
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://localhost:4200",
    ]
else:
    # In production, use configured origins
    cors_origins = settings.BACKEND_CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=3600,
)

# Add compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# DEBUG: Add debug middleware for track-search
from src.middleware.debug import debug_track_search_middleware

@app.middleware("http")
async def debug_middleware(request: Request, call_next):
    return await debug_track_search_middleware(request, call_next)


# Custom middleware for request tracking and performance monitoring
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """
    Add request processing time and request ID to headers.
    Also tracks performance metrics.
    """
    start_time = time.time()
    
    # Generate or get request ID
    request_id = request.headers.get("X-Request-ID", f"{time.time()}")
    
    # Process request
    response = await call_next(request)
    
    # Calculate process time
    process_time = time.time() - start_time
    
    # Add headers
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id
    
    # Log slow requests
    if process_time > 1.0:
        logger.warning(
            f"Slow request detected: {request.method} {request.url.path} "
            f"took {process_time:.2f}s"
        )
    
    return response


# Health check endpoints
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
    }


@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check() -> Dict[str, Any]:
    """
    Detailed health check with database and service status.
    Should be protected in production.
    """
    health_status = {
        "status": "checking",
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
        "services": {},
    }
    
    # Check database if initialized
    if db_session.db_manager:
        try:
            db_health = await db_session.db_manager.health_check()
            health_status["services"]["database"] = db_health
        except Exception as e:
            health_status["services"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
    else:
        health_status["services"]["database"] = {
            "status": "not initialized",
            "error": "Database manager not available"
        }
    
    # Check external services configuration
    health_status["services"]["external"] = settings.validate_external_services()
    
    # Determine overall health
    db_healthy = health_status["services"]["database"].get("primary", False)
    health_status["status"] = "healthy" if db_healthy else "unhealthy"
    
    return health_status


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """
    Get application metrics.
    Should be protected and used by monitoring systems.
    """
    if settings.is_production():
        # In production, this should be protected
        return {"error": "Metrics endpoint disabled in production"}
    
    metrics = {
        "database": await get_db_stats() if db_session.db_manager else {"status": "not initialized"},
        "application": {
            "environment": settings.ENVIRONMENT,
            "version": settings.VERSION,
            "debug_mode": settings.DEBUG,
        }
    }
    
    return metrics


# Include API routers
from src.api.v1.api import api_router
app.include_router(api_router, prefix=settings.API_V1_STR)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.
    Logs full error in server, returns safe error to client.
    """
    logger.exception(
        f"Unhandled exception: {exc}\n"
        f"Path: {request.url.path}\n"
        f"Method: {request.method}"
    )
    
    # Don't expose internal errors in production
    if settings.is_production():
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "request_id": request.headers.get("X-Request-ID"),
            }
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "request_id": request.headers.get("X-Request-ID"),
            }
        )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
