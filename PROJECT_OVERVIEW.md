# Fagoon AI Agents Workflow — Project Overview & Flow

Welcome to the **Fagoon AI Agents Workflow** codebase. This document outlines the project's high-level architectural design, detailed folder structure, dual-mode system flow (Lite & Full modes), and the precise lifecycles of core operations.

---

## 1. High-Level Folder Structure

The repository follows a clean, modular, and layered architecture that physically separates routing/API logic, core business services, third-party provider clients, and data models.

```text
d:\upgrade-fagoon\agents-workflow\
├── .github/                       # GitHub actions for CI/CD and Release pipelines
│   └── workflows/
│       ├── ci.yml                 # Runs test suites, import-guards, and boot validation
│       └── release.yml            # Multi-arch docker builds and PyPI deployment on tag
├── alembic/                       # Database migrations and schema version history
├── deploy/                        # Deployment configurations
│   ├── docker-compose.yml         # Container spec for Lite Mode (bundled PG, no Redis/Celery)
│   ├── docker-compose.full.yml    # Container spec for Full Mode (PG, Redis, App, Celery Worker)
│   ├── Dockerfile                 # Multi-stage build file
│   └── entrypoint.sh              # Container startup script (runs migrations then uvicorn)
├── fagoon_cli/                    # Control CLI source code (wraps Docker Compose)
│   ├── compose/                   # Bundled docker-compose files shipped inside python package
│   └── main.py                    # Typer command definitions (fagoon up, down, logs, etc.)
├── scripts/                       # Local shell, setup, and import guard helper scripts
├── src/                           # Central Application Source Code
│   ├── api/                       # API Layer
│   │   ├── custom_middleware.py   # Auth and CORS middlewares
│   │   └── v1/
│   │       ├── routers/           # FastAPI Domain routers (agents, auth, video_gen, workspace, etc.)
│   │       └── setup_api.py       # API setup, CORS configuration, and router aggregation
│   ├── core/                      # Application Bootstrap, Globals, and Settings
│   │   ├── bootstrap.py           # First-boot secret generator (JWT, Encryption key)
│   │   ├── globals.py             # Singletons and application globals
│   │   ├── runtime.py             # Runtime Factory choosing backends based on LITE_MODE
│   │   └── settings.py            # Layered Settings Resolver (.env, config.json, environment)
│   ├── models/                    # Data models and base objects
│   │   └── sql/
│   │       └── models.py          # SQLAlchemy SQL models mapping to PostgreSQL
│   ├── providers/                 # Direct client wrappers for 3rd-party services (OpenAI, Gemini, etc.)
│   ├── schemas/                   # Pydantic Schemas for strict request/response validation
│   ├── services/                  # Business Logic Layer
│   │   ├── cache/                 # Cache backend interfaces (Redis vs. In-Memory)
│   │   ├── database/              # Database switch and live migration logic
│   │   ├── google_workspace/      # Gmail, Docs, Drive, and Google AI services
│   │   ├── limiter/               # Rate-limiting backends (Redis vs. In-Memory)
│   │   ├── nosql/                 # DB wrapper services (e.g., PostgresServices)
│   │   ├── rag/                   # Document ingestion, text chunking, and embedding
│   │   ├── taskqueue/             # Asynchronous task dispatchers (Celery vs. Inline Asyncio)
│   │   └── tool_handlers/         # Execution handlers for Agent tools (Search, Mermaid, etc.)
│   ├── launch_server.py           # Application Entry Point & Lifespan/Teardown registry
│   └── constants.py               # Shared global constants
├── tests/                         # Full automated test suite (Unit, Integration, and Guardrails)
│   ├── conftest.py                # Test configuration and environment defaults (LITE_MODE=true)
│   ├── test_db_switch.py          # Tests for DB migration switch
│   ├── test_dual_mode.py          # Tests for Cache, Limiter, Queue, and Runtime configurations
│   ├── test_lite_boot.py          # Proves Lite Mode boots with zero env and no Redis
│   └── test_vibe_coder.py         # Tests setup and environment variables for Vibe Coder
├── pyproject.toml                 # Central project packaging, script hooks, and dependencies
└── GEMINI.md                      # Foundational AI mandate guidelines
```

---

## 2. Key Architectural Layers & Responsibilities

1. **The API Layer (`src/api/`):**
   - **Responsibility:** Handles request parsing, Pydantic model validation, HTTP response statuses, and endpoint definitions.
   - **Rules:** No business logic resides here. All routers must delegate heavy computational or orchestration work to **Services**.
2. **The Service Layer (`src/services/`):**
   - **Responsibility:** Houses all core business logic (e.g., orchestrating LLM steps, handling task processing, managing chat flows, and executing database lookups).
   - **Boundary Constraints:** Service classes should remain independent of specific deployment modes. Instead, they interact with runtime abstractions (`app.state.queue`, `app.state.limiter`, etc.).
3. **The Providers Layer (`src/providers/` & `src/llms/`):**
   - **Responsibility:** Wrappers around external SDKs (OpenAI, Anthropic, Google GenAI, ElevenLabs). They normalize payloads, handle API retries, and translate responses into standard internal objects.
4. **The Core Layer (`src/core/`):**
   - **Responsibility:** App bootstrapping, configuration resolution, database connection pooling (`PostgresManager`), and lifespan management.

---

## 3. The Core Concept: Dual-Mode Runtime Flow

Fagoon operates under two distinct deployment topologies governed dynamically by the `LITE_MODE` environment variable.

