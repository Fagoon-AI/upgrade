# Fagoon Dual-Mode — Gemini CLI Implementation Instructions

> **How to use this file:** Hand it to Gemini CLI as the task. Execute phases **in order**. Each phase lists exact files to create (full content in code blocks) and exact edits to existing files. Do not skip a phase, and after each phase run its verification command before moving on. The single rule the whole design depends on: **business code never imports `redis` or `celery` directly — it calls `app.state.limiter`, `app.state.queue`, `app.state.cache`.** Only the four backend modules, `runtime.py`, and `celery_app.py` may import those packages.

**Non-negotiable invariants:**
1. With `LITE_MODE=false` the app must behave exactly as it does today.
2. In lite mode, no environment variable may be *required* — secrets auto-generate, DB URL falls back to the bundled DSN.
3. Lite mode is single-process: `WEB_CONCURRENCY=1`, enforced at startup.

---

## Phase 0 — Branch and baseline

**Goal:** Set up a working branch and confirm the project runs before any change. Every later phase must keep the app working in its current (full) behavior.

Run these in the project root:

```bash
git checkout -b feat/dual-mode
git status
```

Confirm the existing app currently starts (full mode, with the project's current Redis/Celery setup). Do NOT change behavior yet. If there is no test runner configured, install dev tooling:

```bash
uv add --dev pytest pytest-asyncio import-linter ruff
```

Do not delete or rewrite any existing file in this phase.

---

## Phase 1 — Config foundation (settings + bootstrap)

**Goal:** Add the layered settings resolver and first-boot secret bootstrap. With LITE_MODE unset/false, behavior is unchanged. This phase adds new files only.


**Create `src/core/settings.py`:**

````python
"""Application settings with a layered resolver.

Precedence (highest first):
    1. Explicit constructor kwargs (used internally)
    2. Environment variables  -> contributors set these via .env
    3. .env file
    4. <DATA_DIR>/config.json  -> package mode persists generated values here
    5. Hardcoded field defaults

The same class serves both audiences: a contributor's env wins, while a
package user who sets nothing still boots on file + default layers.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class JsonConfigSource(PydanticBaseSettingsSource):
    """Lowest-priority source (above field defaults): reads persisted config
    written by the bootstrap step at <DATA_DIR>/config.json."""

    def __init__(self, settings_cls, path: Path):
        super().__init__(settings_cls)
        self._path = path

    def get_field_value(self, field, field_name):  # abstract, unused here
        return None, field_name, False

    def __call__(self) -> dict:
        try:
            return json.loads(self._path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}


class Settings(BaseSettings):
    # --- mode ---
    lite_mode: bool = False
    data_dir: str = "/data"
    web_concurrency: int = 1

    # --- infra (all optional; resolved below) ---
    database_url: str = ""
    database_url_default: str = ""  # bundled DSN injected by compose in lite mode
    redis_url: str = ""

    # --- secrets (auto-generated on first boot if empty) ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    encryption_key: str = ""

    # --- feature gating ---
    features: str = "chat,agents,workflow,vibecoder"

    # --- integrations (optional; may also be set via the UI) ---
    openai_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    ollama_base_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        data_dir = Path(
            init_settings.init_kwargs.get("data_dir")
            or os.environ.get("DATA_DIR")
            or "/data"
        )
        json_source = JsonConfigSource(settings_cls, data_dir / "config.json")
        return (init_settings, env_settings, dotenv_settings, json_source)

    @property
    def enabled_features(self) -> set[str]:
        return {f.strip() for f in self.features.split(",") if f.strip()}

    def feature_enabled(self, name: str) -> bool:
        return name in self.enabled_features

    @model_validator(mode="after")
    def _resolve(self):
        # DB url falls back to the bundled DSN (lite mode) when nothing explicit.
        if not self.database_url and self.database_url_default:
            self.database_url = self.database_url_default

        # Full mode requires Redis: fail loud rather than silently degrade.
        if not self.lite_mode and not self.redis_url:
            raise ValueError(
                "redis_url is required when LITE_MODE is false. "
                "Set REDIS_URL, or run with LITE_MODE=true."
            )
        # Lite mode ignores redis_url even if present (explicit contract).
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings(data_dir=os.environ.get("DATA_DIR", "/data"))
````

**Create `src/core/bootstrap.py`:**

````python
"""First-boot bootstrap.

Generates infra secrets (JWT secret, Fernet encryption key) on first run and
persists them to <DATA_DIR>/config.json so they survive container restarts.
This is what lets a package user install with zero environment variables.

User-supplied integration secrets (LLM keys, Google OAuth) are NOT handled here.
Those are entered via the UI and stored encrypted in the DB `credentials` table
using the encryption_key generated below. The database URL is the one pointer
that must live in config.json, because it points AT the DB and cannot live
inside it.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

from src.core.settings import Settings, get_settings


def ensure_bootstrap(settings: Settings) -> Settings:
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = data_dir / "config.json"

    cfg: dict = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            cfg = {}

    changed = False

    if not settings.jwt_secret and not cfg.get("jwt_secret"):
        cfg["jwt_secret"] = secrets.token_urlsafe(48)
        changed = True

    if not settings.encryption_key and not cfg.get("encryption_key"):
        cfg["encryption_key"] = Fernet.generate_key().decode()
        changed = True

    # Persist the resolved DB url so it is stable across restarts.
    if not cfg.get("database_url") and settings.database_url:
        cfg["database_url"] = settings.database_url
        changed = True

    if changed:
        cfg_path.write_text(json.dumps(cfg, indent=2))
        cfg_path.chmod(0o600)

    # Re-read so freshly written values are picked up by the json source.
    get_settings.cache_clear()
    return get_settings()
````

If the project already has a `src/core/settings.py`, do NOT overwrite blindly. Instead:
1. Open the existing settings file and read it.
2. Merge the fields and the `settings_customise_sources` / `_resolve` / `JsonConfigSource` logic from the version above into it, keeping any project-specific fields already present.
3. Ensure `get_settings()` is an `lru_cache`d accessor.

Add the runtime dependency for secret generation if missing:

```bash
uv add cryptography
```

After this phase, verify nothing broke:

```bash
uv run python -c "from src.core.settings import get_settings; print(get_settings().enabled_features)"
```

---

## Phase 2 — Rate limiter abstraction

**Goal:** Introduce the limiter interface with a Redis backend (full mode) and an in-memory backend (lite mode). No call sites change yet.


**Create `src/services/limiter/__init__.py`:** empty file (package marker — `touch src/services/limiter/__init__.py`).

**Create `src/services/limiter/base.py`:**

````python
"""Rate limiter interface. Business code depends only on this Protocol;
the concrete backend is chosen once at startup by src.core.runtime."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    async def allow(self, key: str, limit: int, window_s: int) -> bool:
        """Return True if this hit is within `limit` per rolling `window_s`
        seconds for `key`, and record it. Return False to reject."""
        ...
````

**Create `src/services/limiter/memory_limiter.py`:**

````python
"""In-memory sliding-window rate limiter (LITE MODE).

Correct ONLY in a single process. Lite mode pins WEB_CONCURRENCY=1 and that
invariant is asserted at startup. With multiple workers, counts fragment.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_s
        q = self._hits[key]
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def sweep(self) -> int:
        """Drop empty keys to bound memory. Call periodically. Returns count removed."""
        empty = [k for k, q in self._hits.items() if not q]
        for k in empty:
            del self._hits[k]
        return len(empty)
````

**Create `src/services/limiter/redis_limiter.py`:**

````python
"""Redis-backed sliding-window rate limiter (FULL MODE).

This is the ONLY limiter module permitted to import redis (enforced by
import-linter). Move any existing Redis limiter logic you have into here.

Uses a sorted set per key with millisecond-resolution timestamps and a single
atomic pipeline: drop expired members, count, conditionally add, set TTL.
"""
from __future__ import annotations

import time


class RedisRateLimiter:
    def __init__(self, redis) -> None:
        self._redis = redis  # redis.asyncio client

    async def allow(self, key: str, limit: int, window_s: int) -> bool:
        now_ms = int(time.time() * 1000)
        window_ms = window_s * 1000
        member = f"{now_ms}-{id(object())}"
        rkey = f"ratelimit:{key}"

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(rkey, 0, now_ms - window_ms)
        pipe.zcard(rkey)
        results = await pipe.execute()
        count = results[1]

        if count >= limit:
            return False

        pipe = self._redis.pipeline()
        pipe.zadd(rkey, {member: now_ms})
        pipe.expire(rkey, window_s + 1)
        await pipe.execute()
        return True
````

If the project already has Redis rate-limiting logic somewhere, move that exact logic into `RedisRateLimiter.allow()` (replace the sorted-set implementation above only if you have a preferred one). Leave existing call sites untouched for now — they get migrated in Phase 6.

`src/services/limiter/__init__.py` should be empty (package marker).

---

## Phase 3 — Task queue abstraction

**Goal:** Introduce the task-queue interface with a Celery backend (full mode) and an inline asyncio backend (lite mode).


**Create `src/services/taskqueue/__init__.py`:** empty file (package marker — `touch src/services/taskqueue/__init__.py`).

**Create `src/services/taskqueue/base.py`:**

````python
"""Background task queue interface. Routes/services enqueue work through this;
the backend (Celery in full mode, asyncio inline in lite mode) is chosen at
startup. Job STATUS is always tracked in Postgres regardless of backend, so the
WebSocket status broadcaster is identical across modes."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


@runtime_checkable
class TaskQueue(Protocol):
    def enqueue(
        self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> str:
        """Schedule `fn(*args, **kwargs)` to run in the background.
        Returns an opaque job id immediately (does not await the work)."""
        ...
````

**Create `src/services/taskqueue/inline_queue.py`:**

````python
"""Inline asyncio task queue (LITE MODE).

Runs the coroutine in the current event loop and returns a job id immediately.
Caveat: a job dies if the process restarts mid-run. Acceptable for a single
self-hosted user. Long video renders in lite mode therefore have no retry; the
DB row stays PROCESSING until the broadcaster/timeout marks it FAILED.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)


