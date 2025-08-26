"""
Enhanced database session management with performance optimizations.

This module provides improved dependency injection patterns for database
connection management with request-scoped sessions, performance monitoring,
and advanced transaction control.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, TypeVar, Callable, Any
from functools import wraps
import logging

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    async_sessionmaker, 
    create_async_engine,
    AsyncConnection
)
from sqlalchemy.pool import NullPool, QueuePool, StaticPool
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from src.core.config import settings

logger = logging.getLogger(__name__)

# Type variable for generic model operations
T = TypeVar("T")

# Performance monitoring
class DatabaseMetrics:
    """Track database performance metrics."""
    
    def __init__(self):
        self.query_count = 0
        self.total_time = 0.0
        self.slow_queries = []
        self.connection_count = 0
    
    def record_query(self, duration: float, query: str):
        """Record query execution metrics."""
        self.query_count += 1
        self.total_time += duration
        
        # Track slow queries (>100ms)
        if duration > 0.1:
            self.slow_queries.append({
                "query": query,
                "duration": duration,
                "timestamp": time.time()
            })
    
    @property
    def average_query_time(self) -> float:
        """Get average query execution time."""
        return self.total_time / self.query_count if self.query_count > 0 else 0


# Global metrics instance
db_metrics = DatabaseMetrics()

# Enhanced engine configuration with performance optimizations
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,  # Verify connections before use
    
    # Optimized pool settings based on environment
    pool_size=20 if settings.ENVIRONMENT == "production" else 5,
    max_overflow=40 if settings.ENVIRONMENT == "production" else 10,
    pool_timeout=30,
    pool_recycle=3600,  # Recycle connections after 1 hour
    
    # Use appropriate pool class
    poolclass=(
        StaticPool if settings.ENVIRONMENT == "test" else  # Best for testing
        QueuePool if settings.ENVIRONMENT == "production" else  # Best for production
        NullPool  # Development - new connection each time
    ),
    
    # Connection arguments
    connect_args={
        "server_settings": {
            "application_name": f"nyelux-{settings.ENVIRONMENT}",
            "jit": "on"
        },
        "command_timeout": 60,
        "prepared_statement_cache_size": 0,  # Disable to prevent issues with pooling
    }
)

# Session factory with optimized settings
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autocommit=False,
    autoflush=False,  # Control flushing manually for better performance
)


# Request-scoped session management
class DatabaseSessionManager:
    """
    Manages database sessions with request scope.
    Ensures one session per request for better performance.
    """
    
    def __init__(self):
        self._sessions: dict[int, AsyncSession] = {}
    
    async def get_session(self, request_id: int) -> AsyncSession:
        """Get or create session for request."""
        if request_id not in self._sessions:
            self._sessions[request_id] = AsyncSessionLocal()
        return self._sessions[request_id]
    
    async def close_session(self, request_id: int):
        """Close and remove session for request."""
        if request_id in self._sessions:
            session = self._sessions.pop(request_id)
            await session.close()


# Global session manager
session_manager = DatabaseSessionManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Standard database session dependency.
    Provides auto-commit and auto-rollback functionality.
    """
    async with AsyncSessionLocal() as session:
        start_time = time.time()
        db_metrics.connection_count += 1
        
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            duration = time.time() - start_time
            if duration > 0.5:  # Log slow transactions
                logger.warning(f"Slow transaction: {duration:.3f}s")
            await session.close()


async def get_db_read_only() -> AsyncGenerator[AsyncSession, None]:
    """
    Read-only database session dependency.
    Optimized for read operations with no commit overhead.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # No commit for read-only operations
        except Exception as e:
            logger.error(f"Read-only session error: {e}")
            raise
        finally:
            await session.close()


async def get_request_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Request-scoped database session.
    Reuses the same session throughout a request for better performance.
    """
    request_id = id(request)
    session = await session_manager.get_session(request_id)
    
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Request session error: {e}")
        raise
    finally:
        # Don't close here - let request cleanup handle it
        pass


