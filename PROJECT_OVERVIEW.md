# Fagoon AI Agents Workflow — Project Overview & Flow

Welcome to the **Fagoon AI Agents Workflow** codebase. This document outlines the project's high-level architectural design, detailed folder structure, dual-mode system flow (Lite & Full modes), the advanced workflow engine, and the precise lifecycles of core operations.

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
│   │       ├── routers/           # FastAPI Domain routers (agents, auth, video_gen, workflow, etc.)
│   │       └── setup_api.py       # API setup, CORS configuration, and router aggregation
│   ├── core/                      # Application Bootstrap, Globals, and Settings
│   │   ├── bootstrap.py           # First-boot secret generator (JWT, Encryption key)
│   │   ├── globals.py             # Singletons and application globals
│   │   ├── runtime.py             # Runtime Factory choosing backends based on LITE_MODE
│   │   ├── settings.py            # Layered Settings Resolver (.env, config.json, environment)
│   │   └── sandbox.py             # Sandbox execution engines (Docker vs Subprocess fallback)
│   ├── models/                    # Data models and base objects
│   │   └── sql/
│   │       ├── models.py          # SQLAlchemy SQL models mapping to PostgreSQL
│   │       └── workflow/          # Workflow database models (Workflows, Executions, Connections, Webhooks, Schedules)
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
│   │   ├── tool_handlers/         # Execution handlers for Agent tools (Search, Mermaid, etc.)
│   │   ├── workflow/              # Workflow CRUD, versioning, publishing, and archiving services
│   │   └── workflow_engine/       # Core Graph DAG Execution engine and node definitions
│   │       ├── nodes/             # Fully typed Logic and Tool node implementations (Gemini, Openai, Slack, notion, etc.)
│   │       ├── context.py         # Thread-safe execution context and dynamic input variables
│   │       ├── executor.py        # Adjacency-based DAG executor with concurrent semaphore logic
│   │       └── registry.py        # Thread-safe node registration and manifest discovery
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
   - **Responsibility:** Houses all core business logic (e.g., orchestrating LLM steps, handling task processing, managing chat flows, executing database lookups, and running workflow visual logic).
   - **Boundary Constraints:** Service classes should remain independent of specific deployment modes. Instead, they interact with runtime abstractions (`app.state.queue`, `app.state.limiter`, etc.) and delegating graph execution to the `WorkflowExecutor`.
3. **The Providers & Integrations Layer (`src/providers/`, `src/llms/`, & `src/services/workflow_engine/nodes/`):**
   - **Responsibility:** Wrappers around external SDKs (OpenAI, Anthropic, Google GenAI, ElevenLabs, Notion, Twilio, Slack, Sheets). They normalize payloads, handle API retries, and translate responses into standard internal objects or node outputs.
4. **The Core Layer (`src/core/`):**
   - **Responsibility:** App bootstrapping, configuration resolution, database connection pooling (`PostgresManager`), isolated execution sandboxing (`DockerSandboxExecutor`), and lifespan management.

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

### Flow D: Visual DAG Workflow Execution (Real-time WebSocket Streaming)
Handles the invocation, execution mapping, and real-time trace logging of a multi-node workflow graph.

```text
[ Trigger Source ]          [ Workflow Router ]         [ WorkflowExecutor ]        [ Node Registry ]         [ Client (UI) ]
(Schedules / Hooks / API)           │                            │                         │                         │
        │                           │                            │                         │                         │
        │── Trigger Execution ─────>│                            │                         │                         │
        │                           │── Instantiate Executor ───>│                         │                         │
        │                           │   with Graph definition    │                         │                         │
        │                           │                            │── Resolve & Load Node ──>│                         │
        │                           │                            │   from Manifest/Registry│                         │
        │                           │                            │<─ Node Class Instance ──│                         │
        │                           │                            │                                                   │
        │                           │                            │── Start Execution Loop ─── [PostgreSQL (PENDING)] │
        │                           │                            │                                                   │
        │                           │                            │── Dynamic Data Mapping & Input Validation         │
        │                           │                            │                                                   │
        │                           │                            │── Execute Node Logic (LLM / Tool / Sandbox)       │
        │                           │                            │                                                   │
        │                           │                            │── Stream Node Trace Update ──────────────────────>│
        │                           │                            │   (Via Websockets / streams.py)                   │
        │                           │                            │                                                   │
        │                           │                            │── Increment Cost, Usage, & Token Counts           │
        │                           │                            │                                                   │
        │                           │                            │── Mark Node Executed ────> [PostgreSQL (SUCCESS)] │
        │                           │                            │                                                   │
        │                           │<─ Return Execution Stats ──│                                                   │
        │                           │   (Status, Trace, Costs)   │                                                   │
        │                           │                                                                                │
        │                           │── Save Results & Costs ───> [PostgreSQL (UsageRecord & MonthlySummary)]        │
```

