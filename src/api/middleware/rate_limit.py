"""
Redis-based Rate Limiting Middleware.

Production-ready middleware that:
- Uses Redis for distributed rate limiting across instances
- Supports per-IP, per-user, and per-endpoint limits
- Handles tier-based rate limits (anonymous, free, pro, enterprise)
- Provides bypass mechanisms for internal services
- Falls back gracefully when Redis is unavailable
- Adds standard rate limit headers to responses
"""

import time
import secrets
import importlib
from typing import Optional, Callable, Tuple, Dict, Any

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from src.core.config import settings


# ============================================================
# ENDPOINT PATTERNS FOR SPECIAL RATE LIMITS
# ============================================================

# Endpoints that need stricter rate limits
STRICT_RATE_LIMIT_PATTERNS = {
    # Auth endpoints - prevent brute force
    "/api/v1/auth/login": ("auth", 10, 60),  # 10 per minute
    "/api/v1/auth/register": ("auth", 5, 60),  # 5 per minute
    "/api/v1/auth/refresh": ("auth", 20, 60),  # 20 per minute
    "/api/v1/auth/forgot-password": ("auth", 3, 60),  # 3 per minute

    # Execution endpoints - expensive operations
    "/api/v1/workflows/*/execute": ("execute", 30, 60),  # 30 per minute
    "/api/v1/executions": ("execute", 30, 60),  # 30 per minute

    # AI-heavy endpoints
    "/api/v1/discovery/search": ("ai", 20, 60),  # 20 per minute
}

