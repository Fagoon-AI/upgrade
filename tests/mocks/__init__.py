"""
Mock utilities for external services.

Provides mock implementations for:
- Redis
- External APIs (Google, LLM providers)
- Celery tasks
"""

from tests.mocks.redis import FakeRedisManager
from tests.mocks.services import (
    MockAuthService,
    MockStorageService,
)

__all__ = [
    "FakeRedisManager",
    "MockAuthService",
    "MockStorageService",
]
