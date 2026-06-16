#!/usr/bin/env bash
set -euo pipefail
uv run alembic upgrade head
WORKERS="${WEB_CONCURRENCY:-1}"
exec uv run uvicorn src.launch_server:app \
  --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
