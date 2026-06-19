# Fagoon

Self-hostable AI agents + workflow platform. Two ways to run:

## Package users (one command)
```bash
pipx install fagoon-upgrade
fagoon up                 # lite mode: no Redis, no Celery, zero env required
fagoon up --ollama        # add the local Gemma fallback LLM
```
Open http://localhost:8000 and complete the setup wizard (LLM key + features).
Secrets are auto-generated; the database URL and config live in `~/.fagoon`.

## Contributors (clone + run)
```bash
git clone https://github.com/Fagoon-AI/upgrade.git
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
