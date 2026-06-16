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
     ':(exclude)src/core/task_processing/celery_app.py' \
     ':(exclude)src/core/task_processing/celery_tasks.py' \
     ':(exclude)src/core/task_processing/celery_worker_setup.py'; then
  echo "ERROR: redis/celery imported outside approved backend modules."
  echo "Route the dependency through an interface in src/services/* instead."
  exit 1
fi
echo "import guard passed"