---

## 5. The Advanced Workflow Engine & Nodes Registry

Fagoon includes a state-of-the-art Visual Workflow DAG (Directed Acyclic Graph) engine that empowers users to create, schedule, version, and execute automated pipelines with conditional routing, secure custom code execution, and deep third-party integrations.

### A. Graph Execution Engine (`WorkflowExecutor`)
The core orchestrator of graph evaluations:
- **Visual Data Flow:** Edges represent both control transitions and detailed data mappings (`data_mappings`) that extract fields from one node's output to inject into a downstream node's inputs.
- **Lock-Guarded Concurrency:** Employs an asynchronous lock-based semaphore pattern to evaluate parallel node paths safely without race conditions.
- **Advanced Control Logic:** Evaluates loops (`LoopNode`), multi-choice routers (`RouterNode`), conditionals (`FilterNode`), wait states (`WaitNode`), and concurrent branch joins (`ParallelNode`).
- **Dynamic Input Resolution:** Supports `@node_alias` and `@previous` syntactic variables. Input structures resolve templates dynamically on edge connections.
- **Circuit Breaker:** Integrates a built-in `CircuitBreaker` pattern to prevent cascading API crashes and isolate run failures.
- **Checkpoints & Resume:** Allows pausing graph executions (e.g., waiting for external input or human verification) and resuming from specified node checkpoints.

### B. Secure Sandbox Execution (`DockerSandboxExecutor`)
When a workflow node contains custom code scripts (Python, JS, HTML), security constraints are enforced strictly:
- **Docker Sandbox:** Runs user code inside lightweight, temporary, unprivileged Docker containers with **zero network access**, a read-only filesystem (with locked tmpfs for `/tmp`), dropped kernel capabilities, strictly restricted memory and CPU quotas via cgroups, and PID limits.
- **Subprocess Fallback:** Houses a secure fallback sandbox utilizing constrained subprocess execution environments with resource bounds, ensuring the system boots successfully in local or lightweight Docker setups.

### C. Comprehensive Nodes Registry & Discovery
All logical components and third-party tools are defined as modular, self-contained `BaseNode` extensions:
- **Thread-Safe NodeRegistry:** Manages dynamic discovery and class registration with hot-reload capabilities.
- **Structured Manifests:** Each node class exposes a declarative JSON-schema `NodeManifest` (display names, categories, fields, defaults, validations, documentation URLs, and expected outputs).
- **Core Node Categories:**
  - *Triggers:* Webhook triggers, manual API routes, and Scheduler Triggers.
  - *Logic & Flow:* Filter, Loop, Router, Wait, Parallel, and Start nodes.
  - *AI & Data:* Gemini, OpenAI, Anthropic, AgentManager, RAG, Perplexity, and Mistral Parse.
  - *Communication:* Slack, Twilio, Discord, and Gmail.
  - *Integrations:* Notion, YouTube, Google Sheets, and Supabase.
  - *Utilities:* Code Execution Sandboxes.

### D. Secure Connection & Credential Management
Users can link authenticated accounts (e.g., Salesforce, Slack, Notion, GitHub, and Shopify) directly in the UI:
- **Encrypted Storage:** Integrations map to a dedicated `Connection` model, storing credentials securely using multi-layered AES-256 encryption.
- **Environment Context Resolution:** During node evaluation, the `WorkflowExecutor` transparently retrieves the connection's credentials, decrypts them in-memory, and injects them safely into the tool API clients.

### E. Scheduler & Webhook Trigger Engine
- **High-Performance Scheduling:** Manages cron-based, interval, and one-off scheduled pipelines through database-backed `WorkflowSchedule` records. Runs asynchronous background execution loops that check schedule state and enqueue tasks directly to Celery or the Inline Task Queue.
- **Dynamic Webhooks (Hooks):** Exposes customizable webhook URL routes (`/hooks/{slug}`) that maps payloads to matching workflow trigger nodes instantly.

### F. Granular Usage Tracking & Quotas
- **Cost Accumulation:** Tracks detailed input/output tokens and financial costs associated with LLM calls and third-party API executions during a run.
- **User Quotas:** Monitors monthly quotas, active executions, and record summaries, checking execution boundaries dynamically at start-time to prevent platform abuse.

---

## 6. Development Invariants & Quality Standards

- **Never bypass Pydantic:** Request payloads and database-bound structures must always go through strict validation models.
- **Do not lock connections:** DB lookups must run asynchronously (`await session.execute()`), and heavy blocking operations must be offloaded to thread executors using `asyncio.to_thread`.
- **LITE_MODE must always pass testing:** Running `uv run pytest` installs minimal extras by default. If any core module accidentally imports an unauthorized package (like `redis` or `celery`), the import linter gate will catch it immediately.
