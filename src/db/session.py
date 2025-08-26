"""
Enhanced Database Session Management with Dependency Injection
Features:
- Connection pooling with performance optimization
- Automatic session lifecycle management
- Read replica support for scaling
- Health checks and monitoring
- Retry logic for transient failures
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy import event, select, text, create_engine
from contextlib import asynccontextmanager
import logging
import time
from typing import AsyncGenerator, Optional, Dict, Any
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_sync_engine():
    """Get synchronous engine for migrations and setup."""
    from src.core.config import settings
    return create_engine(
        settings.SYNC_DATABASE_URL,
        pool_pre_ping=True,
        echo=settings.DEBUG
    )


class DatabaseSessionManager:
    """
    Advanced database session manager with connection pooling,
    health checks, and performance monitoring.
    """
    
    def __init__(
        self,
        database_url: str,
        read_replica_url: Optional[str] = None,
        pool_size: int = 20,
        max_overflow: int = 40,
        pool_timeout: float = 30.0,
        pool_recycle: int = 3600,
        echo: bool = False,
        enable_query_logging: bool = False
    ):
        """
        Initialize database connection manager.
        
        Args:
            database_url: Primary database URL
            read_replica_url: Optional read replica URL for read operations
            pool_size: Number of connections to maintain in pool
            max_overflow: Maximum overflow connections allowed
            pool_timeout: Timeout for getting connection from pool
            pool_recycle: Recycle connections after this many seconds
            echo: Enable SQL query logging
            enable_query_logging: Enable detailed query performance logging
        """
        self.database_url = database_url
        self.read_replica_url = read_replica_url
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        self.echo = echo
        self.enable_query_logging = enable_query_logging
        
        # Performance metrics
        self._metrics: Dict[str, Any] = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "slow_queries": 0,
            "total_queries": 0,
            "last_health_check": None,
            "is_healthy": False
        }
        
        # Create engines
        self._primary_engine: Optional[AsyncEngine] = None
        self._read_replica_engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker] = None
        self._read_session_factory: Optional[async_sessionmaker] = None
        
    async def initialize(self):
        """Initialize database engines and session factories."""
        logger.info("Initializing database connection manager...")
        
        # Create primary engine with optimized pool
        self._primary_engine = create_async_engine(
            self.database_url,
            echo=self.echo,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=self.pool_recycle,
            pool_pre_ping=True,  # Verify connections before use
            connect_args={
                "server_settings": {
                    "application_name": "nyelux_backend",
                    "jit": "off"  # Disable JIT for consistent performance
                },
                "command_timeout": 60,
                "prepared_statement_cache_size": 0,  # Disable for better compatibility
            }
        )
        
        # Create read replica engine if URL provided
        if self.read_replica_url:
            self._read_replica_engine = create_async_engine(
                self.read_replica_url,
                echo=self.echo,
                pool_size=self.pool_size // 2,  # Smaller pool for read replica
                max_overflow=self.max_overflow // 2,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=True,
                connect_args={
                    "server_settings": {
                        "application_name": "nyelux_backend_read",
                        "jit": "off"
                    },
                    "command_timeout": 60,
                }
            )
        
        # Create session factories
        self._session_factory = async_sessionmaker(
            self._primary_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        if self._read_replica_engine:
            self._read_session_factory = async_sessionmaker(
                self._read_replica_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
        
        # Set up event listeners for monitoring
        if self.enable_query_logging:
            self._setup_query_logging()
        
        # Run initial health check
        await self.health_check()
        
        logger.info("Database connection manager initialized successfully")
    
    def _setup_query_logging(self):
        """Set up query performance logging."""
        
        @event.listens_for(self._primary_engine.sync_engine, "before_cursor_execute")
        def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault("query_start_time", []).append(time.time())
            
        @event.listens_for(self._primary_engine.sync_engine, "after_cursor_execute")
        def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            total_time = time.time() - conn.info["query_start_time"].pop(-1)
            self._metrics["total_queries"] += 1
            
            # Log slow queries
            if total_time > 1.0:  # Queries taking more than 1 second
                self._metrics["slow_queries"] += 1
                logger.warning(
                    f"Slow query detected ({total_time:.2f}s): {statement[:100]}..."
                )
    
    async def close(self):
        """Close all database connections."""
        logger.info("Closing database connections...")
        
        if self._primary_engine:
            await self._primary_engine.dispose()
            
        if self._read_replica_engine:
            await self._read_replica_engine.dispose()
            
        logger.info("Database connections closed")
    
    @asynccontextmanager
    async def get_db_session(self, read_only: bool = False) -> AsyncGenerator[AsyncSession, None]:
        """
        Get database session with automatic lifecycle management.
        
        Args:
            read_only: If True and read replica is configured, use read replica
            
        Yields:
            AsyncSession: Database session
        """
        session_factory = self._session_factory
        
        # Use read replica for read-only operations if available
        if read_only and self._read_session_factory:
            session_factory = self._read_session_factory
            
        async with session_factory() as session:
            self._metrics["total_connections"] += 1
            self._metrics["active_connections"] += 1
            
            try:
                yield session
                # Note: We don't auto-commit here - let the endpoint decide
            except Exception as e:
                self._metrics["failed_connections"] += 1
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                self._metrics["active_connections"] -= 1
                await session.close()
    
    async def get_db(self) -> AsyncGenerator[AsyncSession, None]:
        """
        FastAPI dependency for getting database session.
        
        This is the main dependency injection function for FastAPI.
        """
        async with self.get_db_session() as session:
            yield session
    
    async def get_read_db(self) -> AsyncGenerator[AsyncSession, None]:
        """
        FastAPI dependency for getting read-only database session.
        
        Uses read replica if available, otherwise uses primary.
        """
        async with self.get_db_session(read_only=True) as session:
            yield session
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on database connections.
        
        Returns:
            Dict with health status and metrics
        """
        health_status = {
            "primary": False,
            "read_replica": False,
            "metrics": self._metrics.copy(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Check primary database
        try:
            async with self.get_db_session() as session:
                result = await session.execute(text("SELECT 1"))
                health_status["primary"] = bool(result.scalar())
        except Exception as e:
            logger.error(f"Primary database health check failed: {e}")
            health_status["primary_error"] = str(e)
        
        # Check read replica if configured
        if self._read_replica_engine:
            try:
                async with self.get_db_session(read_only=True) as session:
                    result = await session.execute(text("SELECT 1"))
                    health_status["read_replica"] = bool(result.scalar())
            except Exception as e:
                logger.error(f"Read replica health check failed: {e}")
                health_status["read_replica_error"] = str(e)
        else:
            health_status["read_replica"] = None
        
        # Update metrics
        self._metrics["last_health_check"] = datetime.utcnow()
        self._metrics["is_healthy"] = health_status["primary"]
        
        return health_status
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        return self._metrics.copy()
    
    async def execute_with_retry(
        self,
        func,
        max_retries: int = 3,
        retry_delay: float = 0.5,
        exponential_backoff: bool = True
    ):
        """
        Execute database operation with retry logic for transient failures.
        
        Args:
            func: Async function to execute
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds
            exponential_backoff: Whether to use exponential backoff
            
        Returns:
            Result of the function
        """
        last_exception = None
        delay = retry_delay
        
        for attempt in range(max_retries + 1):
            try:
                return await func()
            except Exception as e:
                last_exception = e
                
                # Don't retry on certain errors
                error_message = str(e).lower()
                if any(msg in error_message for msg in [
                    "syntax error",
                    "column",
                    "relation",
                    "permission",
                    "constraint"
                ]):
                    raise  # Don't retry programming errors
                
                if attempt < max_retries:
                    logger.warning(
                        f"Database operation failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    await asyncio.sleep(delay)
                    
                    if exponential_backoff:
                        delay *= 2  # Double the delay for next retry
        
        raise last_exception


# Global database manager instance
db_manager: Optional[DatabaseSessionManager] = None


async def init_db(
    database_url: str,
    read_replica_url: Optional[str] = None,
    **kwargs
) -> DatabaseSessionManager:
    """
    Initialize the global database manager.
    
    Args:
        database_url: Primary database URL
        read_replica_url: Optional read replica URL
        **kwargs: Additional arguments for DatabaseSessionManager
        
    Returns:
        Initialized DatabaseSessionManager
    """
    global db_manager
    
    db_manager = DatabaseSessionManager(
        database_url=database_url,
        read_replica_url=read_replica_url,
        **kwargs
    )
    
    await db_manager.initialize()
    return db_manager


async def close_db():
    """Close the global database manager."""
    global db_manager
    
    if db_manager:
        await db_manager.close()
        db_manager = None


# FastAPI dependency functions
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database session.
    
    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    if not db_manager:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    async with db_manager.get_db_session() as session:
        yield session


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for read-only database session.
    
    Uses read replica if available, otherwise uses primary.
    
    Usage:
        @router.get("/items/{id}")
        async def get_item(id: int, db: AsyncSession = Depends(get_read_db)):
            result = await db.execute(select(Item).where(Item.id == id))
            return result.scalar_one_or_none()
    """
    if not db_manager:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    async with db_manager.get_db_session(read_only=True) as session:
        yield session


# Transaction helpers
@asynccontextmanager
async def database_transaction():
    """
    Context manager for explicit transaction control.
    
    Usage:
        async with database_transaction() as session:
            user = User(name="John")
            session.add(user)
            # Transaction automatically commits on success, rolls back on error
    """
    if not db_manager:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    async with db_manager.get_db_session() as session:
        async with session.begin():
            yield session


# Performance monitoring endpoint data
async def get_db_stats() -> Dict[str, Any]:
    """Get database performance statistics for monitoring."""
    if not db_manager:
        return {"error": "Database not initialized"}
    
    stats = db_manager.get_metrics()
    health = await db_manager.health_check()
    
    return {
        "connections": {
            "total": stats["total_connections"],
            "active": stats["active_connections"],
            "failed": stats["failed_connections"],
        },
        "queries": {
            "total": stats["total_queries"],
            "slow": stats["slow_queries"],
        },
        "health": health,
        "pool": {
            "size": db_manager.pool_size,
            "max_overflow": db_manager.max_overflow,
            "timeout": db_manager.pool_timeout,
            "recycle": db_manager.pool_recycle,
        }
    }


# For backward compatibility - create a simple engine
from src.core.config import settings

# Create a simple async engine for scripts that need it
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)
