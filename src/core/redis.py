import asyncio
from typing import Optional, AsyncIterator, Callable, Awaitable, Any
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis.asyncio as redis
from redis.asyncio import ConnectionPool
from loguru import logger


class RedisConfig:
    """Redis connection configuration."""

    def __init__(
            self,
            host: str = "localhost",
            port: int = 6379,
            password: Optional[str] = None,
            ssl: bool = False,
            db: int = 0,
            max_connections: int = 50,
            socket_timeout: float = 5.0,
            socket_connect_timeout: float = 5.0,
            retry_on_timeout: bool = True,
            health_check_interval: int = 30
    ):
        self.host = host
        self.port = port
        self.password = password
        self.ssl = ssl
        self.db = db
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self.health_check_interval = health_check_interval

    @property
    def url(self) -> str:
        """Constructs Redis URL from config."""
        scheme = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"

    @classmethod
    def from_url(cls, url: str, **kwargs) -> 'RedisConfig':
        """Creates config from URL string."""
        config = cls(**kwargs)
        # Parse URL components
        if url.startswith("rediss://"):
            config.ssl = True
            url = url[9:]
        elif url.startswith("redis://"):
            url = url[8:]

        # Extract password if present
        if "@" in url:
            auth, url = url.split("@", 1)
            if ":" in auth:
                config.password = auth.split(":", 1)[1]

        # Extract host:port/db
        if "/" in url:
            url, db = url.rsplit("/", 1)
            config.db = int(db) if db else 0

        if ":" in url:
            config.host, port = url.rsplit(":", 1)
            config.port = int(port)
        else:
            config.host = url

        return config