@asynccontextmanager
async def get_db_transaction():
    """
    Explicit transaction context manager.
    Use for complex multi-step operations that need transaction control.
    
    Usage:
        async with get_db_transaction() as session:
            # All operations here are in a single transaction
            user = await session.get(User, user_id)
            user.credits -= 10
            await session.flush()  # Flush but don't commit yet
            
            order = Order(user_id=user.id, amount=10)
            session.add(order)
            # Commit happens automatically on context exit
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
        # Auto-commit on successful exit, auto-rollback on exception


def transactional(func: Callable) -> Callable:
    """
    Decorator for transactional operations.
    Ensures all database operations in the function run in a single transaction.
    
    Usage:
        @transactional
        async def transfer_credits(db: AsyncSession, from_user_id: int, to_user_id: int, amount: int):
            from_user = await db.get(User, from_user_id)
            to_user = await db.get(User, to_user_id)
            
            from_user.credits -= amount
            to_user.credits += amount
            
            # Automatically committed or rolled back
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Find the db session in arguments
        db = None
        for arg in args:
            if isinstance(arg, AsyncSession):
                db = arg
                break
        
        if not db:
            # Look in kwargs
            db = kwargs.get('db')
        
        if not db:
            raise ValueError("No AsyncSession found in function arguments")
        
        async with db.begin():
            return await func(*args, **kwargs)
    
    return wrapper


class DatabaseSessionMiddleware:
    """
    Middleware for request-scoped session management.
    Ensures one database session per request.
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request_id = id(scope)
            
            async def cleanup():
                await session_manager.close_session(request_id)
            
            scope["cleanup_funcs"] = scope.get("cleanup_funcs", [])
            scope["cleanup_funcs"].append(cleanup)
        
        await self.app(scope, receive, send)


# Performance monitoring with events
@event.listens_for(engine.sync_engine, "before_execute")
def before_execute(conn, clauseelement, multiparams, params, execution_options):
    """Track query start time."""
    conn.info["query_start_time"] = time.time()


@event.listens_for(engine.sync_engine, "after_execute")
def after_execute(conn, clauseelement, multiparams, params, execution_options, result):
    """Track query execution time."""
    start_time = conn.info.pop("query_start_time", None)
    if start_time:
        duration = time.time() - start_time
        db_metrics.record_query(duration, str(clauseelement))


# Optimized bulk operations
async def bulk_insert(session: AsyncSession, models: list[T]) -> list[T]:
    """
    Optimized bulk insert operation.
    Much faster than individual inserts for large datasets.
    """
    if not models:
        return []
    
    session.add_all(models)
    await session.flush()
    
    # Refresh all models to get generated IDs
    for model in models:
        await session.refresh(model)
    
    return models


async def bulk_update(session: AsyncSession, model_class: type[T], updates: list[dict]) -> int:
    """
    Optimized bulk update operation.
    
    Args:
        session: Database session
        model_class: SQLAlchemy model class
        updates: List of dicts with 'id' and fields to update
        
    Returns:
        Number of records updated
    """
    if not updates:
        return 0
    
    # Use bulk_update_mappings for efficiency
    await session.execute(
        model_class.__table__.update(),
        updates
    )
    
    return len(updates)


# Connection pool monitoring
async def get_pool_status() -> dict:
    """Get current connection pool status."""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total": pool.size() + pool.overflow()
    }


# Health check with performance info
async def check_database_health() -> dict:
    """
    Comprehensive database health check.
    Returns health status and performance metrics.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Basic connectivity test
            start = time.time()
            result = await session.execute(text("SELECT 1"))
            query_time = time.time() - start
            
            # Get table counts for monitoring
            table_counts = {}
            for table in ["users", "vendor_devices", "gudid_devices"]:
                count_result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                )
                table_counts[table] = count_result.scalar()
            
            # Get pool status
            pool_status = await get_pool_status()
            
            return {
                "status": "healthy",
                "response_time_ms": query_time * 1000,
                "pool_status": pool_status,
                "metrics": {
                    "total_queries": db_metrics.query_count,
                    "average_query_time_ms": db_metrics.average_query_time * 1000,
                    "slow_queries": len(db_metrics.slow_queries),
                    "total_connections": db_metrics.connection_count
                },
                "table_counts": table_counts
            }
            
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# Export improved dependencies
__all__ = [
    "get_db",
    "get_db_read_only", 
    "get_request_db",
    "get_db_transaction",
    "transactional",
    "bulk_insert",
    "bulk_update",
    "check_database_health",
    "db_metrics"
]
