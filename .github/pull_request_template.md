## What this changes


## Lite-mode contract checklist
- [ ] No direct `redis` / `celery` import outside approved backend modules
- [ ] New background work goes through `app.state.queue`, not Celery directly
- [ ] New shared state has a lite (in-memory) backend, not Redis-only
- [ ] No new *required* env var (must have a safe default or config.json path)
- [ ] `uv run pytest` and `uv run lint-imports --config importlinter.ini` pass locally
