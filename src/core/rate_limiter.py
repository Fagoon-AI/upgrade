"""
Distributed Rate Limiter using Redis.

Implements multiple rate limiting algorithms:
1. Sliding Window Log - Most accurate, higher memory
2. Sliding Window Counter - Good balance of accuracy and efficiency
3. Token Bucket - Best for handling bursts

Supports multiple scopes:
- Per IP address (default)
- Per authenticated user
- Per API key
- Per endpoint
- Custom composite keys

Production Features:
- Redis cluster support
- Graceful degradation (fail-open when Redis unavailable)
- Atomic operations using Lua scripts
- Configurable limits per tier (free/pro/enterprise)
- Rate limit headers (X-RateLimit-*)
- Retry-After header on limit exceeded
"""

import time
import hashlib
from typing import Optional, Dict, Any, Tuple, List, Callable
from enum import Enum
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

import redis.asyncio as redis
from loguru import logger


# ============================================================
# CONFIGURATION
# ============================================================

class RateLimitAlgorithm(str, Enum):
    """Available rate limiting algorithms."""
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    TOKEN_BUCKET = "token_bucket"
    FIXED_WINDOW = "fixed_window"


class RateLimitScope(str, Enum):
    """Rate limit scope identifiers."""
    GLOBAL = "global"
    IP = "ip"
    USER = "user"
    API_KEY = "api_key"
    ENDPOINT = "endpoint"
    COMPOSITE = "composite"


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""
    requests: int  # Max requests allowed
    window_seconds: int  # Time window in seconds
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW_COUNTER
    scope: RateLimitScope = RateLimitScope.IP
    burst_size: Optional[int] = None  # For token bucket
    key_prefix: str = "rl"
    fail_open: bool = True  # Allow requests if Redis unavailable
    skip_successful_requests: bool = False  # Only count failed requests

    @property
    def bucket_refill_rate(self) -> float:
        """Tokens per second for token bucket algorithm."""
        return self.requests / self.window_seconds


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: Optional[int] = None  # Seconds until next allowed request
    current_count: int = 0

    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at),
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        return headers


@dataclass
class RateLimitTier:
    """Rate limit configuration per user tier."""
    name: str
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_allowance: int = 10  # Extra requests allowed in burst


# Default tiers
DEFAULT_TIERS = {
    "anonymous": RateLimitTier("anonymous", 30, 500, 5000, 5),
    "free": RateLimitTier("free", 60, 1000, 10000, 10),
    "pro": RateLimitTier("pro", 300, 5000, 50000, 50),
    "enterprise": RateLimitTier("enterprise", 1000, 20000, 200000, 100),
}


# ============================================================
# LUA SCRIPTS FOR ATOMIC OPERATIONS
# ============================================================

# Sliding Window Counter - Most efficient for distributed systems
SLIDING_WINDOW_COUNTER_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

local window_start = now - window
local current_window = math.floor(now / window) * window
local previous_window = current_window - window

local current_key = key .. ":" .. current_window
local previous_key = key .. ":" .. previous_window

-- Get counts from both windows
local current_count = tonumber(redis.call("GET", current_key) or "0")
local previous_count = tonumber(redis.call("GET", previous_key) or "0")

-- Calculate weighted count using sliding window
local elapsed = now - current_window
local weight = (window - elapsed) / window
local weighted_count = math.floor(previous_count * weight) + current_count

if weighted_count >= limit then
    -- Calculate when the limit will reset
    local reset_at = current_window + window
    return {0, weighted_count, limit - weighted_count, reset_at}
end

-- Increment current window counter
redis.call("INCR", current_key)
redis.call("EXPIRE", current_key, window * 2)

return {1, weighted_count + 1, limit - weighted_count - 1, current_window + window}
"""

# Sliding Window Log - Most accurate but higher memory usage
SLIDING_WINDOW_LOG_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

local window_start = now - window

-- Remove expired entries
redis.call("ZREMRANGEBYSCORE", key, "-inf", window_start)

-- Count requests in current window
local count = redis.call("ZCARD", key)

if count >= limit then
    -- Get oldest entry to calculate retry_after
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    local retry_after = 0
    if oldest and #oldest >= 2 then
        retry_after = math.ceil(tonumber(oldest[2]) + window - now)
    end
    return {0, count, 0, now + retry_after, retry_after}
end

-- Add current request
redis.call("ZADD", key, now, now .. ":" .. math.random(1000000))
redis.call("EXPIRE", key, window + 1)

return {1, count + 1, limit - count - 1, now + window, 0}
"""

