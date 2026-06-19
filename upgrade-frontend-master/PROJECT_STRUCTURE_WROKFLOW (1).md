# Project Architecture & Workflow Structure

This document details the file directory layout and the internal execution workflows for the AI Workflow Automation Platform.

---

## 📂 Complete Project Directory Structure

```text
D:\workflow_code\
├── alembic.ini                   # Alembic database migrations configuration file
├── Dockerfile                    # Docker build configuration for the main application
├── connect_redis.sh              # Utility shell script to connect/verify Redis connection
├── pyproject.toml                # Project metadata, dependencies, build tool settings, and pytest configuration
├── README.md                     # Main project readme
├── uv.lock                       # Lockfile managing specific python package versions (via UV packaging)
│
├── alembic/                      # Database migrations folder
│   ├── env.py                    # Migration execution script configuring DB context
│   ├── script.py.mako            # Template for generating new migration scripts
│   └── versions/                 # Individual migration script files
│       ├── 0ef15e78f70d_init_uuid_schema.py
│       ├── 0b463d51fdf2_add_usage_tracking_tables.py
│       ├── 0dfa49bde271_add_agentic_memory_and_rag_document_.py
│       ├── 4dd6b27a4d41_add_memory_and_rag_vector_tables.py
│       ├── 5362b7633307_add_engine_metadata_and_versioning.py
│       ├── a1b2c3d4e5f6_add_connection_tracking_columns.py
│       ├── b2c3d4e5f6a7_add_missing_webhook_columns.py
│       ├── c3d4e5f6a7b8_add_created_by_to_workflowversion.py
│       ├── d4e5f6a7b8c9_add_schedule_and_template_tables.py
│       ├── e18c5e4bf740_add_encrypted_connections.py
│       ├── e338371b80aa_fix_timezone_columns.py
│       ├── e5f6a7b8c9d0_seed_builtin_templates.py
│       └── fdb4494e113e_add_results_field_to_workflow_execution.py
│
├── app/                          # Core application source code
│   ├── __init__.py
│   ├── main.py                   # FastAPI app declaration, lifecycle hooks (startup/shutdown), and middleware setup
│   │
│   ├── api/                      # Routing layer for HTTP API requests
│   │   ├── __init__.py
│   │   ├── api_router.py         # Main router aggregating all versioned endpoints and health checks
│   │   ├── deps.py               # API dependency injections (Auth, Database sessions, Rate limiters)
│   │   └── v1/                   # API Version 1 endpoints
│   │       ├── __init__.py
│   │       └── endpoints/        # Grouped router endpoints
│   │           ├── auth.py                # User signup, login, JWT issuance, and OAuth flow endpoints
│   │           ├── connections.py         # External connection/credentials management (OAuth, API keys)
│   │           ├── discovery.py           # Discovers available integrations, schemas, and node types
│   │           ├── executions.py          # Controls and queries workflow executions (trigger, pause, resume)
│   │           ├── hooks.py               # Handles inbound generic and verified external Webhook requests
│   │           ├── nodes.py               # Queries registered node types and their validation manifests
│   │           ├── schedules.py           # CRUD and control of automated schedule-based executions
│   │           ├── streams.py             # Event streaming endpoints (WebSockets / SSE) for real-time tracking
│   │           ├── templates.py           # Platform templates configuration and CRUD
│   │           ├── usage.py               # Cost, token count, and financial billing metrics reporting
│   │           ├── variables.py           # Global and scoped system variables management
│   │           ├── workflow_templates.py  # Specific template workflows deployment
│   │           └── workflows.py           # Workflow creation, editing, visual graph definition, and retrieval
│   │
│   ├── core/                     # Platform-wide configuration, security, and low-level drivers
│   │   ├── __init__.py
│   │   ├── config.py             # Environment configurations (settings, database URLs, secret keys) loaded via Pydantic
│   │   ├── database.py           # SQLModel database engine & asynchronous context session managers
│   │   ├── celery_app.py         # Celery broker/backend setup and queuing configuration
│   │   ├── encryption.py         # Symmetric field-level encryption for securely caching user credentials/keys
│   │   ├── exceptions.py         # Global Exception handling mapping, error models, and standard validation handlers
│   │   ├── rate_limiter.py       # In-memory and Redis-backed rate limiting controls
│   │   ├── redis.py              # Redis connection pooling, pub/sub drivers, and cache drivers
│   │   ├── sandbox.py            # Code execution sandbox driver for isolated Python/JS execution
│   │   └── security.py           # Password hashing (Argon2), JWT encoding/decoding, and token generation
│   │
│   ├── dao/                      # Data Access Objects (encapsulated database CRUD)
│   │   ├── __init__.py
│   │   ├── user_dao.py           # Queries and mutations for User models
│   │   └── workflow_dao.py       # High-performance DB actions for workflows and layout definitions
│   │
│   ├── middleware/               # Custom HTTP request/response pipeline processors
│   │   ├── __init__.py
│   │   └── rate_limit.py         # Rate-limiting middleware intercepting API endpoints using Redis
│   │
│   ├── models/                   # SQLModel models representing database tables
│   │   ├── __init__.py
│   │   ├── user.py               # User registration, permissions, and profile records
│   │   ├── workflow.py           # Workflows metadata and graph definitions
│   │   ├── version.py            # History of published revisions for each workflow (WorkflowVersion)
│   │   ├── execution.py          # WorkflowExecution status, trace logs, variables state, and performance markers
│   │   ├── connection.py         # User's encrypted external credentials (API keys, OAuth tokens)
│   │   ├── document.py           # RAG Document uploads, chunking schemas, and embedding pointers
│   │   ├── memory.py             # Agentic memory models (long/short term recall storage for AI workflows)
│   │   ├── schedule.py           # Cron/interval schedule configurations mapping to workflows
│   │   ├── template.py           # Preset workflow structures used for quick installations
│   │   ├── usage.py              # Token count and monetary costing traces of executing workflows
│   │   └── webhook.py            # Custom inbound webhook identifiers, keys, and signatures verification
│   │
│   ├── schemas/                  # Pydantic schemas validating API payloads & serialization schemas
│   │   ├── __init__.py
│   │   ├── auth.py               # Request/response schemas for login, tokens, password resets
│   │   ├── connection.py         # Connection schemas validating setup configs and credential fields
│   │   ├── execution.py          # Execution statuses and historical payloads
│   │   ├── response.py           # Standardized API JSON envelope wrapper schemas
│   │   ├── schedule.py           # Formats for Cron-type validations
│   │   ├── template.py           # Blueprint definitions of prebuilt systems
│   │   └── workflow.py           # Full DAG schema layout validation (Nodes, Edges, properties)
│   │
│   ├── services/                 # Business logic controllers
│   │   ├── __init__.py
│   │   ├── auth_service.py       # Manages user accounts, session tokens, and passwords verification
│   │   ├── cost_tracking.py      # Calculates real-time financial and token costs of running LLM nodes
│   │   ├── discovery_service.py  # Maps dynamic integrations and metadata schemas for front-end rendering
│   │   ├── google_oauth.py       # OAuth handshake with Google API suites (Gmail, Sheets, etc.)
│   │   ├── graph_validation.py   # Complete DAG validation (checks cycles, disconnected nodes, type consistency)
│   │   ├── storage_service.py    # Local/Cloud storage interaction logic for workflow artifacts
│   │   ├── templates.py          # Handles deployment and lifecycle of workflow blueprints
│   │   ├── webhook_verifier.py   # Signature validation for third-party endpoints
│   │   ├── workflow_service.py   # CRUD, publishing, variables injection, and execution triggers for workflows
│   │   │
│   │   ├── tools/                # Utility modules for service layers
│   │   │   └── __init__.py
│   │   │
│   │   └── workflow_engine/      # Core execution engine for DAG traversal
│   │       ├── __init__.py
│   │       ├── context.py        # Shared memory, metrics, state progression, and concurrency guards (ExecutionContext)
│   │       ├── executor.py       # Topology traverser, input resolver, circuit breaker, and node scheduler
│   │       ├── registry.py       # Thread-safe node factory matching node identifiers to Python classes (NodeRegistry)
│   │       └── nodes/            # Extensible concrete node implementations
│   │           ├── __init__.py
│   │           ├── base.py                 # Abstract base class (BaseNode) enforcing standardized execution contracts
│   │           ├── start.py                # Initial execution entry point trigger node
│   │           ├── trigger_schedule.py     # Scheduled/cron entry point trigger node
│   │           │
│   │           ├── logic_filter.py         # Branches/stops flow based on evaluation of conditions
│   │           ├── logic_loop.py           # Iterates over dataset arrays, executing child chains sequentially or in parallel
│   │           ├── logic_parallel.py       # Executes concurrent branches simultaneously
│   │           ├── logic_router.py         # Multi-destination router matching variables against specific conditions
│   │           ├── logic_wait.py           # Pauses execution for defined duration or until inbound callback event
│   │           │
│   │           ├── tool_agent.py           # Runs an autonomous AI Agent loop utilizing registered functions/tools
│   │           ├── tool_anthropic.py       # Standard prompt completion using Anthropic Claude models
│   │           ├── tool_browser_use.py     # Autonomous web page scraper/interaction agent
│   │           ├── tool_code.py            # Executes custom Python or JavaScript blocks securely
│   │           ├── tool_discord.py         # Interacts with Discord API (sends/reads messages)
│   │           ├── tool_gemini.py          # Prompts Google Gemini LLMs
│   │           ├── tool_gmail.py           # Sends, reads, labels, or processes Gmail items
│   │           ├── tool_google_sheets.py   # Reads, appends, writes rows in Google Spreadsheet cells
│   │           ├── tool_memory.py          # Performs long/short term vector store memory adjustments
│   │           ├── tool_mistral_parse.py   # Leverages Mistral AI OCR capabilities for parsing documents
│   │           ├── tool_notion.py          # Reads, updates database rows/pages inside Notion workspaces
│   │           ├── tool_openai.py          # Connects to OpenAI chat models (GPT-4o, o1/o3, etc.)
│   │           ├── tool_perplexity.py      # Performs real-time web-enhanced queries via Perplexity search API
│   │           ├── tool_rag.py             # Executes semantic queries over vector-embedded files
│   │           ├── tool_slack.py           # Sends notifications or acts on Slack channels
│   │           ├── tool_supabase.py        # Standard queries/inserts into direct Supabase instances
│   │           ├── tool_twilio.py          # Sends SMS messages or WhatsApp template pings
│   │           ├── tool_webhook.py         # Fires customized outgoing HTTP webhook payloads
│   │           └── tool_youtube.py         # Searches videos, queries captions, and aggregates channel data
│   │
│   └── tasks/                    # Celery background tasks
│       ├── __init__.py
│       ├── cleanup.py            # Prunes old transaction trace logs, expired sandboxes, and file caches
│       ├── scheduler.py          # Periodically runs Cron evaluations and spawns workflow schedules
│       ├── workflow_task.py      # Base async Task class wrappers and error-handling utilities
│       └── workflow.py           # Core 'execute_workflow_task' background execution thread
│
├── docker/                       # Supporting container configurations
│   ├── build-sandbox.sh          # Orchestrates building a isolated container sandbox for custom code execution
│   └── Dockerfile.sandbox        # Hardened, lightweight image to safely host custom python/JS runtime blocks
│
├── scripts/                      # Developer utility scripts
│   └── export_openapi.py         # Automatically extracts standard Swagger / OpenAPI specs from code
│
└── tests/                        # Full automated test suites
    ├── __init__.py
    ├── conftest.py               # Configures shared Pytest fixtures, mock database managers, and loops
    ├── factories/                # FactoryBoy setups generating test data models
    │   ├── __init__.py
    │   ├── connection.py
    │   ├── execution.py
    │   ├── user.py
    │   └── workflow.py
    ├── integration/              # Tests end-to-end integration flows (requires database connections)
    ├── mocks/                    # Mock drivers for external tools
    │   ├── __init__.py
    │   ├── redis.py              # Mocked fake Redis cache (utilizing fakeredis)
    │   └── services.py           # Mocked third-party AI services and API backends
    └── unit/                     # Fast unit tests testing modules in isolation (no external network dependencies)
        ├── __init__.py
        ├── test_auth.py
        ├── test_execution.py
        └── test_workflow.py
```

