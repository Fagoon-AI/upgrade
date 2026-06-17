# Fagoon Dual-Mode — Phase Plan (what each phase does)

This is the map. The companion file `GEMINI_CLI_IMPLEMENTATION.md` is the
territory — hand that one to Gemini CLI to actually write the code. Read this
one yourself to understand what is happening and to review Gemini's work after
each phase.

## The one idea

The app reads a single flag, `LITE_MODE`, once at startup. A factory
(`runtime.py`) uses it to pick backends and attaches them to `app.state`.
Everything else in the app calls `app.state.limiter`, `app.state.queue`,
`app.state.cache` — never Redis or Celery directly.

- **Lite mode** (default for package users): in-memory limiter/cache, inline
  asyncio background jobs, no Redis, no Celery, single process. Zero env needed.
- **Full mode** (contributors, concurrency): Redis + Celery worker, multi-worker.

The refactor is one move — "put an interface between code and backend" — repeated
for the three things that touch Redis/Celery. Nothing is rewritten wholesale.

---

## Phases at a glance

| Phase | What it delivers | Touches existing code? | Verify |
|-------|------------------|------------------------|--------|
| 0 | Working branch, dev tooling | No | App still starts |
| 1 | Settings resolver + secret bootstrap | Maybe merges settings.py | `enabled_features` prints |
| 2 | Rate limiter interface + 2 backends | No (new files) | — |
| 3 | Task queue interface + 2 backends | No (new files) | — |
| 4 | Cache interface + 2 backends | No (new files) | — |
| 5 | Runtime factory + lifespan wiring | Edits launch_server.py | App boots both modes |
| 6 | Migrate call sites to app.state | Edits routers/services | grep finds no stray imports |
| 7 | Guardrails: import-linter, tests | No (new files) | All 3 checks pass |
| 8 | Packaging: Docker, compose, CLI | Merges pyproject.toml | `fagoon --help` works |
| 9 | CI + release workflows + governance | No (new files) | Tag triggers release |

---

## Phase 0 — Branch and baseline
Create `feat/dual-mode`, confirm the app currently runs, install dev tooling
(pytest, import-linter, ruff). **Nothing changes behaviorally.** This exists so
every later phase has a known-good starting point and a rollback target.

## Phase 1 — Config foundation
Adds the layered settings resolver (env → config.json → defaults) and the
first-boot bootstrap that auto-generates the JWT secret and encryption key into
`config.json`. This is what lets a package user install with no `.env`. With
`LITE_MODE` still false, the app behaves exactly as before. If a `settings.py`
already exists, Gemini merges into it rather than replacing it.

**Review point:** check that existing settings fields survived the merge and
that full mode still raises if `REDIS_URL` is missing.

## Phase 2 — Rate limiter abstraction
Defines `RateLimiter` (a Protocol), a `RedisRateLimiter` (your full-mode logic),
and a `MemoryRateLimiter` (a sliding window in a dict, lite mode). No call sites
change yet — this phase just creates the parts.

## Phase 3 — Task queue abstraction
Same shape for background jobs: `TaskQueue` interface, `CeleryTaskQueue` (full),
`InlineTaskQueue` (lite, runs work as an asyncio task). Job *status* keeps
flowing through Postgres unchanged, so your WebSocket status broadcaster is
untouched. The only behavioral difference in lite mode: a job dies on restart.

## Phase 4 — Cache abstraction
`Cache` interface with Redis and in-memory TTL backends. Cheap to add even if you
barely use caching, because the runtime factory wires it alongside the others.

## Phase 5 — Runtime factory + lifespan wiring
The keystone. `runtime.py` reads `LITE_MODE` and builds the right backends.
`launch_server.py`'s lifespan calls `ensure_bootstrap`, enforces the
single-process invariant, builds the runtime, and attaches the backends to
`app.state`. Here Gemini also plugs your **real** Celery task into the queue
registry.

**Review point:** this is the file edit most worth reading carefully. Confirm
the lifespan still sets up your existing singletons (postgres_manager, vector
store, etc.) and that `rt.shutdown()` is called on teardown.

## Phase 6 — Migrate call sites
The mechanical pass: every `redis.xxx` and `task.delay(...)` in routers/services
becomes `app.state.limiter` / `app.state.queue` / `app.state.cache`. You don't
have to hunt by hand — Phase 7's import-linter will name every file that still
imports redis/celery where it shouldn't.

**Review point:** run the grep commands yourself and confirm the only remaining
redis/celery imports are in the four backend modules, `runtime.py`, and
`celery_app.py`.

## Phase 7 — Guardrails
The answer to "I can't watch every PR." Three automated gates:
- **import-linter** fails the build if business code imports redis/celery.
- **guard script** is a blunt grep backup for string-level cases.
- **lite-boot test** installs *without* the full extra and boots with no env, no
  Redis — proving lite mode is self-contained — and asserts lite mode refuses
  multiple workers.

Once these are required status checks (Phase 9 + GitHub UI), a PR that breaks
lite mode physically cannot merge. You stop reviewing for this class of bug.

## Phase 8 — Packaging
Makes it shippable: optional `full` extra so lite installs stay lean, the
`fagoon` console script, the Dockerfile, the entrypoint that runs migrations
then uvicorn, both compose files (lite = published image; full = build context
with Redis + worker), and the Typer CLI that wraps Compose so users type
`fagoon up`. Gemini merges the new bits into an existing `pyproject.toml`.

**Review point:** replace the `ghcr.io/you/fagoon` placeholder with your real
owner/repo everywhere before shipping.

## Phase 9 — GitHub automation
`ci.yml` runs tests + guardrails on every PR and on main, publishing nothing.
`release.yml` runs only on `v*` tags: builds the multi-arch image to GHCR,
publishes the CLI to PyPI via trusted publishing, cuts a GitHub release.
CODEOWNERS forces your review on the mode-machinery files. PR template keeps the
contract visible.

**Manual steps (GitHub UI, not Gemini's job):** branch protection with the three
required checks, PyPI trusted-publishing registration + a protected `pypi`
environment, and flipping the GHCR package to public after the first release.

---

## After Gemini finishes

1. Read the `launch_server.py` and call-site diffs — those are the only edits to
   your existing code, so they're where a mistake would hide.
2. Run locally: `uv run pytest -q`, `uv run lint-imports`, `bash scripts/guard_imports.sh`.
3. Boot lite mode with no env to feel the package experience:
   `LITE_MODE=true DATABASE_URL_DEFAULT=... uv run uvicorn src.launch_server:app --workers 1`
4. Open a PR; confirm the three CI checks run and pass.
5. Set up branch protection + PyPI trusted publishing,

## Boundaries to keep in mind

- pgvector means Postgres is mandatory in both modes — there is no SQLite path.
- Lite mode = single process. The memory limiter/queue are correct only with one
  worker; the startup guard enforces it.
- Contributor changes never reach package users until you tag a release. Users
  pin a version; `main` is for people running from source.
