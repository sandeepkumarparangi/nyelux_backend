"""
Database Base Configuration
Import all models here for Alembic to detect them.
"""
from src.db.base_class import Base

# Import all models to ensure they're registered with SQLAlchemy
# This is required for Alembic migrations to work properly
from src.db.models import *  # noqa: F401, F403

# Export Base
__all__ = ["Base"]
