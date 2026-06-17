import os
import pytest

# Default LITE_MODE to true for testing to avoid requiring REDIS_URL when not testing full mode
os.environ.setdefault("LITE_MODE", "true")

@pytest.fixture(autouse=True)
def clear_settings_cache():
    from src.core.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