# Token Bucket - Best for burst handling
TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local bucket_size = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])  -- tokens per second
local requested = tonumber(ARGV[4]) or 1

-- Get current bucket state
local bucket = redis.call("HMGET", key, "tokens", "last_update")
local tokens = tonumber(bucket[1])
local last_update = tonumber(bucket[2])

-- Initialize bucket if not exists
if not tokens then
    tokens = bucket_size
    last_update = now
end

-- Calculate tokens to add based on time elapsed
local elapsed = now - last_update
local tokens_to_add = elapsed * refill_rate
tokens = math.min(bucket_size, tokens + tokens_to_add)

-- Check if we have enough tokens
if tokens < requested then
    -- Calculate when tokens will be available
    local tokens_needed = requested - tokens
    local wait_time = math.ceil(tokens_needed / refill_rate)
    return {0, math.floor(tokens), bucket_size, now + wait_time, wait_time}
end

-- Consume tokens
tokens = tokens - requested
redis.call("HMSET", key, "tokens", tokens, "last_update", now)
redis.call("EXPIRE", key, math.ceil(bucket_size / refill_rate) + 60)

return {1, math.floor(tokens), bucket_size, now + math.ceil((bucket_size - tokens) / refill_rate), 0}
"""

# Fixed Window - Simplest but can have edge case issues
FIXED_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

local window_key = key .. ":" .. math.floor(now / window)
local count = tonumber(redis.call("GET", window_key) or "0")

if count >= limit then
    local reset_at = (math.floor(now / window) + 1) * window
    return {0, count, 0, reset_at}
end

redis.call("INCR", window_key)
redis.call("EXPIRE", window_key, window + 1)

local reset_at = (math.floor(now / window) + 1) * window
return {1, count + 1, limit - count - 1, reset_at}
"""


# ============================================================
# RATE LIMITER IMPLEMENTATION
# ============================================================