class InlineTaskQueue:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def enqueue(
        self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> str:
        job_id = str(uuid.uuid4())
        task = asyncio.create_task(self._run(job_id, fn, *args, **kwargs))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job_id

    async def _run(self, job_id, fn, *args, **kwargs) -> None:
        try:
            await fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - log and swallow; status lives in DB
            log.exception("inline job %s failed", job_id)

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
````

**Create `src/services/taskqueue/celery_queue.py`:**

````python
"""Celery-backed task queue (FULL MODE).

The ONLY taskqueue module permitted to import celery (enforced by import-linter).

Because Celery serializes tasks by name (not arbitrary coroutines), register
your real jobs as Celery tasks elsewhere (e.g. generate_video_task) and map the
callable passed to enqueue() onto the matching registered task. The simplest
robust pattern is a name registry: pass a registered task, or look it up by
fn.__name__. Adapt to your existing celery_app task definitions.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable


class CeleryTaskQueue:
    def __init__(self, celery_app, task_registry: dict[str, Any] | None = None) -> None:
        self._celery = celery_app
        # maps a plain function name -> registered celery task (.delay-able)
        self._registry = task_registry or {}

    def register(self, name: str, celery_task) -> None:
        self._registry[name] = celery_task

    def enqueue(
        self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> str:
        name = getattr(fn, "__name__", str(fn))
        task = self._registry.get(name)
        if task is None:
            raise KeyError(
                f"No Celery task registered for '{name}'. "
                f"Register it via CeleryTaskQueue.register('{name}', the_task)."
            )
        async_result = task.delay(*args, **kwargs)
        return async_result.id
````

`CeleryTaskQueue` dispatches by task name via a registry. In Phase 5 you will register the project's real Celery tasks (e.g. the video generation task) onto it. `src/services/taskqueue/__init__.py` is an empty package marker.

---

## Phase 4 — Cache abstraction

**Goal:** Introduce the cache interface with Redis and in-memory backends. Only add these if the project uses Redis for caching/ephemeral state; otherwise still add them (they are cheap and used by the runtime factory).


**Create `src/services/cache/__init__.py`:** empty file (package marker — `touch src/services/cache/__init__.py`).

**Create `src/services/cache/base.py`:**

````python
"""Cache / ephemeral key-value interface. Redis in full mode, in-process dict
with TTL in lite mode."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_s: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
````

**Create `src/services/cache/memory_cache.py`:**

````python
"""In-memory TTL cache (LITE MODE). Single-process only."""
from __future__ import annotations

import time
from typing import Any


class MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float | None, Any]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        expires_at = time.monotonic() + ttl_s if ttl_s else None
        self._store[key] = (expires_at, value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
````

**Create `src/services/cache/redis_cache.py`:**

````python
"""Redis-backed cache (FULL MODE). One of the few modules allowed to import
redis. Values are JSON-encoded so any JSON-serializable payload round-trips."""
from __future__ import annotations

import json
from typing import Any


class RedisCache:
    def __init__(self, redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> Any | None:
        raw = await self._redis.get(f"cache:{key}")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return raw

    async def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        raw = json.dumps(value)
        if ttl_s:
            await self._redis.set(f"cache:{key}", raw, ex=ttl_s)
        else:
            await self._redis.set(f"cache:{key}", raw)

    async def delete(self, key: str) -> None:
        await self._redis.delete(f"cache:{key}")
````

`src/services/cache/__init__.py` is an empty package marker.

---

## Phase 5 — Runtime factory + lifespan wiring

**Goal:** Add the single place that reads LITE_MODE and binds backends, then attach them to app.state in the FastAPI lifespan. This is the heart of the dual-mode design.


**Create `src/core/runtime.py`:**

````python
"""Runtime factory.

Reads LITE_MODE once and binds each interface to a concrete backend. This is
the single place where mode branching happens. Everything else in the app talks
to app.state.{limiter,queue,cache,redis} without knowing which mode is active.

This module and the *_limiter / *_cache / celery_queue backend modules are the
ONLY places permitted to import redis or celery (enforced by import-linter).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.core.settings import Settings
from src.services.cache.memory_cache import MemoryCache
from src.services.cache.redis_cache import RedisCache
from src.services.limiter.memory_limiter import MemoryRateLimiter
from src.services.limiter.redis_limiter import RedisRateLimiter
from src.services.taskqueue.celery_queue import CeleryTaskQueue
from src.services.taskqueue.inline_queue import InlineTaskQueue

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    limiter: Any
    queue: Any
    cache: Any
    redis: Any | None  # None in lite mode

    async def shutdown(self) -> None:
        if hasattr(self.queue, "shutdown"):
            await self.queue.shutdown()
        if self.redis is not None:
            await self.redis.aclose()


async def build_runtime(settings: Settings) -> Runtime:
    if settings.lite_mode:
        log.info("Building LITE runtime: in-memory limiter/cache, inline queue, no Redis.")
        return Runtime(
            limiter=MemoryRateLimiter(),
            queue=InlineTaskQueue(),
            cache=MemoryCache(),
            redis=None,
        )

    log.info("Building FULL runtime: Redis limiter/cache, Celery queue.")
    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    # Import your existing Celery app and register tasks onto the queue.
    # from src.core.celery_app import celery_app, generate_video_task
    # queue = CeleryTaskQueue(celery_app)
    # queue.register("run_video_job", generate_video_task)
    from src.core.celery_app import celery_app  # noqa: provided by your codebase

    queue = CeleryTaskQueue(celery_app)
    return Runtime(
        limiter=RedisRateLimiter(redis_client),
        queue=queue,
        cache=RedisCache(redis_client),
        redis=redis_client,
    )
````

**Edit the existing `src/launch_server.py`** (do not create a new one). Inside the existing `lifespan` async context manager, near the top where other singletons are set up, add:

```python
from src.core.settings import get_settings
from src.core.bootstrap import ensure_bootstrap
from src.core.runtime import build_runtime

# inside lifespan, before yield:
settings = ensure_bootstrap(get_settings())
app.state.settings = settings

# Hard invariant: lite mode is single-process only.
if settings.lite_mode and settings.web_concurrency != 1:
    raise RuntimeError(
        "LITE_MODE requires WEB_CONCURRENCY=1. In-memory limiter/queue "
        "fragment across workers. Use full mode for concurrency."
    )

rt = await build_runtime(settings)
app.state.limiter = rt.limiter
app.state.queue = rt.queue
app.state.cache = rt.cache
app.state.redis = rt.redis
```

And in the teardown section (after `yield`), add:

```python
await rt.shutdown()
```

**In `src/core/runtime.py`, wire the real Celery tasks.** Find the commented block in the full-mode branch and replace it with the project's actual imports, for example:

```python
from src.core.celery_app import celery_app, generate_video_task
queue = CeleryTaskQueue(celery_app)
queue.register("run_video_job", generate_video_task)
```

Match the registry key (`"run_video_job"`) to the function name you pass to `app.state.queue.enqueue(...)` in Phase 6.

---

## Phase 6 — Migrate call sites

**Goal:** Replace every direct Redis/Celery usage in routers and services with the app.state interfaces. This is mechanical; the guardrails in Phase 7 will tell you if you miss any.

Search the codebase and replace:

```bash
# find direct usages
git grep -nE "(import|from)\s+(redis|celery)" -- "src/**/*.py"
git grep -n "\.delay(" -- "src/**/*.py"
```

Replacement patterns:

```python
# rate limiting — before:
#   await redis.incr(key) ... / custom redis limiter call
# after:
if not await request.app.state.limiter.allow(client_ip, limit=60, window_s=60):
    raise HTTPException(status_code=429, detail="rate limited")

# background work — before:
#   generate_video_task.delay(job_id)
# after:
request.app.state.queue.enqueue(run_video_job, job_id)

# cache — before:
#   await redis.get(k) / await redis.set(k, v)
# after:
await request.app.state.cache.get(k)
await request.app.state.cache.set(k, v, ttl_s=300)
```

Leave the four approved backend modules and `runtime.py` and `celery_app.py` importing redis/celery — those are the only files allowed to. Everything else must go through `app.state`. Job status writes to Postgres stay exactly as they are.

---

## Phase 7 — Guardrails (architecture + lite-boot tests)

**Goal:** Add the automated checks that make it impossible for a contributor to silently break lite mode: import-linter contracts, a grep guard, and the zero-env boot test.


**Create `importlinter.ini`:**

````ini
[importlinter]
root_package = src

[importlinter:contract:no-direct-redis]
name = Only backend modules may import redis
type = forbidden
source_modules =
    src.api
    src.services.agents
    src.services.tool_handlers
    src.services.google_workspace
forbidden_modules =
    redis

[importlinter:contract:no-direct-celery]
name = Only the celery backend may import celery
type = forbidden
source_modules =
    src.api
    src.services.agents
    src.services.tool_handlers
forbidden_modules =
    celery
````

**Create `scripts/guard_imports.sh`:**

````bash
#!/usr/bin/env bash
# Fails if redis/celery are imported outside the approved backend modules.
# Backup to import-linter; catches string-level cases too.
set -euo pipefail

if git grep -nE '^[[:space:]]*(import|from)[[:space:]]+(redis|celery)' -- \
     'src/**/*.py' \
     ':(exclude)src/services/limiter/redis_limiter.py' \
     ':(exclude)src/services/cache/redis_cache.py' \
     ':(exclude)src/services/taskqueue/celery_queue.py' \
     ':(exclude)src/core/runtime.py' \
     ':(exclude)src/core/celery_app.py'; then
  echo "ERROR: redis/celery imported outside approved backend modules."
  echo "Route the dependency through an interface in src/services/* instead."
  exit 1
fi
echo "import guard passed"
````

**Create `tests/__init__.py`:** empty file (package marker — `touch tests/__init__.py`).

**Create `tests/test_lite_boot.py`:**

````python
"""Guardrail test: the app must boot in lite mode with NO env and NO Redis.

If a contributor adds a hard Redis dependency or a newly-required env var, the
first test fails. The second enforces the single-process invariant.

Note: this test exercises mode WIRING, not DB connectivity. If your real
lifespan opens a live Postgres connection, either provide one via CI services
(see ci.yml) or monkeypatch the postgres_manager init. The asserts below check
the runtime backends regardless.
"""
import pytest


@pytest.mark.asyncio
async def test_app_boots_with_no_env_no_redis(tmp_path, monkeypatch):
    # Strip anything that could mask a hard dependency.
    for k in ("REDIS_URL", "JWT_SECRET", "ENCRYPTION_KEY", "DATABASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LITE_MODE", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DATABASE_URL_DEFAULT",
        "postgresql+asyncpg://test:test@localhost:5432/test",
    )
    monkeypatch.setenv("WEB_CONCURRENCY", "1")

    from src.core.bootstrap import ensure_bootstrap
    from src.core.runtime import build_runtime
    from src.core.settings import get_settings

    get_settings.cache_clear()
    settings = ensure_bootstrap(get_settings())

    # Secrets were auto-generated and persisted.
    assert settings.jwt_secret
    assert settings.encryption_key
    assert (tmp_path / "config.json").exists()

    rt = await build_runtime(settings)
    try:
        assert rt.redis is None
        assert rt.limiter.__class__.__name__ == "MemoryRateLimiter"
        assert rt.queue.__class__.__name__ == "InlineTaskQueue"
        assert rt.cache.__class__.__name__ == "MemoryCache"

        # The limiter actually limits.
        assert await rt.limiter.allow("k", limit=2, window_s=60) is True
        assert await rt.limiter.allow("k", limit=2, window_s=60) is True
        assert await rt.limiter.allow("k", limit=2, window_s=60) is False
    finally:
        await rt.shutdown()


def test_full_mode_requires_redis(tmp_path, monkeypatch):
    for k in ("REDIS_URL",):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LITE_MODE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.core.settings import Settings

    with pytest.raises(ValueError):
        Settings(data_dir=str(tmp_path), lite_mode=False, redis_url="")
````

Make the guard script executable and run all three checks locally:

```bash
chmod +x scripts/guard_imports.sh
uv run lint-imports
bash scripts/guard_imports.sh
uv run pytest tests/test_lite_boot.py -q
```

`tests/__init__.py` is an empty package marker. If `lint-imports` reports violations, go back to Phase 6 and route those imports through `app.state`. If the boot test needs a live Postgres, either run one locally or set `DATABASE_URL_DEFAULT` to a reachable test DB; the test checks mode wiring, not data.

---

## Phase 8 — Packaging (Docker, compose, CLI, project metadata)

**Goal:** Make the app installable and runnable: optional dependency extras, a console script, the Docker image, the entrypoint, both compose files, and the fagoon CLI.


**Create `pyproject.toml`:**

````toml
[project]
name = "fagoon"
version = "0.1.0"
description = "Fagoon AI Agents Workflow - self-hostable, single-command install."
requires-python = ">=3.12"
dependencies = [
  "fastapi",
  "uvicorn[standard]",
  "sqlalchemy[asyncio]",
  "asyncpg",
  "pgvector",
  "alembic",
  "pydantic-settings",
  "cryptography",
  "httpx",
  "typer",
]

[project.optional-dependencies]
full = ["celery[redis]", "redis", "eventlet"]   # only needed in full mode
dev  = ["pytest", "pytest-asyncio", "import-linter", "ruff"]

[project.scripts]
fagoon = "fagoon_cli.main:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src", "fagoon_cli"]
````

**Create `deploy/Dockerfile`:**

````
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --extra full || uv sync --extra full

COPY . .
RUN chmod +x deploy/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["deploy/entrypoint.sh"]
````

**Create `deploy/entrypoint.sh`:**

````bash
#!/usr/bin/env bash
set -euo pipefail
uv run alembic upgrade head
WORKERS="${WEB_CONCURRENCY:-1}"
exec uv run uvicorn src.launch_server:app \
  --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
````

**Create `deploy/docker-compose.yml`:**

````yaml
# LITE MODE - single user, no Redis, no Celery. References the PUBLISHED image.
services:
  app:
    image: ghcr.io/you/fagoon:1.2.0       # PINNED, not :latest
    restart: unless-stopped
    ports: ["8000:8000"]
    environment:
      LITE_MODE: "true"
      DATA_DIR: /data
      DATABASE_URL_DEFAULT: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
      WEB_CONCURRENCY: "1"
    command: >
      uvicorn src.launch_server:app --host 0.0.0.0 --port 8000 --workers 1
    volumes: ["fagoon_data:/data"]
    depends_on:
      db: { condition: service_healthy }

  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: fagoon
      POSTGRES_PASSWORD: fagoon
      POSTGRES_DB: fagoon
    volumes: ["fagoon_db:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fagoon"]
      interval: 5s
      timeout: 5s
      retries: 10

  ollama:
    image: ollama/ollama:latest
    profiles: ["ollama"]
    restart: unless-stopped
    ports: ["11434:11434"]
    volumes: ["fagoon_ollama:/root/.ollama"]

volumes:
  fagoon_data:
  fagoon_db:
  fagoon_ollama:
````

**Create `deploy/docker-compose.full.yml`:**

````yaml
# FULL MODE - Redis + Celery worker. For contributors and multi-worker setups.
services:
  app:
    build: { context: .., dockerfile: deploy/Dockerfile }
    restart: unless-stopped
    ports: ["8000:8000"]
    environment:
      LITE_MODE: "false"
      DATA_DIR: /data
      DATABASE_URL: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/1
      WEB_CONCURRENCY: "2"
    volumes: ["fagoon_data:/data"]
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }

  worker:
    build: { context: .., dockerfile: deploy/Dockerfile }
    command: uv run celery -A src.core.celery_app worker -P eventlet -c 50
    environment:
      LITE_MODE: "false"
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/1
      DATABASE_URL: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
    depends_on:
      redis: { condition: service_started }
      db: { condition: service_healthy }

  redis:
    image: redis:7-alpine
    restart: unless-stopped

  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: fagoon
      POSTGRES_PASSWORD: fagoon
      POSTGRES_DB: fagoon
    volumes: ["fagoon_db:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fagoon"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  fagoon_data:
  fagoon_db:
````

**Create `fagoon_cli/__init__.py`:** empty file (package marker — `touch fagoon_cli/__init__.py`).

**Create `fagoon_cli/main.py`:**

````python
"""fagoon CLI - a thin wrapper over Docker Compose so package users get an
n8n-like one-command experience without learning Compose.

Install:   pipx install fagoon
Usage:
    fagoon up                       start the stack (lite mode by default)
    fagoon up --full                start with Redis + Celery worker
    fagoon up --ollama              also start the Ollama fallback LLM
    fagoon down                     stop the stack
    fagoon logs [-f]                tail logs
    fagoon config set KEY=VALUE     write to <DATA_DIR>/config.json
    fagoon db set-url URL           repoint the database and run migrations
    fagoon update                   pull the newest pinned image and restart

This wrapper ships its own bundled compose files inside the package so the user
never has to download anything by hand.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(add_completion=False, help="Fagoon self-hosted control CLI.")

# Compose files are packaged alongside the CLI.
PKG_DIR = Path(__file__).resolve().parent
COMPOSE_LITE = PKG_DIR / "compose" / "docker-compose.yml"
COMPOSE_FULL = PKG_DIR / "compose" / "docker-compose.full.yml"

DATA_DIR = Path(os.environ.get("FAGOON_DATA_DIR", Path.home() / ".fagoon"))
CONFIG_PATH = DATA_DIR / "config.json"


def _compose_bin() -> list[str]:
    if shutil.which("docker") is None:
        typer.secho("Docker is not installed or not on PATH.", fg="red")
        raise typer.Exit(1)
    return ["docker", "compose"]


def _run(args: list[str]) -> None:
    typer.secho("$ " + " ".join(args), fg="bright_black")
    result = subprocess.run(args)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    CONFIG_PATH.chmod(0o600)


@app.command()
def up(
    full: bool = typer.Option(False, "--full", help="Run with Redis + Celery worker."),
    ollama: bool = typer.Option(False, "--ollama", help="Also start the Ollama fallback."),
):
    """Start the Fagoon stack."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    compose_file = COMPOSE_FULL if full else COMPOSE_LITE
    args = [*_compose_bin(), "-f", str(compose_file)]
    if ollama:
        args += ["--profile", "ollama"]
    args += ["up", "-d"]
    env = os.environ.copy()
    env["FAGOON_DATA_DIR"] = str(DATA_DIR)
    typer.secho(f"Starting Fagoon ({'full' if full else 'lite'} mode)...", fg="green")
    _run(args)
    typer.secho("Up. Open http://localhost:8000", fg="green")


@app.command()
def down(full: bool = typer.Option(False, "--full")):
    """Stop the Fagoon stack."""
    compose_file = COMPOSE_FULL if full else COMPOSE_LITE
    _run([*_compose_bin(), "-f", str(compose_file), "down"])


@app.command()
def logs(follow: bool = typer.Option(False, "-f", "--follow")):
    """Show stack logs."""
    args = [*_compose_bin(), "-f", str(COMPOSE_LITE), "logs"]
    if follow:
        args.append("-f")
    _run(args)


config_app = typer.Typer(help="Read/write persisted config.")
app.add_typer(config_app, name="config")


@config_app.command("set")
def config_set(pair: str = typer.Argument(..., help="KEY=VALUE")):
    """Set a config value in <DATA_DIR>/config.json."""
    if "=" not in pair:
        typer.secho("Expected KEY=VALUE", fg="red")
        raise typer.Exit(1)
    key, value = pair.split("=", 1)
    cfg = _load_config()
    cfg[key.strip()] = value.strip()
    _save_config(cfg)
    typer.secho(f"Set {key.strip()}.", fg="green")


@config_app.command("show")
def config_show():
    """Print current config (secrets redacted)."""
    cfg = _load_config()
    redacted = {
        k: ("***" if any(s in k.lower() for s in ("secret", "key", "password")) else v)
        for k, v in cfg.items()
    }
    typer.echo(json.dumps(redacted, indent=2))


db_app = typer.Typer(help="Database management.")
app.add_typer(db_app, name="db")


@db_app.command("set-url")
def db_set_url(url: str = typer.Argument(..., help="postgresql+asyncpg://...")):
    """Repoint the database URL and trigger migrations on next restart."""
    cfg = _load_config()
    cfg["database_url"] = url
    _save_config(cfg)
    typer.secho("Database URL saved. Restart to migrate: fagoon down && fagoon up", fg="yellow")


@app.command()
def update():
    """Pull the newest pinned image and restart."""
    _run([*_compose_bin(), "-f", str(COMPOSE_LITE), "pull"])
    _run([*_compose_bin(), "-f", str(COMPOSE_LITE), "up", "-d"])
    typer.secho("Updated.", fg="green")


def main():
    app()


if __name__ == "__main__":
    sys.exit(main())
````

**Create `fagoon_cli/compose/docker-compose.yml`:**

````yaml
# LITE MODE - single user, no Redis, no Celery. References the PUBLISHED image.
services:
  app:
    image: ghcr.io/you/fagoon:1.2.0       # PINNED, not :latest
    restart: unless-stopped
    ports: ["8000:8000"]
    environment:
      LITE_MODE: "true"
      DATA_DIR: /data
      DATABASE_URL_DEFAULT: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
      WEB_CONCURRENCY: "1"
    command: >
      uvicorn src.launch_server:app --host 0.0.0.0 --port 8000 --workers 1
    volumes: ["fagoon_data:/data"]
    depends_on:
      db: { condition: service_healthy }

  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: fagoon
      POSTGRES_PASSWORD: fagoon
      POSTGRES_DB: fagoon
    volumes: ["fagoon_db:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fagoon"]
      interval: 5s
      timeout: 5s
      retries: 10

  ollama:
    image: ollama/ollama:latest
    profiles: ["ollama"]
    restart: unless-stopped
    ports: ["11434:11434"]
    volumes: ["fagoon_ollama:/root/.ollama"]

volumes:
  fagoon_data:
  fagoon_db:
  fagoon_ollama:
````

**Create `fagoon_cli/compose/docker-compose.full.yml`:**

````yaml
# FULL MODE - Redis + Celery worker. For contributors and multi-worker setups.
services:
  app:
    build: { context: .., dockerfile: deploy/Dockerfile }
    restart: unless-stopped
    ports: ["8000:8000"]
    environment:
      LITE_MODE: "false"
      DATA_DIR: /data
      DATABASE_URL: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/1
      WEB_CONCURRENCY: "2"
    volumes: ["fagoon_data:/data"]
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }

  worker:
    build: { context: .., dockerfile: deploy/Dockerfile }
    command: uv run celery -A src.core.celery_app worker -P eventlet -c 50
    environment:
      LITE_MODE: "false"
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/1
      DATABASE_URL: postgresql+asyncpg://fagoon:fagoon@db:5432/fagoon
    depends_on:
      redis: { condition: service_started }
      db: { condition: service_healthy }

  redis:
    image: redis:7-alpine
    restart: unless-stopped

  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: fagoon
      POSTGRES_PASSWORD: fagoon
      POSTGRES_DB: fagoon
    volumes: ["fagoon_db:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fagoon"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  fagoon_data:
  fagoon_db:
````

**Create `.env.example`:**

````bash
# ---- Mode ----
# Contributors typically run full mode. Leave LITE_MODE unset/false here.
LITE_MODE=false
DATA_DIR=./data
WEB_CONCURRENCY=2

# ---- Infra (required in full mode) ----
DATABASE_URL=postgresql+asyncpg://fagoon:fagoon@localhost:5432/fagoon
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ---- Secrets (auto-generated in package mode; set explicitly for dev) ----
JWT_SECRET=change-me-in-dev
JWT_ALGORITHM=HS256
ENCRYPTION_KEY=                 # leave empty to auto-generate a Fernet key

# ---- Feature gating ----
FEATURES=chat,agents,workflow,vibecoder

# ---- Integrations (optional; can also be set via the UI) ----
OPENAI_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
OLLAMA_BASE_URL=
````

**Create `README.md`:**

````markdown
# Fagoon

Self-hostable AI agents + workflow platform. Two ways to run:

## Package users (one command)
```bash
pipx install fagoon
fagoon up                 # lite mode: no Redis, no Celery, zero env required
fagoon up --ollama        # add the local Gemma fallback LLM
```
Open http://localhost:8000 and complete the setup wizard (LLM key + features).
Secrets are auto-generated; the database URL and config live in `~/.fagoon`.

## Contributors (clone + run)
```bash
git clone https://github.com/you/fagoon
cp .env.example .env      # fill minimal values
docker compose -f deploy/docker-compose.full.yml up --build
```

## Two modes
- **Lite** (default package): in-memory limiter/cache, inline asyncio jobs,
  single process. Best for one user. Video generation runs in-process.
- **Full**: Redis + Celery worker, multi-worker. Best for concurrency.

Mode is selected by `LITE_MODE` and resolved once at startup in
`src/core/runtime.py`. Business code never imports redis/celery directly;
that rule is enforced in CI by import-linter (`importlinter.ini`).

See `DUAL_MODE_IMPLEMENTATION.md` for the full design and refactor guide.
````

If a `pyproject.toml` already exists, MERGE these into it rather than overwriting: the `[project.optional-dependencies]` (`full`, `dev`), the `[project.scripts]` `fagoon` entry, and the `[tool.pytest.ini_options]` block. Keep the project's existing dependencies.

Make the entrypoint executable:

```bash
chmod +x deploy/entrypoint.sh
```

Replace the placeholder `ghcr.io/you/fagoon:1.2.0` in BOTH compose files (and the bundled copies under `fagoon_cli/compose/`) with the real `ghcr.io/<owner>/<repo>` and the version you intend to ship.

Add the CLI runtime dependency:

```bash
uv add typer
```

Smoke-test the CLI help:

```bash
uv run fagoon --help
```

---

## Phase 9 — GitHub automation (CI + release + governance)

**Goal:** Add the workflows and governance files. CI runs on PRs and main and publishes nothing; release runs only on version tags.


**Create `.github/workflows/ci.yml`:**

````yaml
name: ci

# Runs on every PR and on main. Publishes NOTHING. These jobs are the required
# status checks that block a PR which would break lite mode or the architecture.

on:
  pull_request:
  push:
    branches: [main]

jobs:
  tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U test"
          --health-interval 5s --health-timeout 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-extras --dev
      - run: uv run pytest -q
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test

  lite-boot:
    # Deliberately installs WITHOUT the `full` extra. If any non-backend module
    # imports redis/celery, this fails at import time - a dependency-level proof
    # that lite mode is self-contained.
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U test"
          --health-interval 5s --health-timeout 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --dev          # no --extra full
      - run: uv run pytest tests/test_lite_boot.py -q
        env:
          DATABASE_URL_DEFAULT: postgresql+asyncpg://test:test@localhost:5432/test

  architecture:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-extras --dev
      - run: uv run lint-imports
      - run: bash scripts/guard_imports.sh
````

**Create `.github/workflows/release.yml`:**

````yaml
name: release

# Fires ONLY on version tags (v1.2.0). Pushes to main publish nothing.
# This tag boundary is what keeps contributor commits off users' installs.

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read
  packages: write

env:
  IMAGE: ghcr.io/${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U test"
          --health-interval 5s --health-timeout 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-extras --dev
      - run: uv run pytest -q
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test

  image:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Derive version from tag
        id: ver
        run: echo "version=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push (multi-arch)
        uses: docker/build-push-action@v6
        with:
          context: .
          file: deploy/Dockerfile
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ${{ env.IMAGE }}:${{ steps.ver.outputs.version }}
            ${{ env.IMAGE }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  pypi:
    needs: test
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write   # OIDC trusted publishing; no stored token
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1

  github-release:
    needs: [image, pypi]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
````

**Create `.github/CODEOWNERS`:**

````
# Changes to the mode machinery require maintainer review even if CI passes.
/src/core/runtime.py        @you
/src/core/settings.py       @you
/src/core/bootstrap.py      @you
/src/services/limiter/      @you
/src/services/taskqueue/    @you
/src/services/cache/        @you
/importlinter.ini           @you
/scripts/guard_imports.sh   @you
/.github/workflows/         @you
````

**Create `.github/pull_request_template.md`:**

````markdown
## What this changes


## Lite-mode contract checklist
- [ ] No direct `redis` / `celery` import outside approved backend modules
- [ ] New background work goes through `app.state.queue`, not Celery directly
- [ ] New shared state has a lite (in-memory) backend, not Redis-only
- [ ] No new *required* env var (must have a safe default or config.json path)
- [ ] `uv run pytest` and `uv run lint-imports` pass locally
````

Replace `@you` in `.github/CODEOWNERS` with the maintainer's GitHub handle. Replace `ghcr.io/you/fagoon` references if any remain. Commit everything:

```bash
git add -A
git commit -m "feat: dual-mode (lite/full) runtime, packaging, CI/release guardrails"
```

The manual GitHub setup that is NOT code (do these in the GitHub UI, not via Gemini):
1. Branch protection on `main`: require PR review + the `tests`, `lite-boot`, `architecture` status checks.
2. PyPI trusted publishing: register repo + workflow `release.yml` + environment `pypi`; create a protected `pypi` environment in repo settings.
3. After the first tagged release, set the GHCR package visibility to public.

Cut the first release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

---
