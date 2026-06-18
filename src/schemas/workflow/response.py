from datetime import datetime
from typing import Generic, TypeVar, Optional, Any, List, Dict
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# TYPE VARIABLES
# ============================================================

T = TypeVar("T")


# ============================================================
# BASE RESPONSE
# ============================================================

class APIResponse(BaseModel, Generic[T]):
    """
    Standard API response wrapper.

    Usage:
        return APIResponse(data=user, message="User created")
        return APIResponse[UserResponse](data=user)
    """
    success: bool = True
    message: str = "Request processed successfully"
    data: Optional[T] = None
    meta: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata (pagination, etc.)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Request processed successfully",
                "data": {},
                "meta": None,
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )


# ============================================================
# ERROR RESPONSE
# ============================================================

class ErrorDetail(BaseModel):
    """Individual error detail."""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """
    Standard error response format.

    Error Codes:
    - VALIDATION_ERROR: Input validation failed
    - NOT_FOUND: Resource not found
    - UNAUTHORIZED: Authentication required
    - FORBIDDEN: Permission denied
    - CONFLICT: Resource conflict
    - RATE_LIMITED: Too many requests
    - INTERNAL_ERROR: Server error
    - SERVICE_UNAVAILABLE: External service unavailable
    - BAD_GATEWAY: Upstream service error
    - GATEWAY_TIMEOUT: Upstream service timeout
    """
    success: bool = False
    message: str
    error_code: str = "INTERNAL_ERROR"
    details: Optional[List[ErrorDetail]] = None
    correlation_id: Optional[str] = Field(
        default=None,
        description="Request correlation ID for tracing"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Validation error",
                "error_code": "VALIDATION_ERROR",
                "details": [
                    {"field": "email", "message": "Invalid email format"}
                ],
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )

    @classmethod
    def validation_error(
            cls,
            message: str = "Validation error",
            details: List[ErrorDetail] = None
    ) -> "ErrorResponse":
        """Creates a validation error response."""
        return cls(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details
        )

    @classmethod
    def not_found(
            cls,
            resource: str = "Resource",
            resource_id: Optional[str] = None
    ) -> "ErrorResponse":
        """Creates a not found error response."""
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} '{resource_id}' not found"

        return cls(
            message=message,
            error_code="NOT_FOUND"
        )

    @classmethod
    def unauthorized(
            cls,
            message: str = "Authentication required"
    ) -> "ErrorResponse":
        """Creates an unauthorized error response."""
        return cls(
            message=message,
            error_code="UNAUTHORIZED"
        )

    @classmethod
    def forbidden(
            cls,
            message: str = "Permission denied"
    ) -> "ErrorResponse":
        """Creates a forbidden error response."""
        return cls(
            message=message,
            error_code="FORBIDDEN"
        )

    @classmethod
    def conflict(
            cls,
            message: str = "Resource conflict"
    ) -> "ErrorResponse":
        """Creates a conflict error response."""
        return cls(
            message=message,
            error_code="CONFLICT"
        )

    @classmethod
    def rate_limited(
            cls,
            retry_after: Optional[int] = None
    ) -> "ErrorResponse":
        """Creates a rate limited error response."""
        message = "Too many requests"
        if retry_after:
            message = f"Too many requests. Retry after {retry_after} seconds"

        return cls(
            message=message,
            error_code="RATE_LIMITED"
        )

    @classmethod
    def internal_error(
            cls,
            message: str = "An unexpected error occurred"
    ) -> "ErrorResponse":
        """Creates an internal error response."""
        return cls(
            message=message,
            error_code="INTERNAL_ERROR"
        )


# ============================================================
# PAGINATION
# ============================================================

