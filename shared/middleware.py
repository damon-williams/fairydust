# shared/middleware.py
"""
Centralized middleware for the fairydust platform.
Provides consistent request validation, error handling, and security across all services.
"""

import json
import logging
import time
from typing import Callable, Dict, Any, Optional
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Centralized request validation middleware with:
    - Request size limits
    - Content type validation
    - Request logging
    - Standardized error responses
    """
    
    def __init__(
        self,
        app: ASGIApp,
        max_request_size: int = 10 * 1024 * 1024,  # 10MB default
        allowed_content_types: Optional[list] = None,
        log_requests: bool = True
    ):
        super().__init__(app)
        self.max_request_size = max_request_size
        self.allowed_content_types = allowed_content_types or [
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
            "text/plain"
        ]
        self.log_requests = log_requests
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        try:
            # Skip validation for certain paths
            if self._should_skip_validation(request.url.path):
                response = await call_next(request)
                return response
            
            # Validate request size
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_request_size:
                return self._create_error_response(
                    status_code=413,
                    message=f"Request too large. Maximum size: {self.max_request_size} bytes",
                    details={"max_size": self.max_request_size, "received_size": int(content_length)}
                )
            
            # Validate content type for POST/PUT/PATCH requests
            if request.method in ["POST", "PUT", "PATCH"]:
                content_type = request.headers.get("content-type", "").split(";")[0]
                if content_type and content_type not in self.allowed_content_types:
                    return self._create_error_response(
                        status_code=415,
                        message=f"Unsupported content type: {content_type}",
                        details={"allowed_types": self.allowed_content_types}
                    )
            
            # Log incoming request
            if self.log_requests:
                logger.info(f"{request.method} {request.url.path} - Client: {request.client.host if request.client else 'unknown'}")
            
            # Process request
            response = await call_next(request)
            
            # Log response
            if self.log_requests:
                process_time = time.time() - start_time
                logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
            
            return response
            
        except HTTPException as e:
            # Convert FastAPI HTTPException to standardized response
            return self._create_error_response(
                status_code=e.status_code,
                message=e.detail,
                details=getattr(e, 'details', None)
            )
            
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in middleware: {e}", exc_info=True)
            return self._create_error_response(
                status_code=500,
                message="Internal server error",
                details={"error_type": type(e).__name__}
            )
    
    def _should_skip_validation(self, path: str) -> bool:
        """Skip validation for certain paths"""
        skip_paths = [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico"
        ]
        return any(path.startswith(skip_path) for skip_path in skip_paths)
    
    def _create_error_response(
        self, 
        status_code: int, 
        message: str, 
        details: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """Create standardized error response"""
        error_response = {
            "error": True,
            "message": message,
            "status_code": status_code,
            "timestamp": time.time()
        }
        
        if details:
            error_response["details"] = details
        
        return JSONResponse(
            status_code=status_code,
            content=error_response
        )

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses
    """
    
    def __init__(self, app: ASGIApp, service_name: str = "fairydust"):
        super().__init__(app)
        self.service_name = service_name
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Service-Name"] = self.service_name
        
        # Add cache control for API responses
        if request.url.path.startswith("/api") or "json" in response.headers.get("content-type", ""):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        
        return response

class RequestSizeValidationMiddleware(BaseHTTPMiddleware):
    """
    Validate request body size for specific endpoints
    """
    
    def __init__(self, app: ASGIApp, endpoint_limits: Optional[Dict[str, int]] = None):
        super().__init__(app)
        self.endpoint_limits = endpoint_limits or {}
        self.default_limit = 10 * 1024 * 1024  # 10MB
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get content length
        content_length = request.headers.get("content-length")
        if not content_length:
            return await call_next(request)
        
        content_length = int(content_length)
        
        # Check endpoint-specific limits
        path = request.url.path
        limit = self.default_limit
        
        for endpoint_pattern, endpoint_limit in self.endpoint_limits.items():
            if endpoint_pattern in path:
                limit = endpoint_limit
                break
        
        # Validate size
        if content_length > limit:
            return JSONResponse(
                status_code=413,
                content={
                    "error": True,
                    "message": f"Request too large for endpoint {path}",
                    "details": {
                        "max_size": limit,
                        "received_size": content_length,
                        "endpoint": path
                    }
                }
            )
        
        return await call_next(request)

def create_standard_error_handler():
    """
    Create standardized error handlers for FastAPI apps
    """
    async def validation_exception_handler(request: Request, exc):
        """Handle Pydantic validation errors"""
        return JSONResponse(
            status_code=422,
            content={
                "error": True,
                "message": "Validation error",
                "details": exc.errors() if hasattr(exc, 'errors') else str(exc),
                "status_code": 422,
                "timestamp": time.time()
            }
        )
    
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions"""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "message": exc.detail,
                "status_code": exc.status_code,
                "timestamp": time.time()
            }
        )
    
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions"""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "Internal server error",
                "status_code": 500,
                "timestamp": time.time()
            }
        )
    
    return {
        "validation_exception_handler": validation_exception_handler,
        "http_exception_handler": http_exception_handler,
        "general_exception_handler": general_exception_handler
    }

def add_middleware_to_app(
    app,
    service_name: str,
    max_request_size: int = 10 * 1024 * 1024,
    endpoint_limits: Optional[Dict[str, int]] = None,
    log_requests: bool = True
):
    """
    Add all standard middleware to a FastAPI app
    
    Args:
        app: FastAPI application instance
        service_name: Name of the service (for headers and logging)
        max_request_size: Default maximum request size in bytes
        endpoint_limits: Dict of endpoint patterns to size limits
        log_requests: Whether to log requests
    """
    
    # Add middleware (order matters - last added is executed first)
    app.add_middleware(SecurityHeadersMiddleware, service_name=service_name)
    
    if endpoint_limits:
        app.add_middleware(RequestSizeValidationMiddleware, endpoint_limits=endpoint_limits)
    
    app.add_middleware(
        RequestValidationMiddleware,
        max_request_size=max_request_size,
        log_requests=log_requests
    )
    
    # Add exception handlers
    handlers = create_standard_error_handler()
    from fastapi.exceptions import RequestValidationError
    
    app.add_exception_handler(RequestValidationError, handlers["validation_exception_handler"])
    app.add_exception_handler(HTTPException, handlers["http_exception_handler"])
    app.add_exception_handler(Exception, handlers["general_exception_handler"])