---

## 🔄 End-to-End Workflow Execution Lifecycle

The system transforms structural canvas flowmaps (represented as Directed Acyclic Graphs or DAGs) into active executions. Below is the precise operational flow.

### Phase 1: Triggering
1. **API Call/Manual Trigger:** User targets `/api/v1/executions/trigger` with a payload.
2. **Scheduled Trigger:** The platform's automated scheduling daemon (`app/tasks/scheduler.py`) runs cron tests and initiates schedules.
3. **Webhook Callback Trigger:** Generic webhook hits `/api/v1/hooks/{webhook_id}` triggering custom branches.

### Phase 2: Orchestration & DB Staging
1. The `WorkflowService` processes the request, fetching the active `Workflow` and `WorkflowVersion` definitions from the DB.
2. An execution entry is logged in the `WorkflowExecution` table in `"PENDING"` status.
3. The job is queued into the Celery task broker (Redis) via:
   ```python
   execute_workflow_task.delay(execution_id, workflow_id, initial_input)
   ```

### Phase 3: Background Worker Processing
1. A Celery worker processes `execute_workflow_task`.
2. The database execution status transitions to `"RUNNING"`.
3. A WebSocket stream handler begins publishing real-time telemetry events directly to the Redis Pub/Sub channels under `exec_trace:{execution_id}`.

### Phase 4: DAG Traversal Loop
1. The **`WorkflowExecutor`** loads the DAG node mapping.
2. It constructs an **`ExecutionContext`** to manage concurrency-safe scoped variables, variables, outputs, and decryption keys.
3. It determines the starting vertices (triggers) and iterates:
   - Evaluates node dependencies (executes once parent node requirements are completed).
   - Validates the current node with a dedicated **`CircuitBreaker`** to avoid cascade failures on external API downtime.
   - Decrypts and injects cached credentials from the `Connection` table.
   - Runs the dynamic node's `.execute()` handler.
   - Resolves template inputs dynamically via the Jinja2 **`InputResolver`**.
   - Truncates/masks sensitive keys, tokens, or credentials inside the results before serializing telemetry traces.
   - Records outputs back to the context.

### Phase 5: Termination
1. When all eligible traversal routes are completed or dead-ended, the engine terminates.
2. Financial/token usage overhead is tracked and stored in the database via `app/services/cost_tracking.py`.
3. The execution status is finalized in the database as `"COMPLETED"` or `"FAILED"`.