class RateLimiter:
    """
    Distributed rate limiter using Redis.

    Thread-safe and supports horizontal scaling across multiple
    application instances.

    Usage:
        limiter = RateLimiter(redis_client)

        # Check rate limit
        result = await limiter.check("user:123", config)
        if not result.allowed:
            return 429, result.to_headers()

        # Or use as decorator
        @limiter.limit(requests=100, window_seconds=60)
        async def my_endpoint():
            ...
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        key_prefix: str = "ratelimit",
        fail_open: bool = True
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client instance
            key_prefix: Prefix for all rate limit keys
            fail_open: Allow requests if Redis is unavailable
        """
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._fail_open = fail_open
        self._scripts: Dict[RateLimitAlgorithm, Any] = {}

    async def _ensure_scripts(self) -> None:
        """Register Lua scripts with Redis."""
        if self._scripts:
            return

        try:
            self._scripts[RateLimitAlgorithm.SLIDING_WINDOW_COUNTER] = \
                self._redis.register_script(SLIDING_WINDOW_COUNTER_SCRIPT)
            self._scripts[RateLimitAlgorithm.SLIDING_WINDOW_LOG] = \
                self._redis.register_script(SLIDING_WINDOW_LOG_SCRIPT)
            self._scripts[RateLimitAlgorithm.TOKEN_BUCKET] = \
                self._redis.register_script(TOKEN_BUCKET_SCRIPT)
            self._scripts[RateLimitAlgorithm.FIXED_WINDOW] = \
                self._redis.register_script(FIXED_WINDOW_SCRIPT)
        except Exception as e:
            logger.error(f"Failed to register rate limit scripts: {e}")

    def _build_key(self, identifier: str, config: RateLimitConfig) -> str:
        """Build Redis key for rate limiting."""
        # Hash long identifiers to keep key length manageable
        if len(identifier) > 64:
            identifier = hashlib.sha256(identifier.encode()).hexdigest()[:16]

        return f"{self._key_prefix}:{config.key_prefix}:{identifier}"

    async def check(
        self,
        identifier: str,
        config: RateLimitConfig
    ) -> RateLimitResult:
        """
        Check if request is allowed under rate limit.

        Args:
            identifier: Unique identifier (IP, user ID, API key, etc.)
            config: Rate limit configuration

        Returns:
            RateLimitResult with allowed status and metadata
        """
        try:
            await self._ensure_scripts()

            key = self._build_key(identifier, config)
            now = time.time()

            script = self._scripts.get(config.algorithm)
            if not script:
                logger.error(f"Unknown algorithm: {config.algorithm}")
                return self._fail_open_result(config)

            # Execute appropriate algorithm
            if config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                result = await script(
                    keys=[key],
                    args=[
                        now,
                        config.burst_size or config.requests,
                        config.bucket_refill_rate,
                        1
                    ]
                )
            else:
                result = await script(
                    keys=[key],
                    args=[now, config.window_seconds, config.requests]
                )

            allowed = bool(result[0])
            current_count = int(result[1])
            remaining = int(result[2])
            reset_at = int(result[3])
            retry_after = int(result[4]) if len(result) > 4 and result[4] else None

            return RateLimitResult(
                allowed=allowed,
                limit=config.requests,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after if not allowed else None,
                current_count=current_count
            )

        except redis.ConnectionError as e:
            logger.warning(f"Redis connection error in rate limiter: {e}")
            if config.fail_open:
                return self._fail_open_result(config)
            return self._fail_closed_result(config)

        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            if config.fail_open:
                return self._fail_open_result(config)
            return self._fail_closed_result(config)

    async def check_multiple(
        self,
        checks: List[Tuple[str, RateLimitConfig]]
    ) -> Tuple[bool, RateLimitResult]:
        """
        Check multiple rate limits (e.g., per-minute AND per-hour).

        Returns the most restrictive result.

        Args:
            checks: List of (identifier, config) tuples

        Returns:
            Tuple of (all_allowed, most_restrictive_result)
        """
        results = []
        for identifier, config in checks:
            result = await self.check(identifier, config)
            results.append(result)

        # Find most restrictive (lowest remaining)
        most_restrictive = min(results, key=lambda r: r.remaining)

        # All must be allowed
        all_allowed = all(r.allowed for r in results)

        return all_allowed, most_restrictive

    async def reset(self, identifier: str, config: RateLimitConfig) -> bool:
        """
        Reset rate limit for an identifier.

        Useful for admin operations or after successful auth.
        """
        try:
            key = self._build_key(identifier, config)

            if config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                await self._redis.delete(key)
            elif config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_LOG:
                await self._redis.delete(key)
            else:
                # Delete both current and previous windows
                now = time.time()
                window = config.window_seconds
                current_window = int(now / window) * window
                previous_window = current_window - window
                await self._redis.delete(
                    f"{key}:{current_window}",
                    f"{key}:{previous_window}"
                )

            logger.info(f"Rate limit reset for {identifier}")
            return True

        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")
            return False

    async def get_status(
        self,
        identifier: str,
        config: RateLimitConfig
    ) -> Dict[str, Any]:
        """
        Get current rate limit status without consuming a request.
        """
        try:
            key = self._build_key(identifier, config)
            now = time.time()

            if config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_LOG:
                window_start = now - config.window_seconds
                await self._redis.zremrangebyscore(key, "-inf", window_start)
                count = await self._redis.zcard(key)
            elif config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                bucket = await self._redis.hmget(key, "tokens", "last_update")
                tokens = float(bucket[0] or config.requests)
                last_update = float(bucket[1] or now)
                elapsed = now - last_update
                tokens = min(
                    config.burst_size or config.requests,
                    tokens + elapsed * config.bucket_refill_rate
                )
                count = int((config.burst_size or config.requests) - tokens)
            else:
                current_window = int(now / config.window_seconds) * config.window_seconds
                current_key = f"{key}:{current_window}"
                count = int(await self._redis.get(current_key) or 0)

            return {
                "identifier": identifier,
                "limit": config.requests,
                "used": count,
                "remaining": max(0, config.requests - count),
                "reset_at": int(now + config.window_seconds),
                "algorithm": config.algorithm.value
            }

        except Exception as e:
            logger.error(f"Failed to get rate limit status: {e}")
            return {}

    def _fail_open_result(self, config: RateLimitConfig) -> RateLimitResult:
        """Result when failing open (allowing request)."""
        return RateLimitResult(
            allowed=True,
            limit=config.requests,
            remaining=config.requests,
            reset_at=int(time.time() + config.window_seconds),
            current_count=0
        )

    def _fail_closed_result(self, config: RateLimitConfig) -> RateLimitResult:
        """Result when failing closed (denying request)."""
        return RateLimitResult(
            allowed=False,
            limit=config.requests,
            remaining=0,
            reset_at=int(time.time() + config.window_seconds),
            retry_after=config.window_seconds,
            current_count=config.requests
        )


