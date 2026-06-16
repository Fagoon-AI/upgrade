# Fagoon AI Agents Workflow

This repository contains the backend for the Fagoon AI Agents Workflow platform, built with FastAPI. It handles complex AI orchestration, including RAG-enabled chat, background video generation, image generation, text-to-speech, tool-calling execution, and deep integration with Google Workspace.

## Mandatory Rule for AI Agents
**CRITICAL:** Any major architectural, structural, or infrastructural changes made to this project MUST be documented by updating this `GEMINI.md` file immediately. This ensures all future agents understand the current system state. Do not proceed with major architecture refactors without updating this document.

## Tech Stack & Architecture

- **Framework:** FastAPI (Python 3.12+)
- **Package Management:** `uv` with `pyproject.toml`
- **Primary Database:** PostgreSQL (accessed via SQLAlchemy `AsyncSession` & `asyncpg`)
- **Vector Database:** PostgreSQL via `pgvector` (for RAG document chunks)
- **Migrations:** Alembic
- **Background Jobs:** Celery (with Redis broker, Eventlet execution pool)
- **Real-time:** Server-Sent Events (SSE) for streaming LLM responses, WebSockets for video generation status.
- **LLM/AI Integrations:** OpenAI, Anthropic, Google GenAI (Gemini/Veo), Groq, Hugging Face, Fal AI, ElevenLabs, Kokoro.
- **Architecture Pattern:** Layered/Modular (Routers -> Services -> Providers -> Data/Storage).

## Strict Layer & Module Rules

- **Routers (`src/api/v1/routers/`):** ONLY routing and request validation (Pydantic). Dependency injection happens here. No business logic. Subdirectories categorize domains (`agents`, `authentication`, `external`, `misc`, `upgrade`, `video_gen`, `workflow`, `workspace`).
- **Services (`src/services/`):** Core business logic. Orchestrates calls to models, storage, and external providers.
    - `tool_handlers/`: Specific execution logic for AI tools (e.g., `web_search_handler.py`, `mermaid_handler.py`, `deep_research_handler.py`).
    - `rag/`: Document ingestion and chunking (`ingestion_manager.py`).
    - `google_workspace/`: Logic for Docs, Drive, and Gmail APIs.
    - `channel_adapter/`: Webhook processing for external messaging platforms.
    - `nosql/`: Database wrapper services (Legacy naming, but currently houses `postgres_services.py`).
- **Models & Schemas:** 
    - `src/models/sql/`: SQLAlchemy Base models (`models.py`) defining the exact PostgreSQL schema.
    - `src/schemas/`: Pydantic schemas for request/response validation. Keep them strictly typed.
- **Storages (`src/storages/`):** Abstractions for `file_storage` and vector storage (`vectordb_storages/pgvector.py`).
- **LLMs & Providers (`src/llms/`, `src/providers/`):** Wrappers for external AI API clients.
- **Core (`src/core/`):** Application globals, settings (`settings.py`), database connection pool (`PostgresManager`), exception handlers.

## Lifespan Singletons
Heavy clients are initialized once during FastAPI lifespan (`src/launch_server.py`) and attached to `app.state`. Do NOT instantiate these per request:
- `app.state.postgres_manager`: Connection pool for PostgreSQL.
- `app.state.httpx_client`: Global HTTP client.
- `app.state.vector_store`: Singleton `PgVectorStorage`.
- `app.state.agent_manager` & `app.state.chat_orchestrator`: Core orchestration singletons.

## Core Request Lifecycles & Component Flows