class RedisManager:
    """
    Redis Connection Manager.

    Features:
    - Connection pooling for high concurrency
    - Automatic reconnection on failures
    - Pub/Sub with proper message handling
    - Health checks and monitoring
    - Graceful degradation when Redis unavailable

    Usage:
        # Initialize
        redis_manager = RedisManager(config)
        await redis_manager.connect()

        # Publish
        await redis_manager.publish("channel", "message")

        # Subscribe
        async for message in redis_manager.subscribe("channel"):
            print(message)

        # Cleanup
        await redis_manager.disconnect()
    """

    def __init__(self, config: Optional[RedisConfig] = None):
        """
        Initialize Redis manager.

        Args:
            config: Redis configuration. If None, loads from settings.
        """
        self._config = config
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._connected = False
        self._lock = asyncio.Lock()
        self._subscribers: dict = {}

    async def connect(self) -> bool:
        """
        Establishes connection pool to Redis.

        Returns:
            True if connected successfully, False otherwise
        """
        async with self._lock:
            if self._connected:
                return True

            try:
                # Load config if not provided
                if self._config is None:
                    try:
                        from src.core.config import settings
                        # Extract secret value if REDIS_PASSWORD is a SecretStr
                        redis_password = None
                        if settings.REDIS_PASSWORD:
                            redis_password = (
                                settings.REDIS_PASSWORD.get_secret_value()
                                if hasattr(settings.REDIS_PASSWORD, 'get_secret_value')
                                else settings.REDIS_PASSWORD
                            )
                        self._config = RedisConfig(
                            host=settings.REDIS_HOST,
                            port=settings.REDIS_PORT,
                            password=redis_password,
                            ssl=settings.REDIS_SSL
                        )
                    except ImportError:
                        logger.warning("Settings not available, using defaults")
                        self._config = RedisConfig()

                # Create connection pool
                self._pool = ConnectionPool(
                    host=self._config.host,
                    port=self._config.port,
                    password=self._config.password,
                    db=self._config.db,
                    max_connections=self._config.max_connections,
                    socket_timeout=self._config.socket_timeout,
                    socket_connect_timeout=self._config.socket_connect_timeout,
                    retry_on_timeout=self._config.retry_on_timeout,
                    health_check_interval=self._config.health_check_interval,
                    decode_responses=True,
                    connection_class=redis.SSLConnection if self._config.ssl else redis.Connection
                )

                # Create client with pool
                self._client = redis.Redis(connection_pool=self._pool)

                # Verify connection
                await self._client.ping()

                self._connected = True
                logger.info(f"🔌 Redis connected: {self._config.host}:{self._config.port}")
                return True

            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                self._connected = False
                return False

    async def disconnect(self) -> None:
        """Gracefully closes all Redis connections."""
        async with self._lock:
            # Cancel all subscriptions
            for pubsub in list(self._subscribers.values()):
                try:
                    await pubsub.unsubscribe()
                    await pubsub.close()
                except Exception:
                    pass
            self._subscribers.clear()

            # Close client
            if self._client:
                await self._client.close()
                self._client = None

            # Close pool
            if self._pool:
                await self._pool.disconnect()
                self._pool = None

            self._connected = False
            logger.info("🔌 Redis disconnected")

    async def ensure_connected(self) -> bool:
        """Ensures connection is active, reconnects if needed."""
        if not self._connected:
            return await self.connect()

        try:
            await self._client.ping()
            return True
        except Exception:
            self._connected = False
            return await self.connect()

    # PUB/SUB OPERATIONS

    async def publish(self, channel: str, message: str) -> int:
        """
        Publishes a message to a channel.

        Args:
            channel: Channel name
            message: Message to publish

        Returns:
            Number of subscribers that received the message
        """
        if not await self.ensure_connected():
            logger.warning(f"Redis unavailable, message to {channel} dropped")
            return 0

        try:
            return await self._client.publish(channel, message)
        except Exception as e:
            logger.error(f"Redis publish failed: {e}")
            return 0

    async def subscribe(
            self,
            channel: str,
            timeout: Optional[float] = None
    ) -> AsyncIterator[str]:
        """
        Subscribes to a channel and yields messages.

        Args:
            channel: Channel to subscribe to
            timeout: Optional timeout between messages

        Yields:
            Messages received on the channel
        """
        if not await self.ensure_connected():
            logger.error("Cannot subscribe: Redis not connected")
            return

        pubsub = self._client.pubsub()
        self._subscribers[channel] = pubsub

        try:
            await pubsub.subscribe(channel)
            logger.debug(f"📡 Subscribed to: {channel}")

            while True:
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=timeout or 60.0
                    )

                    if message and message.get("type") == "message":
                        yield message["data"]

                except asyncio.TimeoutError:
                    # No message within timeout, continue listening
                    # This allows checking if we should stop
                    continue
                except asyncio.CancelledError:
                    break

        except Exception as e:
            logger.error(f"Subscription error on {channel}: {e}")
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass
            self._subscribers.pop(channel, None)
            logger.debug(f"📡 Unsubscribed from: {channel}")

    @asynccontextmanager
    async def subscription(self, channel: str):
        """
        Context manager for subscriptions.

        Usage:
            async with redis_manager.subscription("channel") as sub:
                async for message in sub:
                    process(message)
        """
        if not await self.ensure_connected():
            raise ConnectionError("Redis not connected")

        pubsub = self._client.pubsub()

        try:
            await pubsub.subscribe(channel)

            async def message_generator():
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )
                    if message and message.get("type") == "message":
                        yield message["data"]
                    await asyncio.sleep(0.01)

            yield message_generator()

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    # BASIC OPERATIONS

    async def get(self, key: str) -> Optional[str]:
        """Gets a value from Redis."""
        if not await self.ensure_connected():
            return None
        try:
            return await self._client.get(key)
        except Exception as e:
            logger.error(f"Redis GET failed: {e}")
            return None

    async def set(
            self,
            key: str,
            value: str,
            ex: Optional[int] = None,
            px: Optional[int] = None,
            nx: bool = False,
            xx: bool = False
    ) -> bool:
        """
        Sets a value in Redis.

        Args:
            key: Key name
            value: Value to set
            ex: Expire time in seconds
            px: Expire time in milliseconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists
        """
        if not await self.ensure_connected():
            return False
        try:
            await self._client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
            return True
        except Exception as e:
            logger.error(f"Redis SET failed: {e}")
            return False

    async def delete(self, *keys: str) -> int:
        """Deletes keys from Redis."""
        if not await self.ensure_connected():
            return 0
        try:
            return await self._client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis DELETE failed: {e}")
            return 0

    async def expire(self, key: str, seconds: int) -> bool:
        """Sets expiration on a key."""
        if not await self.ensure_connected():
            return False
        try:
            return await self._client.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis EXPIRE failed: {e}")
            return False

    # HEALTH & MONITORING

    async def health_check(self) -> dict:
        """
        Performs health check on Redis connection.

        Returns:
            Dict with health status and metrics
        """
        try:
            if not await self.ensure_connected():
                return {
                    "status": "unhealthy",
                    "error": "Not connected",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            # Ping test
            start = asyncio.get_event_loop().time()
            await self._client.ping()
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000

            # Get info
            info = await self._client.info("server")

            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "pool_size": self._pool.max_connections if self._pool else 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def get_client(self) -> Optional[redis.Redis]:
        """Returns the underlying Redis client (for advanced usage)."""
        return self._client

    @property
    def is_connected(self) -> bool:
        """Returns connection status."""
        return self._connected


# GLOBAL SINGLETON
redis_manager = RedisManager()


async def get_redis() -> RedisManager:
    """
    FastAPI dependency for Redis manager.

    Usage:
        @app.get("/test")
        async def test(redis: RedisManager = Depends(get_redis)):
            await redis.publish("channel", "message")
    """
    if not redis_manager.is_connected:
        await redis_manager.connect()
    return redis_manager