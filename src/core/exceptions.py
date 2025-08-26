"""
Custom exceptions for the Nyelux application.
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException, status


class NyeluxException(Exception):
    """Base exception for all Nyelux custom exceptions"""
    
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(NyeluxException):
    """Raised when authentication fails"""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details
        )


class AuthorizationError(NyeluxException):
    """Raised when user lacks required permissions"""
    
    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details
        )


class ResourceNotFoundError(NyeluxException):
    """Raised when a requested resource is not found"""
    
    def __init__(self, resource: str, identifier: Any = None, details: Optional[str] = None):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with id '{identifier}' not found"
        if details:
            message = f"{message}. {details}"
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND
        )


class NotFoundError(NyeluxException):
    """Raised when a requested resource is not found"""
    
    def __init__(self, resource: str, identifier: Any = None):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with id '{identifier}' not found"
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND
        )


class ValidationError(NyeluxException):
    """Raised when validation fails"""
    
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        if field:
            details = details or {}
            details["field"] = field
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class ConflictError(NyeluxException):
    """Raised when there's a conflict with existing data"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details
        )


class RateLimitError(NyeluxException):
    """Raised when rate limit is exceeded"""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details
        )


class ExternalServiceError(NyeluxException):
    """Raised when an external service fails"""
    
    def __init__(self, service: str, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        msg = f"{service} service error"
        if message:
            msg = f"{msg}: {message}"
        super().__init__(
            message=msg,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details or {"service": service}
        )


class ServiceUnavailableError(NyeluxException):
    """Raised when an external service is unavailable"""
    
    def __init__(self, service: str, message: Optional[str] = None):
        msg = f"{service} service is currently unavailable"
        if message:
            msg = f"{msg}: {message}"
        super().__init__(
            message=msg,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"service": service}
        )


class DatabaseError(NyeluxException):
    """Raised when a database operation fails"""
    
    def __init__(self, message: str = "Database operation failed", operation: Optional[str] = None):
        details = {}
        if operation:
            details["operation"] = operation
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class FileProcessingError(NyeluxException):
    """Raised when file processing fails"""
    
    def __init__(self, filename: str, reason: str):
        super().__init__(
            message=f"Failed to process file '{filename}': {reason}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"filename": filename, "reason": reason}
        )


class ExternalAPIError(NyeluxException):
    """Raised when an external API call fails"""
    
    def __init__(self, api_name: str, message: str, status_code: Optional[int] = None):
        super().__init__(
            message=f"{api_name} API error: {message}",
            status_code=status_code or status.HTTP_502_BAD_GATEWAY,
            details={"api": api_name}
        )


class TokenError(AuthenticationError):
    """Raised when token validation fails"""
    
    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(message=message)


class MFARequiredError(AuthenticationError):
    """Raised when MFA is required but not provided"""
    
    def __init__(self, message: str = "Multi-factor authentication required"):
        super().__init__(
            message=message,
            details={"mfa_required": True}
        )


class OrganizationError(NyeluxException):
    """Raised for organization-related issues"""
    
    def __init__(self, message: str, org_id: Optional[int] = None):
        details = {}
        if org_id:
            details["organization_id"] = org_id
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class LicenseError(NyeluxException):
    """Raised when license limits are exceeded"""
    
    def __init__(self, message: str, limit_type: str, current: int, limit: int):
        super().__init__(
            message=message,
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            details={
                "limit_type": limit_type,
                "current": current,
                "limit": limit
            }
        )


# Exception handler for FastAPI
def create_http_exception(exc: NyeluxException) -> HTTPException:
    """Convert NyeluxException to HTTPException for FastAPI"""
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "message": exc.message,
            **exc.details
        }
    )


# Exception handlers for common scenarios
def handle_database_error(e: Exception) -> None:
    """Convert database exceptions to appropriate NyeluxException"""
    error_str = str(e).lower()
    
    if "duplicate key" in error_str or "unique constraint" in error_str:
        raise ConflictError("Resource already exists")
    elif "foreign key" in error_str:
        raise ValidationError("Referenced resource does not exist")
    elif "not null" in error_str:
        raise ValidationError("Required field is missing")
    else:
        raise DatabaseError(str(e))