# ============================================================
# RATE LIMIT MANAGER (HIGH-LEVEL API)
# ============================================================

class RateLimitManager:
    """
    High-level rate limit manager with tier support.

    Provides easy-to-use methods for common rate limiting scenarios.

    Usage:
        manager = RateLimitManager(redis_client)

        # Check by IP
        result = await manager.check_ip("192.168.1.1")

        # Check by user with tier
        result = await manager.check_user(user_id="123", tier="pro")

        # Check by API key
        result = await manager.check_api_key("api_key_xxx")

        # Check endpoint-specific limit
        result = await manager.check_endpoint(
            identifier="user:123",
            endpoint="/api/v1/execute",
            method="POST"
        )
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        tiers: Optional[Dict[str, RateLimitTier]] = None,
        fail_open: bool = True
    ):
        self._limiter = RateLimiter(redis_client, fail_open=fail_open)
        self._tiers = tiers or DEFAULT_TIERS
        self._endpoint_limits: Dict[str, RateLimitConfig] = {}

    def register_endpoint_limit(
        self,
        endpoint: str,
        method: str,
        requests: int,
        window_seconds: int
    ) -> None:
        """Register a custom rate limit for a specific endpoint."""
        key = f"{method.upper()}:{endpoint}"
        self._endpoint_limits[key] = RateLimitConfig(
            requests=requests,
            window_seconds=window_seconds,
            scope=RateLimitScope.ENDPOINT,
            key_prefix=f"endpoint:{key.replace('/', '_')}"
        )

    async def check_ip(
        self,
        ip_address: str,
        requests: int = 100,
        window_seconds: int = 60
    ) -> RateLimitResult:
        """Check rate limit by IP address."""
        config = RateLimitConfig(
            requests=requests,
            window_seconds=window_seconds,
            scope=RateLimitScope.IP,
            key_prefix="ip"
        )
        return await self._limiter.check(ip_address, config)

    async def check_user(
        self,
        user_id: str,
        tier: str = "free",
        window: str = "minute"  # minute, hour, day
    ) -> RateLimitResult:
        """Check rate limit by user ID with tier-based limits."""
        tier_config = self._tiers.get(tier, self._tiers["free"])

        if window == "minute":
            requests = tier_config.requests_per_minute
            window_seconds = 60
        elif window == "hour":
            requests = tier_config.requests_per_hour
            window_seconds = 3600
        else:  # day
            requests = tier_config.requests_per_day
            window_seconds = 86400

        config = RateLimitConfig(
            requests=requests,
            window_seconds=window_seconds,
            scope=RateLimitScope.USER,
            key_prefix=f"user:{window}",
            burst_size=tier_config.burst_allowance + requests // 10
        )
        return await self._limiter.check(user_id, config)

    async def check_api_key(
        self,
        api_key: str,
        tier: str = "free"
    ) -> RateLimitResult:
        """Check rate limit by API key."""
        tier_config = self._tiers.get(tier, self._tiers["free"])

        config = RateLimitConfig(
            requests=tier_config.requests_per_minute,
            window_seconds=60,
            scope=RateLimitScope.API_KEY,
            key_prefix="apikey",
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            burst_size=tier_config.burst_allowance + tier_config.requests_per_minute // 10
        )

        # Hash API key for privacy
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        return await self._limiter.check(key_hash, config)

    async def check_endpoint(
        self,
        identifier: str,
        endpoint: str,
        method: str = "GET"
    ) -> RateLimitResult:
        """Check endpoint-specific rate limit."""
        key = f"{method.upper()}:{endpoint}"
        config = self._endpoint_limits.get(key)

        if not config:
            # Default endpoint limit
            config = RateLimitConfig(
                requests=100,
                window_seconds=60,
                scope=RateLimitScope.ENDPOINT,
                key_prefix=f"ep:{key.replace('/', '_')}"
            )

        composite_key = f"{identifier}:{key}"
        return await self._limiter.check(composite_key, config)

    async def check_composite(
        self,
        ip_address: str,
        user_id: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        method: str = "GET",
        tier: str = "free"
    ) -> Tuple[bool, RateLimitResult, Dict[str, RateLimitResult]]:
        """
        Check multiple rate limits at once.

        Returns most restrictive result and individual results.
        """
        results: Dict[str, RateLimitResult] = {}
        checks = []

        # Always check IP
        ip_result = await self.check_ip(ip_address)
        results["ip"] = ip_result
        if not ip_result.allowed:
            return False, ip_result, results

        # Check user if authenticated
        if user_id:
            user_result = await self.check_user(user_id, tier)
            results["user"] = user_result
            if not user_result.allowed:
                return False, user_result, results

        # Check API key if provided
        if api_key:
            key_result = await self.check_api_key(api_key, tier)
            results["api_key"] = key_result
            if not key_result.allowed:
                return False, key_result, results

        # Check endpoint if provided
        if endpoint:
            ep_result = await self.check_endpoint(
                user_id or ip_address,
                endpoint,
                method
            )
            results["endpoint"] = ep_result
            if not ep_result.allowed:
                return False, ep_result, results

        # Find most restrictive
        most_restrictive = min(results.values(), key=lambda r: r.remaining)
        return True, most_restrictive, results

    async def reset_user(self, user_id: str) -> bool:
        """Reset all rate limits for a user."""
        success = True
        for window in ["minute", "hour", "day"]:
            config = RateLimitConfig(
                requests=1,  # Doesn't matter for reset
                window_seconds=60,
                key_prefix=f"user:{window}"
            )
            if not await self._limiter.reset(user_id, config):
                success = False
        return success

    async def get_user_status(
        self,
        user_id: str,
        tier: str = "free"
    ) -> Dict[str, Any]:
        """Get rate limit status for a user across all windows."""
        status = {}
        for window in ["minute", "hour", "day"]:
            tier_config = self._tiers.get(tier, self._tiers["free"])

            if window == "minute":
                requests = tier_config.requests_per_minute
                window_seconds = 60
            elif window == "hour":
                requests = tier_config.requests_per_hour
                window_seconds = 3600
            else:
                requests = tier_config.requests_per_day
                window_seconds = 86400

            config = RateLimitConfig(
                requests=requests,
                window_seconds=window_seconds,
                key_prefix=f"user:{window}"
            )
            status[window] = await self._limiter.get_status(user_id, config)

        return status


# ============================================================
# FACTORY FUNCTION
# ============================================================

_manager_instance: Optional[RateLimitManager] = None


async def get_rate_limit_manager() -> RateLimitManager:
    """
    Get or create the rate limit manager singleton.

    Usage:
        manager = await get_rate_limit_manager()
        result = await manager.check_ip("192.168.1.1")
    """
    global _manager_instance

    if _manager_instance is None:
        from src.core.redis import redis_manager

        if not redis_manager.is_connected:
            await redis_manager.connect()

        client = redis_manager.get_client()
        if client is None:
            raise RuntimeError("Redis not available for rate limiting")

        _manager_instance = RateLimitManager(client)
        logger.info("Rate limit manager initialized")

    return _manager_instance


def reset_rate_limit_manager() -> None:
    """Reset the rate limit manager (for testing)."""
    global _manager_instance
    _manager_instance = None
