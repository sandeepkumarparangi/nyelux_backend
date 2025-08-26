from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, DateTime, func

class CustomBase:
    """
    Base class for all database models.
    Provides common fields and functionality.
    """
    
    # Generate __tablename__ automatically from class name
    @declared_attr
    def __tablename__(cls) -> str:
        """
        Generate table name from class name.
        Example: UserAccount -> user_account
        """
        name = cls.__name__
        # Convert CamelCase to snake_case
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                # Add underscore before uppercase letter
                if name[i-1].islower() or (i < len(name) - 1 and name[i+1].islower()):
                    result.append('_')
            result.append(char.lower())
        return ''.join(result)
    
    # Add timestamp columns to all tables
    created_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False,
        comment="Record creation timestamp"
    )
    
    updated_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(), 
        nullable=False,
        comment="Record last update timestamp"
    )

# Create the declarative base
Base = declarative_base(cls=CustomBase)

# Metadata for database creation
metadata = Base.metadata