### 1. RAG-Enabled Agent Chat (Server-Sent Events)
The system uses Retrieval-Augmented Generation (RAG) to provide AI agents with specific document context.
1. **Entry Point:** `POST /api/v1/agent/chat` (via `src/api/v1/routers/agents/agent_chat.py`).
2. **Middleware Check:** `AuthMiddleware` (`src/api/custom_middleware.py`) validates the JWT in headers/cookies.
3. **Validation & Routing:** Validates `AgentChatRequest`. Retrieves `ChatOrchestrator` from `app.state`.
4. **Orchestrator Execution (`src/services/agents/chat_orchestrator.py`):**
    - **Embed:** Calls the embedding model to generate a vector for the user query.
    - **Retrieve:** Queries PostgreSQL (`app.state.vector_store`) asynchronously using `pgvector` to retrieve relevant `document_chunks`. Offloads BM25 Reranking to a background thread if configured.
    - **Tool Handling:** If the LLM requests a tool, execution routes to `src/services/tool_handlers/` (e.g., triggering a deep web search or generating Mermaid charts).
5. **Streaming Response:** Yields Server-Sent Events (SSE) back to the client using utility functions in `src/utils/common.py`.
6. **Persistence:** Saves chat history to PostgreSQL asynchronously via `AgentChatService`.

### 2. Background Video Generation
1. **Entry Point:** `/api/v1/video-generation/...` (via `src/api/v1/routers/video_gen/video_gen_routes.py`).
2. **Database Initiation:** A `VideoJob` record is created in PostgreSQL with status `PENDING`.
3. **Task Queueing:** A Celery task (`generate_video_task`) is dispatched to the broker (Redis). The HTTP request immediately returns the `job_id` to the client.
4. **Celery Worker Execution:**
    - Worker updates PostgreSQL status to `PROCESSING`.
    - Dispatches to `VeoVideoGenerator` (`src/services/veo_video_generator.py`) or text-to-video handlers.
    - Resulting video is saved locally or pushed to Google Cloud Storage (GCS).
    - Status is updated to `COMPLETED` or `FAILED`.
5. **Client Notification:** A background asyncio task (`periodic_status_broadcaster` in `src/video_generation/websocket_manager.py`) constantly reads job statuses from the DB and pushes real-time updates to the client via WebSockets.

### 3. Google Workspace Operations
1. **Authentication:** User authenticates via `/api/v1/google-auth/login` (`src/api/v1/routers/workspace/google_auth.py`). System exchanges code for access/refresh tokens and saves them in PostgreSQL (`google_tokens` table).
2. **Operation:** Request sent to a workspace endpoint (e.g., `/api/v1/gmail/messages` in `src/api/v1/routers/workspace/gmail.py`).
3. **Dependency Check:** Router depends on `get_google_credentials` (`src/api/v1/routers/workspace/deps.py`), verifying the Google token exists and is valid.
4. **Service Call:** Service classes in `src/services/google_workspace/` use the `google-api-python-client` to execute the operation on behalf of the user.

### 4. Authentication Flow
1. **Middleware Check:** `AuthMiddleware` runs on all non-public routes (bypassing paths in `ALLOWED_URL_PATH_WITHOUT_AUTHORIZATION`).
2. **Token Extraction & Validation:** Attempts to read `Authorization` header, falls back to `jwt` cookie. Decodes JWT using `JWT_SECRET`. Verifies user active status.
3. **Auto-Refresh:** If the access token is expired but a valid `refresh_token` cookie exists, generates a new access/refresh pair, updates context, and appends cookies to the response.
4. **Authorization Injection:** Injects `request.state.user` for specific router dependencies. Routes are managed in `src/api/v1/routers/authentication/auth_router.py`.

## Required Environment Variables (from `settings.py`)

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` (for database connection URL)
- `JWT_SECRET`, `JWT_ALGORITHM`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, etc. (for respective features)

## What NOT to do (Anti-patterns)

- **Do NOT** put business logic inside FastAPI router functions.
- **Do NOT** use `sync` functions for database or network calls; always use async variants or thread executors.
- **Do NOT** instantiate heavy clients (like DB connection pools or HTTP clients) per request. Use `app.state` singletons.
- **Do NOT** bypass the custom `AuthMiddleware` for protected routes. Check `ALLOWED_URL_PATH_WITHOUT_AUTHORIZATION` for exceptions.
- **Do NOT** suppress or bypass Pydantic validation errors. Use `RequestValidationError` correctly.