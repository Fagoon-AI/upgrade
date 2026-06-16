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
    assert settings.JWT_SECRET
    assert settings.encryption_key
    assert (tmp_path / "config.json").exists()

    rt = await build_runtime(settings)
    try:
        assert rt.redis is None
        assert rt.limiter.__class__.__name__ == "MemoryRateLimiter"
        assert rt.queue.__class__.__name__ == "InlineTaskQueueWithSyncSupport"
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
        Settings(data_dir=str(tmp_path), lite_mode=False, REDIS_URL="")
