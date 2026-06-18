"""PubSub interface.

Business/API code depends only on this Protocol; the concrete backend is chosen
once at startup by src.core.runtime.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, AsyncIterator, Optional


@runtime_checkable
class PubSub(Protocol):
    async def publish(self, channel: str, message: str) -> int:
        """Publishes a message to a channel.

        Returns:
            Number of subscribers that received the message
        """
        ...

    async def subscribe(
        self,
        channel: str,
        timeout: Optional[float] = None
    ) -> AsyncIterator[str]:
        """Subscribes to a channel and yields messages."""
        ...

    async def health_check(self) -> dict:
        """Performs health check on the pub/sub connection."""
        ...
