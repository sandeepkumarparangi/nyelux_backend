from datetime import datetime
from typing import Optional, Any, Dict, Generic, TypeVar, List
from pydantic import BaseModel, ConfigDict, field_serializer

# Type variable for generic pagination
T = TypeVar('T')

class BaseSchema(BaseModel):
    """Base schema with common configuration"""
    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode
        validate_assignment=True,  # Validate on assignment
        populate_by_name=True,  # Allow population by field name
        use_enum_values=True,  # Use enum values instead of names
        arbitrary_types_allowed=True,  # Allow arbitrary types
        protected_namespaces=(),  # Allow fields like 'model_number'
        # json_encoders removed - use field_serializer instead
    )
    
    @field_serializer('created_at', 'updated_at', check_fields=False)
    def serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime to ISO format"""
        return dt.isoformat() if dt else None

class TimestampMixin(BaseModel):
    """Mixin for timestamp fields"""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime to ISO format"""
        return dt.isoformat() if dt else None

class PaginationParams(BaseModel):
    """Pagination parameters"""
    page: int = 1
    limit: int = 20
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit
    
    def validate_limit(self) -> int:
        """Ensure limit is within bounds"""
        return min(max(self.limit, 1), 100)  # Max 100 items per page

class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""
    model_config = ConfigDict(from_attributes=True)
    
    items: List[T]
    total: int
    page: int
    pages: int
    limit: int
    
    @classmethod
    def create(cls, items: List[T], total: int, page: int, limit: int):
        """Create paginated response"""
        pages = (total + limit - 1) // limit if limit > 0 else 1
        return cls(
            items=items,
            total=total,
            page=page,
            pages=pages,
            limit=limit
        )

class SuccessResponse(BaseModel):
    """Standard success response"""
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: Dict[str, Any]
