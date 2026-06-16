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
    for k in ("REDIS_URL", "JWT_SECRET", "ENCRYPTION_KEY", "DATABASE_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
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
    settings = ensure_bootstrap(get_settings(env_file=None), env_file=None)

    # Secrets were auto-generated and persisted.
    assert settings.jwt_secret
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
    for k in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LITE_MODE", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.core.settings import Settings

    with pytest.raises(ValueError):
        Settings(data_dir=str(tmp_path), lite_mode=False, REDIS_URL="", _env_file=None)


def test_fastapi_app_imports_and_loads_routers(tmp_path, monkeypatch):
    """Full-app import test verifying that under a standard Lite Mode environment,
    the complete FastAPI application mounts and registers all routers successfully
    with zero transitive dependencies or validation failures on boot."""
    monkeypatch.setenv("LITE_MODE", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DATABASE_URL_DEFAULT",
        "postgresql+asyncpg://test:test@localhost:5432/test",
    )
    monkeypatch.setenv("WEB_CONCURRENCY", "1")

    from src.core.settings import get_settings
    get_settings.cache_clear()

    from src.launch_server import app

    assert app.routes
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    
    # Verify that crucial routers and endpoints are fully loaded
    assert any("/webhook" in p for p in paths)
    assert any("/video-generation" in p for p in paths)
    assert any("/database/switch" in p for p in paths)


@pytest.mark.asyncio
async def test_webhook_roundtrip_lite(tmp_path, monkeypatch):
    """End-to-end integration test of the webhook path in Lite Mode.
    Verifies that a POST request successfully passes routing, bypasses Auth, normalizes
    the WhatsApp Meta payload, enqueues the event into the REAL InlineTaskQueueWithSyncSupport,
    and triggers the registered task mock-callback cleanly in the background."""
    monkeypatch.setenv("LITE_MODE", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DATABASE_URL_DEFAULT",
        "postgresql+asyncpg://test:test@localhost:5432/test",
    )
    monkeypatch.setenv("WEB_CONCURRENCY", "1")

    from src.core.bootstrap import ensure_bootstrap
    from src.core.settings import get_settings
    get_settings.cache_clear()

    # Pre-build our isolated settings object and override get_settings during lifespan startup
    settings = ensure_bootstrap(get_settings(env_file=None), env_file=None)
    monkeypatch.setattr("src.launch_server.get_settings", lambda: settings)

    from src.launch_server import app
    from httpx import AsyncClient, ASGITransport
    import asyncio
    from unittest.mock import AsyncMock

    # Setup the spy handler and completion event
    task_event = asyncio.Event()
    mock_task_handler = AsyncMock()

    async def spy_handler(*args, **kwargs):
        await mock_task_handler(*args, **kwargs)
        task_event.set()

    # Manually boot and run the app lifespan inside our test's async loop
    async with app.router.lifespan_context(app):
        # Retrieve the real, lifespanned queue and confirm its class
        real_queue = app.state.queue
        assert real_queue.__class__.__name__ == "InlineTaskQueueWithSyncSupport"

        # Register our spy handler directly into the real queue's registry
        real_queue.register("process_webhook_message_task", spy_handler)

        # Set up other state mock dependencies
        app.state.agent_manager = AsyncMock()
        app.state.agent_manager.get_agent = AsyncMock(return_value={
            "user_id": "12345678-1234-5678-1234-567812345678"
        })
        app.state.agent_chat_service = AsyncMock()

        # Mock signature/duplicate/history gateway helper methods
        from src.services.channel_adapter.webhook_gateway import WebhookGatewayService
        
        monkeypatch.setattr(WebhookGatewayService, "_verify_signature", AsyncMock(return_value=None))
        monkeypatch.setattr(WebhookGatewayService, "_is_duplicate", AsyncMock(return_value=False))
        monkeypatch.setattr(WebhookGatewayService, "_get_or_create_history_id", AsyncMock(return_value="history_123"))

        # Valid WhatsApp Webhook Payload
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "msg_123",
                                        "from": "sender_123",
                                        "type": "text",
                                        "text": {
                                            "body": "Hello Fagoon"
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        # Send the raw POST request via ASGI transport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/webhook/whatsapp/agent_abc",
                json=payload,
                headers={"x-hub-signature-256": "sha256=mock_sig"}
            )

        assert response.status_code == 200
        assert response.json() == {"status": "accepted", "message_id": "msg_123"}

        # Wait for the background queue task execution event with a 1.0s timeout
        await asyncio.wait_for(task_event.wait(), timeout=1.0)

        # Confirm the mock handler was called by the REAL InlineTaskQueueWithSyncSupport registry!
        mock_task_handler.assert_called_once()
        args, _ = mock_task_handler.call_args
        event_data = args[0]
        assert event_data["channel"] == "whatsapp"
        assert event_data["agent_id"] == "agent_abc"
        assert event_data["message_id"] == "msg_123"
        assert event_data["sender_id"] == "sender_123"
        assert event_data["text"] == "Hello Fagoon"
        assert event_data["history_id"] == "history_123"
        assert event_data["owner_user_id"] == "12345678-1234-5678-1234-567812345678"