class PaginationParams(BaseModel):
    """Pagination request parameters."""
    skip: int = Field(default=0, ge=0, description="Number of items to skip")
    limit: int = Field(default=100, ge=1, le=1000, description="Max items to return")
    sort_by: Optional[str] = Field(default=None, description="Field to sort by")
    sort_desc: bool = Field(default=True, description="Sort descending")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    skip: int = 0
    limit: int = 100
    total: int = 0
    has_more: bool = False
    page: int = 1
    total_pages: int = 1

    @classmethod
    def from_params(
            cls,
            skip: int,
            limit: int,
            total: int
    ) -> "PaginationMeta":
        """Creates pagination meta from params and total."""
        page = (skip // limit) + 1 if limit > 0 else 1
        total_pages = ((total - 1) // limit) + 1 if limit > 0 and total > 0 else 1

        return cls(
            skip=skip,
            limit=limit,
            total=total,
            has_more=(skip + limit) < total,
            page=page,
            total_pages=total_pages
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""
    success: bool = True
    message: str = "Items retrieved"
    items: List[T] = Field(default_factory=list)
    meta: PaginationMeta
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# HEALTH CHECK
# ============================================================

class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    checks: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# COMMON RESPONSES
# ============================================================

class IdResponse(BaseModel):
    """Response with just an ID."""
    id: UUID


class CountResponse(BaseModel):
    """Response with a count."""
    count: int


class DeleteResponse(BaseModel):
    """Response for delete operations."""
    success: bool = True
    message: str = "Resource deleted successfully"
    deleted_id: Optional[UUID] = None


# ============================================================
# OPENAPI ERROR RESPONSES
# ============================================================

# Pre-defined error responses for OpenAPI documentation
# Use these in endpoint response_model definitions

class UnauthorizedResponse(ErrorResponse):
    """401 Unauthorized response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Authentication required",
                "error_code": "UNAUTHORIZED",
                "details": None,
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )


class ForbiddenResponse(ErrorResponse):
    """403 Forbidden response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Not authorized to perform this action",
                "error_code": "FORBIDDEN",
                "details": None,
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )


class NotFoundResponse(ErrorResponse):
    """404 Not Found response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Resource not found",
                "error_code": "NOT_FOUND",
                "details": None,
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )


class ConflictResponse(ErrorResponse):
    """409 Conflict response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Resource already exists",
                "error_code": "CONFLICT",
                "details": None,
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )


class ValidationErrorResponse(ErrorResponse):
    """422 Validation Error response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Request validation failed",
                "error_code": "VALIDATION_ERROR",
                "details": [
                    {"field": "email", "message": "Invalid email format", "code": "invalid_format"}
                ],
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )


class RateLimitResponse(ErrorResponse):
    """429 Rate Limit response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "Too many requests. Retry after 60 seconds",
                "error_code": "RATE_LIMITED",
                "details": {"retry_after_seconds": 60},
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )


class InternalErrorResponse(ErrorResponse):
    """500 Internal Server Error response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "An unexpected error occurred",
                "error_code": "INTERNAL_ERROR",
                "details": None,
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
    )


# ============================================================
# OPENAPI RESPONSE HELPERS
# ============================================================

def get_error_responses(
    *,
    auth: bool = True,
    not_found: bool = False,
    conflict: bool = False,
    validation: bool = True,
    rate_limit: bool = True
) -> Dict[int, Dict[str, Any]]:
    """
    Generate OpenAPI error response definitions for endpoints.

    Usage:
        @router.get(
            "/items/{id}",
            responses=get_error_responses(not_found=True)
        )

    Args:
        auth: Include 401/403 responses (default True for protected endpoints)
        not_found: Include 404 response
        conflict: Include 409 response
        validation: Include 422 response
        rate_limit: Include 429 response

    Returns:
        Dictionary of status codes to response definitions
    """
    responses: Dict[int, Dict[str, Any]] = {}

    if auth:
        responses[401] = {
            "model": UnauthorizedResponse,
            "description": "Authentication required or invalid token"
        }
        responses[403] = {
            "model": ForbiddenResponse,
            "description": "Insufficient permissions"
        }

    if not_found:
        responses[404] = {
            "model": NotFoundResponse,
            "description": "Resource not found"
        }

    if conflict:
        responses[409] = {
            "model": ConflictResponse,
            "description": "Resource conflict (e.g., duplicate)"
        }

    if validation:
        responses[422] = {
            "model": ValidationErrorResponse,
            "description": "Request validation failed"
        }

    if rate_limit:
        responses[429] = {
            "model": RateLimitResponse,
            "description": "Rate limit exceeded"
        }

    responses[500] = {
        "model": InternalErrorResponse,
        "description": "Internal server error"
    }

    return responses


# Common response sets for different endpoint types
STANDARD_RESPONSES = get_error_responses()
CRUD_RESPONSES = get_error_responses(not_found=True, conflict=True)
PUBLIC_RESPONSES = get_error_responses(auth=False)