```text
                      [ Start launch_server.py ]
                                  │
                    [ Read settings & bootstrap ]
                                  │
                    Is LITE_MODE environment active?
                     /                         \
                   YES                          NO
                   /                             \
       ┌─────────────────────────┐         ┌─────────────────────────┐
       │      LITE RUNTIME       │         │      FULL RUNTIME       │
       │ ─────────────────────── │         │ ─────────────────────── │
       │ • Limiter: Memory       │         │ • Limiter: Redis        │
       │ • Cache: Memory         │         │ • Cache: Redis          │
       │ • Queue: Inline Asyncio │         │ • Queue: Celery         │
       │ • Workers: Forced to 1  │         │ • Workers: Concurrent   │
       └─────────────────────────┘         └─────────────────────────┘
                   \                             /
                    \                           /
                 [ Mount instances on app.state ]
                                │
                    [ Ready to handle requests ]
```

### Dependency Decoupling (Strict CI Gate)
Business logic files must **NEVER** import `redis` or `celery` directly. Doing so would violate the self-contained contract of Lite Mode and crash installations lacking Redis. 
- All queue submissions go through `app.state.queue.enqueue(func, *args)`
- All rate-limiting hits go through `app.state.limiter.allow(key, limit, window)`
- All caching operations go through `app.state.cache.get(key)` / `set(key, value)`

---

## 4. Primary Request Lifecycles & Flows

### Flow A: RAG-Enabled Agent Chat (SSE Streaming)
This flow handles the real-time retrieval-augmented generation streaming chat.

```text
[Client]                [Agent Router]           [Orchestrator]          [Vector DB]           [LLM Provider]
   │                          │                         │                     │                      │
   │── POST /agent/chat ─────>│                         │                     │                      │
   │   (Pydantic validation)  │── Get Orchestrator ────>│                     │                      │
   │                          │   from app.state        │── Embed Query ─────>│                      │
   │                          │                         │   & Search Vector   │                      │
   │                          │                         │<── Document Chunks ─│                      │
   │                          │                         │                                            │
   │                          │                         │── Form Prompt & Call ─────────────────────>│
   │                          │                         │   (With dynamic custom user API Key)       │
   │<─ Yield SSE Chunk ───────│<── Yield Text Stream ───│<── Stream Chunks ──────────────────────────│
   │   (Event-stream format)  │                         │                                            │
   │                          │                         │── Save History ───[PostgreSQL]             │
```

---

### Flow B: Asynchronous Background Video Generation
This flow handles long-running video rendering safely in both Lite and Full modes.

```text
[Client]             [Video Router]          [PostgreSQL]             [Task Queue]          [Veo / Video Gen]
   │                       │                      │                        │                        │
   │── POST /video/gen ───>│                      │                        │                        │
   │                       │── Create Job ───────>│                        │                        │
   │                       │   (Status: PENDING)  │                        │                        │
   │                       │                      │                        │                        │
   │                       │── Dispatch Task ─────────────────────────────>│                        │
   │                       │   (app.state.queue.enqueue)                   │                        │
   │                       │                                               │                        │
   │<─ Return job_id ──────│                                               │                        │
   │   (Immediate 202)     │                                               │                        │
   │                       │                                               │                        │
   │                       │   [Background Worker / Inline Executor]       │                        │
   │                       │   │                                           │                        │
   │                       │   │── Update Job status ─────> [PostgreSQL]   │                        │
   │                       │   │   (Status: PROCESSING)                    │                        │
   │                       │   │                                           │                        │
   │                       │   │── Invoke Veo Generator ───────────────────┼───────────────────────>│
   │                       │   │                                           │                        │
   │                       │   │── Save Asset and Upload to Storage ───────┼───────────────────────>│
   │                       │   │                                           │                        │
   │                       │   │── Mark Job status ──────> [PostgreSQL]    │                        │
   │                       │   │   (COMPLETED or FAILED)                   │                        │
   │                       │                                               │                        │
   │                       │   [WebSocket Manager (Periodic Status Broadcaster)]                    │
   │                       │   │                                           │                        │
   │<─ Push Status Update ─│───│── Poll DB Status & Broadcast ─────────────│                        │
```

---

### Flow C: Google Workspace Integration & Authentication Flow
Handles authorization flow and token-delegated requests securely.

1. **OAuth Setup:**
   - User goes to `/api/v1/google-auth/login` which constructs the Google Authorization URI.
   - Upon callback to `/api/v1/google-auth/callback`, the app exchanges the temporary authorization code for standard OAuth access and refresh tokens.
   - The token is securely stored in the `google_tokens` table in PostgreSQL.
2. **Service Request Delegation:**
   - A request comes in for Gmail or Drive (e.g., `/api/v1/gmail/messages`).
   - The router uses a FastAPI dependency check (`get_google_credentials`) to load the active tokens.
   - The route instantiates `GoogleGmailService(credentials)` which loads the `google-api-python-client` SDK.
   - If the LLM generates a request for Google AI operations, `AIService` resolves the custom Groq/Gemini key from `resolve_api_key()` based on the logged-in user context and executes the LLM step.

---

## 5. Development Invariants & Quality Standards

- **Never bypass Pydantic:** Request payloads and database-bound structures must always go through strict validation models.
- **Do not lock connections:** DB lookups must run asynchronously (`await session.execute()`), and heavy blocking operations must be offloaded to thread executors using `asyncio.to_thread`.
- **LITE_MODE must always pass testing:** Running `uv run pytest` installs minimal extras by default. If any core module accidentally imports an unauthorized package (like `redis` or `celery`), the import linter gate will catch it immediately.
