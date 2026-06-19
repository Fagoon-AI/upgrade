# Fagoon AI Agents Workflow: Comprehensive Documentation

## 1. Executive Summary & Tech Stack

**Fagoon AI Agents Workflow** is a sophisticated, highly scalable backend orchestration platform built for managing complex AI interactions, document retrieval, media generation, and automated workflows. It serves as the intelligent core for both standalone agentic chats and complex DAG-based visual workflows.

**Core Technologies:**
*   **Framework:** FastAPI (Python 3.12+)
*   **Database:** PostgreSQL (asyncpg) with `pgvector` for RAG embeddings.
*   **Migrations:** Alembic.
*   **Background Processing:** Celery + Redis (Distributed) or `asyncio` queues (Local/Lite).
*   **Dependency Management:** `uv`
*   **AI Integration:** Multi-provider support (OpenAI, Anthropic, Google Gemini/Veo, Groq, Perplexity, etc.) managed via a dynamic API Key Resolution system.
*   **Real-time Comms:** Server-Sent Events (SSE) for LLM streaming; WebSockets for job progress tracking.

---

## 2. System Architecture

The application strictly adheres to a Layered/Modular architectural pattern:
*   **Routers (`src/api/v1/routers/`)**: Handles HTTP requests, Pydantic validation, and dependency injection.
*   **Services (`src/services/`)**: The core business logic, including `workflow_engine`, `api_key_resolver`, `auth_service`, and RAG ingestion.
*   **Providers/LLMs (`src/llms/`)**: Standardized wrappers around third-party AI APIs.
*   **Data/Storage (`src/models/sql/`, `src/storages/`)**: SQLAlchemy models, database abstractions, and GCS/Local file storage handlers.

### Dual-Mode Runtime Infrastructure
To accommodate both individual developers and enterprise deployments, the system features a **Dual-Mode Architecture**:

1.  **Lite Mode (`LITE_MODE=true`)**:
    *   Designed for local development and single-user package installations (`fagoon up`).
    *   **In-Memory Services:** Uses `MemoryRateLimiter`, `MemoryCache`, and `MemoryPubSub`.
    *   **Inline Queues:** Replaces Celery with an `InlineTaskQueueWithSyncSupport` using `asyncio` to run background tasks without requiring Redis.
    *   **Auto-Configuration:** Bootstraps missing secrets (JWT, encryption keys) dynamically.
2.  **Full Mode (`LITE_MODE=false`)**:
    *   Production-ready distributed architecture.
    *   Requires a Redis broker (`REDIS_URL`) and Celery workers to handle heavy, concurrent background jobs (e.g., video generation).

---

## 3. Core Backend Flows

### Authentication & Authorization
*   **JWT & HttpOnly Cookies:** Authentication generates an Access Token and a Refresh Token, secured via `HttpOnly`, `Secure`, `SameSite=None` cookies.
*   **`AuthMiddleware`:** Intercepts all requests (except whitelisted public routes), validates the JWT signature (`jwt_secret`), and attaches a validated `UserInDB` object to `request.state.user`.
*   **Auto-Refresh:** If an access token expires but a valid refresh token exists in the cookies, the middleware securely rotates both tokens mid-flight without interrupting the client request.
*   **Workflow Sync:** The workflow engine maintains a separate `user` table to enforce foreign keys. The `get_current_user` dependency automatically syncs the core user profile to this table upon access.

### RAG & Agent Chat
*   **Ingestion:** Documents (PDFs, Web pages) are chunked and embedded via OpenAI/Gemini embedding models, then stored in PostgreSQL using the `pgvector` extension.
*   **Streaming Responses:** Chat interactions (`/api/v1/agent/chat`) execute via the `ChatOrchestrator`. It streams responses back to the client using **Server-Sent Events (SSE)**.
*   **Tool Execution:** Agents can autonomously trigger Python functions (e.g., Web Search, Deep Research) during generation.

### Background Media Generation
*   **Submission:** Video/Image generation requests create a `VideoJob` record in PostgreSQL (`PENDING` status).
*   **Execution:** The task is dispatched to Celery (Full Mode) or an asyncio thread (Lite Mode).
*   **Broadcasting:** A dedicated WebSocket manager polls the database and pushes real-time status updates (`PROCESSING`, `COMPLETED`, `FAILED`) down to connected frontend clients.

### The Workflow Engine
A newly integrated DAG (Directed Acyclic Graph) executor for visual automations.
*   **Node Registry:** Discovers and caches available node tools dynamically (e.g., `OpenAINode`, `GmailNode`, `DiscordNode`).
*   **Execution Context:** Manages state transitions, conditional logic (`routerNode`), loops (`loopNode`), and variables dynamically resolved via Jinja2 templates.
*   **API Key Resolution (`resolve_api_key`)**: 
    A sophisticated hierarchical credential system. When a node (like `GeminiNode` or `OpenAINode`) requires credentials:
    1.  It checks for a user-provided workflow `Connection` mapping.
    2.  If missing, it falls back to the user's "Manage Model" settings (`LLMModelConfig` via `resolve_api_key()`).
    3.  If missing, it defaults to the system `.env` variables.

---

## 4. Data Models & Schema

The platform relies heavily on PostgreSQL, managed via **Alembic** migrations.

**Key Tables:**
*   `users` / `user`: Core authentication and workflow ownership.
*   `llm_model_configs`: Stores user-specific "Manage Model" configurations.
*   `document_chunks` & `file_references`: The foundation of the pgvector RAG system.
*   `workflow`, `workflowversion`, `workflowexecution`: Stores the DAG definitions, historical states, and live execution traces.
*   `connection`: Stores encrypted third-party credentials (OAuth tokens, API keys) securely using Fernet symmetric encryption.
*   `video_jobs`: Tracks state for long-running media generation.

---

## 5. Expected Frontend Integration

While the frontend repository is managed separately, it must adhere to the following integration contracts:

1.  **Authentication Transport:**
    *   The frontend should rely on browser-managed cookies for authentication (`jwt` and `refresh_token`).
    *   Alternatively, it can pass the token manually via the `Authorization: Bearer <token>` header or `X-Access-Token` for non-browser clients.
    *   Credentials must be included in cross-origin requests (`credentials: 'include'`).

2.  **Streaming Chat (SSE):**
    *   To consume agent responses in real-time, the frontend must utilize an EventSource client or fetch stream reader pointing to the `/api/v1/agent/chat` SSE endpoints.

3.  **Real-time Job Updates (WebSockets):**
    *   For video or heavy background generations, the frontend should initiate a WebSocket connection to `/api/v1/ws/{client_id}`.
    *   It must listen for JSON payloads matching `{ "job_id": "...", "status": "COMPLETED", "progress": 100 }`.

4.  **Workflow Canvas Integration:**
    *   The frontend designer fetches available blocks via `GET /api/v1/nodes/registry`.
    *   It submits the React Flow state mapped to the backend `graph_definition` JSON schema via `POST /api/v1/workflows/`.
    *   Authentication is inherited seamlessly from the core auth cookies.