# Endpoints exempt from rate limiting
EXEMPT_PATTERNS = [
    "/health",
    "/health/live",
    "/health/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For (most common)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take first IP (original client)
        return forwarded.split(",")[0].strip()

    # Check X-Real-IP (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Check CF-Connecting-IP (Cloudflare)
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # Fall back to direct connection
    if request.client:
        return request.client.host

    return None


def get_user_from_request(request: Request) -> Tuple[Optional[str], str]:
    """
    Extract user ID and tier from request.

    Returns:
        Tuple of (user_id, tier)
    """
    # Check if user is set by auth middleware
    user = getattr(request.state, "user", None)
    if user:
        user_id = str(user.id) if hasattr(user, "id") else str(user)
        # Get tier from user model or default to free
        tier = getattr(user, "tier", "free") or "free"
        return user_id, tier

    # Check for API key in header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # In production, look up API key to get user/tier
        # For now, return API key as identifier
        return f"apikey:{api_key[:8]}", "free"

    # Anonymous user
    return None, "anonymous"


def get_endpoint_limit(path: str, method: str) -> Optional[Tuple[str, int, int]]:
    """
    Get special rate limit for an endpoint.

    Returns:
        Tuple of (category, requests, window_seconds) or None
    """
    # Check exact match first
    if path in STRICT_RATE_LIMIT_PATTERNS:
        return STRICT_RATE_LIMIT_PATTERNS[path]

    # Check wildcard patterns
    for pattern, limit_config in STRICT_RATE_LIMIT_PATTERNS.items():
        if "*" in pattern:
            # Simple wildcard matching
            parts = pattern.split("*")
            if len(parts) == 2:
                prefix, suffix = parts
                if path.startswith(prefix) and path.endswith(suffix):
                    return limit_config

    return None


def is_exempt(path: str) -> bool:
    """Check if path is exempt from rate limiting."""
    for pattern in EXEMPT_PATTERNS:
        if path == pattern or path.startswith(pattern):
            return True
    return False


def should_bypass(request: Request) -> bool:
    """Check if request should bypass rate limiting."""
    # Check bypass IPs
    client_ip = get_client_ip(request)
    if client_ip and client_ip in settings.RATE_LIMIT_BYPASS_IPS:
        return True

    # Check bypass header/secret
    if settings.RATE_LIMIT_BYPASS_HEADER and settings.RATE_LIMIT_BYPASS_SECRET:
        header_value = request.headers.get(settings.RATE_LIMIT_BYPASS_HEADER)
        secret = settings.RATE_LIMIT_BYPASS_SECRET.get_secret_value()
        if header_value and secret and secrets.compare_digest(header_value, secret):
            return True

    # Check internal service header
    internal = request.headers.get("X-Internal-Service")
    if internal == "true":
        # Verify internal secret if configured
        internal_secret = request.headers.get("X-Internal-Secret")
        if internal_secret:
            # In production, validate against known internal secrets
            pass

    return False


# ============================================================
# RATE LIMIT MIDDLEWARE
# ============================================================

class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Production-ready Redis-based rate limiting middleware.

    Features:
    - Distributed rate limiting across multiple instances
    - Per-IP, per-user, and per-endpoint limits
    - Tier-based limits (anonymous, free, pro, enterprise)
    - Bypass mechanisms for internal services
    - Graceful degradation when Redis unavailable
    - Standard rate limit headers (X-RateLimit-*)
    """

    def __init__(self, app, manager: Any = None):
        super().__init__(app)
        self._manager = manager
        self._initialized = False
        self._tiers = self._build_tiers()

    def _build_tiers(self) -> Dict[str, Any]:
        """Build tier configurations from settings."""
        rate_limiter_mod = importlib.import_module("src.core.rate_limiter")
        RateLimitTier = rate_limiter_mod.RateLimitTier

        return {
            "anonymous": RateLimitTier(
                "anonymous",
                settings.RATE_LIMIT_TIER_ANONYMOUS,
                settings.RATE_LIMIT_TIER_ANONYMOUS * 30,
                settings.RATE_LIMIT_TIER_ANONYMOUS * 500,
                5
            ),
            "free": RateLimitTier(
                "free",
                settings.RATE_LIMIT_TIER_FREE,
                settings.RATE_LIMIT_TIER_FREE * 30,
                settings.RATE_LIMIT_TIER_FREE * 500,
                10
            ),
            "pro": RateLimitTier(
                "pro",
                settings.RATE_LIMIT_TIER_PRO,
                settings.RATE_LIMIT_TIER_PRO * 30,
                settings.RATE_LIMIT_TIER_PRO * 500,
                50
            ),
            "enterprise": RateLimitTier(
                "enterprise",
                settings.RATE_LIMIT_TIER_ENTERPRISE,
                settings.RATE_LIMIT_TIER_ENTERPRISE * 30,
                settings.RATE_LIMIT_TIER_ENTERPRISE * 500,
                100
            ),
        }

    async def _ensure_manager(self) -> Any:
        """Ensure rate limit manager is initialized."""
        if self._manager:
            return self._manager

        if self._initialized:
            return None

        try:
            rate_limiter_mod = importlib.import_module("src.core.rate_limiter")
            RateLimitManager = rate_limiter_mod.RateLimitManager

            redis_mod = importlib.import_module("src.core.redis")
            redis_manager = redis_mod.redis_manager

            if not redis_manager.is_connected:
                await redis_manager.connect()

            client = redis_manager.get_client()
            if client:
                self._manager = RateLimitManager(
                    client,
                    tiers=self._tiers,
                    fail_open=settings.RATE_LIMIT_FAIL_OPEN
                )
                self._register_endpoint_limits()
                logger.info("Redis rate limit middleware initialized")

        except Exception as e:
            logger.warning(f"Failed to initialize Redis rate limiter: {e}")

        self._initialized = True
        return self._manager

    def _register_endpoint_limits(self) -> None:
        """Register special endpoint rate limits."""
        if not self._manager:
            return

        # Register auth endpoints
        self._manager.register_endpoint_limit(
            "/api/v1/auth/login", "POST",
            settings.RATE_LIMIT_AUTH_PER_MINUTE, 60
        )
        self._manager.register_endpoint_limit(
            "/api/v1/auth/register", "POST",
            settings.RATE_LIMIT_AUTH_PER_MINUTE // 2, 60
        )

        # Register execution endpoints
        self._manager.register_endpoint_limit(
            "/api/v1/executions", "POST",
            settings.RATE_LIMIT_EXECUTE_PER_MINUTE, 60
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""

        # Skip if rate limiting disabled
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Skip exempt paths
        if is_exempt(request.url.path):
            return await call_next(request)

        # Check bypass
        if should_bypass(request):
            response = await call_next(request)
            response.headers["X-RateLimit-Bypass"] = "true"
            return response

        # Get client identifier
        client_ip = get_client_ip(request)
        if not client_ip:
            return await call_next(request)

        # Get user info
        user_id, tier = get_user_from_request(request)

        # Try Redis-based rate limiting
        manager = await self._ensure_manager()

        if manager:
            return await self._check_redis_rate_limit(
                request, call_next, manager,
                client_ip, user_id, tier
            )
        else:
            # Fall back to in-memory (fail-open) or fail-closed
            if settings.RATE_LIMIT_FAIL_OPEN:
                logger.debug("Rate limiter unavailable, failing open")
                return await call_next(request)
            else:
                rate_limiter_mod = importlib.import_module("src.core.rate_limiter")
                RateLimitResult = rate_limiter_mod.RateLimitResult
                return self._rate_limit_response(
                    RateLimitResult(
                        allowed=False,
                        limit=0,
                        remaining=0,
                        reset_at=int(time.time() + 60),
                        retry_after=60
                    ),
                    "Rate limiting service unavailable"
                )

    async def _check_redis_rate_limit(
        self,
        request: Request,
        call_next: Callable,
        manager: Any,
        client_ip: str,
        user_id: Optional[str],
        tier: str
    ) -> Response:
        """Check rate limits using Redis backend."""

        path = request.url.path
        method = request.method

        # Check for endpoint-specific limit first
        endpoint_limit = get_endpoint_limit(path, method)

        if endpoint_limit:
            rate_limiter_mod = importlib.import_module("src.core.rate_limiter")
            RateLimitConfig = rate_limiter_mod.RateLimitConfig
            RateLimitScope = rate_limiter_mod.RateLimitScope
            RateLimitAlgorithm = rate_limiter_mod.RateLimitAlgorithm

            category, requests, window = endpoint_limit
            config = RateLimitConfig(
                requests=requests,
                window_seconds=window,
                scope=RateLimitScope.COMPOSITE,
                key_prefix=f"ep:{category}",
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW_COUNTER
            )

            # Use user_id if available, otherwise IP
            identifier = user_id or client_ip
            result = await manager._limiter.check(identifier, config)

            if not result.allowed:
                return self._rate_limit_response(
                    result,
                    f"Rate limit exceeded for {category} operations"
                )

        # Check tier-based limit
        if user_id:
            result = await manager.check_user(user_id, tier, "minute")
        else:
            result = await manager.check_ip(
                client_ip,
                requests=self._tiers.get(tier, self._tiers["anonymous"]).requests_per_minute,
                window_seconds=60
            )

        if not result.allowed:
            return self._rate_limit_response(result)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        for header, value in result.to_headers().items():
            response.headers[header] = value

        # Add tier info header
        response.headers["X-RateLimit-Tier"] = tier

        return response

    def _rate_limit_response(
        self,
        result: Any,
        message: str = "Rate limit exceeded"
    ) -> JSONResponse:
        """Create rate limit exceeded response."""
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "success": False,
                "message": message,
                "error_code": "RATE_LIMIT_EXCEEDED",
                "details": {
                    "limit": result.limit,
                    "remaining": result.remaining,
                    "reset_at": result.reset_at,
                    "retry_after_seconds": result.retry_after or 60
                }
            },
            headers=result.to_headers()
        )


# ============================================================
# FALLBACK IN-MEMORY RATE LIMITER (for development)
# ============================================================

class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting for development only.

    WARNING: Does not work across multiple instances!
    Use Redis-based rate limiting in production.
    """

    def __init__(
        self,
        app,
        requests_per_window: int = 100,
        window_seconds: int = 60
    ):
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        if is_exempt(request.url.path):
            return await call_next(request)

        if should_bypass(request):
            return await call_next(request)

        client_ip = get_client_ip(request)
        if not client_ip:
            return await call_next(request)

        now = time.time()
        window_start = now - self.window_seconds

        # Clean old entries
        if client_ip in self._requests:
            self._requests[client_ip] = [
                t for t in self._requests[client_ip] if t > window_start
            ]
        else:
            self._requests[client_ip] = []

        request_count = len(self._requests[client_ip])

        if request_count >= self.requests_per_window:
            retry_after = int(
                self.window_seconds - (now - self._requests[client_ip][0])
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "message": "Rate limit exceeded",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "retry_after_seconds": retry_after
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.requests_per_window),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + retry_after))
                }
            )

        self._requests[client_ip].append(now)

        response = await call_next(request)

        remaining = self.requests_per_window - len(self._requests[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(now + self.window_seconds))

        return response


# ============================================================
# FACTORY FUNCTION
# ============================================================

def create_rate_limit_middleware(app) -> BaseHTTPMiddleware:
    """
    Create appropriate rate limit middleware based on settings.

    Returns Redis-based middleware for production,
    falls back to in-memory for development if configured.
    """
    if settings.RATE_LIMIT_BACKEND == "memory":
        logger.warning(
            "Using in-memory rate limiting - "
            "NOT suitable for production with multiple instances!"
        )
        return InMemoryRateLimitMiddleware(
            app,
            requests_per_window=settings.RATE_LIMIT_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS
        )

    return RedisRateLimitMiddleware(app)
