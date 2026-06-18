"""
Mock Redis implementation for testing.

Provides an in-memory Redis-like interface for tests
without requiring a real Redis instance.
"""

from typing import Optional, Any, Dict, Set
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock


class FakeRedisManager:
    """
    In-memory Redis mock for testing.

    Supports common Redis operations:
    - String operations (get, set, delete)
    - Expiration (with simulated TTL)
    - Increment/decrement
    - Key existence checks
    - Key pattern matching

    Usage:
        redis = FakeRedisManager()
        await redis.set("key", "value", ex=60)
        value = await redis.get("key")
    """

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, datetime] = {}
        self._sets: Dict[str, Set[str]] = {}
        self._hashes: Dict[str, Dict[str, Any]] = {}

    def _is_expired(self, key: str) -> bool:
        """Check if a key has expired."""
        if key not in self._expiry:
            return False
        return datetime.now(timezone.utc) > self._expiry[key]

    def _cleanup_expired(self):
        """Remove expired keys."""
        now = datetime.now(timezone.utc)
        expired = [k for k, exp in self._expiry.items() if now > exp]
        for key in expired:
            self._data.pop(key, None)
            self._expiry.pop(key, None)
            self._sets.pop(key, None)
            self._hashes.pop(key, None)

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        self._cleanup_expired()
        if self._is_expired(key):
            return None
        value = self._data.get(key)
        if isinstance(value, bytes):
            return value.decode('utf-8')
        return value

    async def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        Set key-value pair.

        Args:
            key: Key name
            value: Value to store
            ex: Expiry in seconds
            px: Expiry in milliseconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists
        """
        self._cleanup_expired()

        # Handle nx (only if not exists)
        if nx and key in self._data:
            return False

        # Handle xx (only if exists)
        if xx and key not in self._data:
            return False

        self._data[key] = value

        # Set expiry
        if ex:
            self._expiry[key] = datetime.now(timezone.utc) + timedelta(seconds=ex)
        elif px:
            self._expiry[key] = datetime.now(timezone.utc) + timedelta(milliseconds=px)

        return True

    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        """Set key with expiry in seconds."""
        return await self.set(key, value, ex=seconds)

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                self._expiry.pop(key, None)
                count += 1
        return count

    async def exists(self, *keys: str) -> int:
        """Check if keys exist."""
        self._cleanup_expired()
        return sum(1 for key in keys if key in self._data and not self._is_expired(key))

    async def incr(self, key: str) -> int:
        """Increment key value."""
        self._cleanup_expired()
        current = int(self._data.get(key, 0))
        self._data[key] = current + 1
        return self._data[key]

    async def decr(self, key: str) -> int:
        """Decrement key value."""
        self._cleanup_expired()
        current = int(self._data.get(key, 0))
        self._data[key] = current - 1
        return self._data[key]

    async def incrby(self, key: str, amount: int) -> int:
        """Increment key by amount."""
        self._cleanup_expired()
        current = int(self._data.get(key, 0))
        self._data[key] = current + amount
        return self._data[key]

    async def expire(self, key: str, seconds: int) -> bool:
        """Set key expiry."""
        if key in self._data:
            self._expiry[key] = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            return True
        return False

    async def ttl(self, key: str) -> int:
        """Get remaining TTL in seconds."""
        if key not in self._expiry:
            return -1 if key in self._data else -2
        remaining = self._expiry[key] - datetime.now(timezone.utc)
        return max(0, int(remaining.total_seconds()))

    async def keys(self, pattern: str = "*") -> list[str]:
        """Get keys matching pattern."""
        self._cleanup_expired()
        import fnmatch
        return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]

    async def mget(self, *keys: str) -> list[Optional[str]]:
        """Get multiple keys."""
        return [await self.get(key) for key in keys]

    async def mset(self, mapping: Dict[str, Any]) -> bool:
        """Set multiple key-value pairs."""
        for key, value in mapping.items():
            await self.set(key, value)
        return True

    # Hash operations
    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field."""
        self._cleanup_expired()
        if name not in self._hashes:
            return None
        return self._hashes[name].get(key)

    async def hset(self, name: str, key: str = None, value: Any = None, mapping: Dict[str, Any] = None) -> int:
        """Set hash field(s)."""
        if name not in self._hashes:
            self._hashes[name] = {}

        count = 0
        if key is not None:
            if key not in self._hashes[name]:
                count = 1
            self._hashes[name][key] = value

        if mapping:
            for k, v in mapping.items():
                if k not in self._hashes[name]:
                    count += 1
                self._hashes[name][k] = v

        return count

    async def hgetall(self, name: str) -> Dict[str, Any]:
        """Get all hash fields."""
        self._cleanup_expired()
        return self._hashes.get(name, {})

    async def hdel(self, name: str, *keys: str) -> int:
        """Delete hash fields."""
        if name not in self._hashes:
            return 0
        count = 0
        for key in keys:
            if key in self._hashes[name]:
                del self._hashes[name][key]
                count += 1
        return count

    # Set operations
    async def sadd(self, key: str, *values: str) -> int:
        """Add to set."""
        if key not in self._sets:
            self._sets[key] = set()
        before = len(self._sets[key])
        self._sets[key].update(values)
        return len(self._sets[key]) - before

    async def srem(self, key: str, *values: str) -> int:
        """Remove from set."""
        if key not in self._sets:
            return 0
        before = len(self._sets[key])
        self._sets[key] -= set(values)
        return before - len(self._sets[key])

    async def smembers(self, key: str) -> Set[str]:
        """Get set members."""
        return self._sets.get(key, set())

    async def sismember(self, key: str, value: str) -> bool:
        """Check set membership."""
        return value in self._sets.get(key, set())

    # Utility methods
    async def flushdb(self) -> bool:
        """Clear all data."""
        self._data.clear()
        self._expiry.clear()
        self._sets.clear()
        self._hashes.clear()
        return True

    async def ping(self) -> str:
        """Health check."""
        return "PONG"

    async def health_check(self) -> dict:
        """Return health status."""
        return {
            "status": "healthy",
            "keys_count": len(self._data),
            "type": "fake_redis",
        }

    def clear(self):
        """Clear all data (sync version for setup/teardown)."""
        self._data.clear()
        self._expiry.clear()
        self._sets.clear()
        self._hashes.clear()


def create_mock_redis() -> AsyncMock:
    """
    Create an AsyncMock with Redis-like interface.

    Useful when you need a simple mock without full FakeRedis behavior.

    Returns:
        AsyncMock configured for Redis operations
    """
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=0)
    mock.incr = AsyncMock(return_value=1)
    mock.decr = AsyncMock(return_value=0)
    mock.expire = AsyncMock(return_value=True)
    mock.ttl = AsyncMock(return_value=-1)
    mock.keys = AsyncMock(return_value=[])
    mock.ping = AsyncMock(return_value="PONG")
    mock.health_check = AsyncMock(return_value={"status": "healthy"})
    return mock
