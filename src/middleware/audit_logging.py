"""
Audit logging middleware for HIPAA compliance.
Logs all data access and modifications.
"""
import time
import json
import logging
from typing import Callable, Optional, Dict, Any
from fastapi import Request, Response
from datetime import datetime

from src.db.models.audit_log import AuditLog
from src.db.session import AsyncSessionLocal
from src.core.config import settings

logger = logging.getLogger(__name__)


class AuditLoggingMiddleware:
    """
    HIPAA-compliant audit logging middleware.
    Tracks all protected health information (PHI) access.
    """
    
    # Endpoints that access PHI or sensitive data
    AUDITABLE_PATHS = [
        "/api/v1/devices",
        "/api/v1/users",
        "/api/v1/organizations",
        "/api/v1/documents",
        "/api/v1/incidents",
        "/api/v1/chat",
        "/api/v1/calendar",
        "/api/v1/analytics"
    ]
    
    # Actions that modify data
    WRITE_METHODS = ["POST", "PUT", "PATCH", "DELETE"]
    
    def __init__(self):
        self.enabled = settings.ENVIRONMENT in ["staging", "production"]
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Process request and create audit log"""
        if not self.enabled:
            return await call_next(request)
        
        # Check if path should be audited
        if not self._should_audit(request):
            return await call_next(request)
        
        # Capture request data
        start_time = time.time()
        request_body = await self._get_request_body(request)
        
        # Process request
        response = await call_next(request)
        
        # Create audit log entry
        try:
            await self._create_audit_log(
                request=request,
                response=response,
                request_body=request_body,
                duration=time.time() - start_time
            )
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
        
        return response
    
    def _should_audit(self, request: Request) -> bool:
        """Determine if request should be audited"""
        # Check if path matches auditable patterns
        path = request.url.path
        return any(path.startswith(pattern) for pattern in self.AUDITABLE_PATHS)
    
    async def _get_request_body(self, request: Request) -> Optional[Dict[str, Any]]:
        """Safely get request body for logging"""
        if request.method not in self.WRITE_METHODS:
            return None
        
        try:
            # Store body for later use
            body = await request.body()
            
            # Create new receive function that returns stored body
            async def receive():
                return {"type": "http.request", "body": body}
            
            request._receive = receive
            
            # Parse body if JSON
            if body and request.headers.get("content-type") == "application/json":
                return json.loads(body)
            
            return None
        except Exception as e:
            logger.error(f"Failed to read request body: {e}")
            return None
    
    async def _create_audit_log(
        self,
        request: Request,
        response: Response,
        request_body: Optional[Dict[str, Any]],
        duration: float
    ):
        """Create audit log entry in database"""
        async with AsyncSessionLocal() as db:
            try:
                # Get user info from request state
                user_id = getattr(request.state, "user_id", None)
                organization_id = getattr(request.state, "organization_id", None)
                
                # Determine action and resource
                action = self._get_action(request.method)
                resource_type, resource_id, resource_name = self._parse_resource(request)
                
                # Prepare changes data
                changes = {}
                if request_body:
                    # Remove sensitive fields
                    changes = self._sanitize_data(request_body)
                
                # Create audit log
                audit_log = AuditLog(
                    user_id=user_id,
                    organization_id=organization_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else "",
                    resource_name=resource_name,
                    changes=changes,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    session_id=request.headers.get("x-session-id"),
                    success=response.status_code < 400,
                    error_message=None if response.status_code < 400 else f"HTTP {response.status_code}"
                )
                
                db.add(audit_log)
                await db.commit()
                
                # Log to file for backup
                self._log_to_file(audit_log, duration)
                
            except Exception as e:
                logger.error(f"Failed to save audit log: {e}")
    
    def _get_action(self, method: str) -> str:
        """Map HTTP method to action"""
        mapping = {
            "GET": "view",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete"
        }
        return mapping.get(method, method.lower())
    
    def _parse_resource(self, request: Request) -> tuple[str, Optional[str], Optional[str]]:
        """Parse resource type and ID from path"""
        path_parts = request.url.path.strip("/").split("/")
        
        # Skip api/v1 prefix
        if len(path_parts) > 2 and path_parts[0] == "api":
            path_parts = path_parts[2:]
        
        resource_type = path_parts[0] if path_parts else "unknown"
        resource_id = None
        resource_name = None
        
        # Extract ID if present
        if len(path_parts) > 1:
            # Check if second part is an ID (numeric or UUID-like)
            potential_id = path_parts[1]
            if potential_id.isdigit() or "-" in potential_id:
                resource_id = potential_id
        
        # Get resource name from query params if available
        if request.query_params.get("name"):
            resource_name = request.query_params.get("name")
        
        return resource_type, resource_id, resource_name
    
    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive fields from logged data"""
        sensitive_fields = [
            "password",
            "password_hash",
            "token",
            "secret",
            "api_key",
            "credit_card",
            "ssn",
            "bank_account"
        ]
        
        sanitized = {}
        for key, value in data.items():
            # Check if field contains sensitive data
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_data(value)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                sanitized[key] = [self._sanitize_data(item) for item in value]
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _log_to_file(self, audit_log: AuditLog, duration: float):
        """Log audit entry to file for backup"""
        try:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": audit_log.user_id,
                "organization_id": audit_log.organization_id,
                "action": audit_log.action,
                "resource_type": audit_log.resource_type,
                "resource_id": audit_log.resource_id,
                "ip_address": audit_log.ip_address,
                "success": audit_log.success,
                "duration_ms": int(duration * 1000)
            }
            
            # Use structured logging
            logger.info(f"AUDIT: {json.dumps(log_entry)}")
            
        except Exception as e:
            logger.error(f"Failed to write audit log to file: {e}")
