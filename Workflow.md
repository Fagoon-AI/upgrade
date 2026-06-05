# Developer Workflow & Project Architecture

Welcome to the **Fagoon AI Agents Workflow** backend. This document provides a comprehensive deep dive into the project's architecture, request lifecycles, database structures, and overall developer workflows to help you onboard quickly.

## 1. High-Level Architecture

The system follows a classic N-Tier Layered Architecture with asynchronous capabilities, designed to handle heavy AI model interactions and real-time streaming.

```text
    +-------------------------------------------------------------+
    |                      Client Apps                            |
    |  (Web / Next.js, HTTP REST, Server-Sent Events, WebSockets) |
    +------------------------------+------------------------------+
                                   |
+----------------------------------v-----------------------------------+
|                          FASTAPI APPLICATION                         |
|                                                                      |
|  +--------------------+    +-------------------+    +-------------+  |
|  |     Middleware     |    |   API Routers     |    |  Lifespan   |  |
|  | (Auth, Logging)    +----> (src/api/v1/...)  <----+ (Singletons)|  |
|  +--------------------+    +---------+---------+    +-------------+  |
|                                      |                               |
|  +-----------------------------------v----------------------------+  |
|  |                        Service Layer                           |  |
|  | (AgentManager, ChatOrchestrator, Crawl4AI, Auth, ImageGen)     |  |
|  +----+------------------+-------------------+--------------------+  |
|       |                  |                   |                       |
| +-----v-----+      +-----v-----+       +-----v-----+                 |
| | Providers |      | Data/DB   |       | Celery    |                 |
| | (OpenAI,  |      | Services  |       | Tasks     |                 |
| |  Gemini,  |      | (NoSQL)   |       | (Async)   |                 |
| |  etc.)    |      +-----+-----+       +-----+-----+                 |
| +-----------+            |                   |                       |
+--------------------------|-------------------|-----------------------+
                           |                   |
               +-----------v----------+  +-----v----------------+
               | MongoDB & Qdrant DBs |  | Redis Task Broker &  |
               | (State & Vectors)    |  | Veo Video Generator  |
               +----------------------+  +----------------------+
```

## 2. Core Request Lifecycles

### 2.1 RAG-Enabled Chat (Server-Sent Events)
The system uses Retrieval-Augmented Generation (RAG) to provide AI agents with specific document context.

1. **Entry Point:** `POST /api/v1/agent/chat`
2. **Middleware:** Intercepts the request to validate the JWT in headers/cookies. Extracts `user_id`.
3. **Router:** Validates the request body (`AgentChatRequest`) using Pydantic. Retrieves `ChatOrchestrator` from `app.state`.
4. **Orchestrator (Embed):** Calls OpenAI API to generate a vector embedding for the user's query (`text-embedding-3-small`).
5. **Orchestrator (Retrieve & Rerank):**
    - Queries **Qdrant** asynchronously to retrieve the top 10 relevant document chunks.
    - Offloads **BM25 Reranking** (CPU-bound) to a background thread via `asyncio.to_thread` to ensure event-loop isn't blocked. Selects top 5 chunks.
6. **Orchestrator (Prompt Build):** Formats a prompt forcing the AI to cite sources.
7. **LLM Generation:** Streams the prompt to the configured LLM provider via `OpenAILLM` or other provider classes.
8. **Response Streaming:** The router yields Server-Sent Events (SSE) back to the client:
    - First, emits the `retrieval_summary`.
    - Then, streams the generation `token` by `token`.
    - Finally, emits a `done` event.
9. **Persistence:** The orchestrator silently saves the complete message history to MongoDB via `AgentChatService`.

### 2.2 Background Video Generation
1. **Entry Point:** `POST /api/v1/video-generation/...`
2. **Database Initiation:** A `VideoJob` document is created in MongoDB with status `PENDING`.
3. **Task Queueing:** A Celery task (`generate_video_task`) is dispatched to the broker (Redis). The HTTP request immediately returns the `job_id` to the client.
4. **Celery Worker Execution:**
    - Worker updates MongoDB status to `PROCESSING`.
    - `VeoVideoGenerator` calls the Google Veo API.
    - Resulting video is saved locally or pushed to Google Cloud Storage (GCS).
    - Status is updated to `COMPLETED` or `FAILED`.
5. **Client Notification:** A background asyncio task in FastAPI (`periodic_status_broadcaster`) constantly reads job statuses from the DB and pushes updates to the client via WebSockets.

### 2.3 Google Workspace Operations
1. **Authentication:** User authenticates via `/api/v1/google-auth/login`. System exchanges code for access/refresh tokens and saves them in MongoDB `google_tokens`.
2. **Operation:** Request sent to e.g., `/api/v1/gmail/messages`.
3. **Dependency Check:** Router depends on `get_google_credentials`, which verifies the Google token exists and is valid.
4. **Service Call:** `GmailService` uses the `google-api-python-client` to execute the operation on behalf of the user.

## 3. Database Architecture (MongoDB)

Handled via `src.services.nosql.mongodb.NoSqlServices` using Motor.
Key Collections:
- `users`: Core identity, encrypted passwords, roles.
- `refresh_tokens`: Hashes of active refresh tokens for session management.
- `agents`: Configurations for AI agents, linking to LLM settings and knowledge bases.
- `agentchathistories`: High-level session metadata.
- `agentchats`: Granular, per-message chat logs linked to `agentchathistories`.
- `video_jobs`: Status tracking for Celery video rendering tasks.
- `file_references`: Metadata for uploaded PDFs and scraped Webpages.

## 4. Authentication & Security Flow

Custom implementation in `src/api/custom_middleware.py`.
1. **Middleware Check:** `AuthMiddleware` runs on all non-public routes (bypassing paths in `ALLOWED_URL_PATH_WITHOUT_AUTHORIZATION`).
2. **Token Extraction:** Attempts to read `Authorization` header (`Bearer ...`), falls back to reading the `jwt` HTTP-only cookie.
3. **Validation:** Decodes JWT using `JWT_SECRET`. Verifies user existence and active status in MongoDB. Checks if the token was issued *before* a recent password change.
4. **Auto-Refresh:** If the access token is expired, but a valid `refresh_token` cookie exists, the middleware silently generates a new access/refresh pair, updates the request context, and appends the new cookies to the outgoing response.
5. **Authorization:** Injects `request.state.user` and `request.state.access` for use in specific router dependencies.

## 5. Background Jobs & Event-Driven Workflows

- **Celery + Redis + Eventlet:**
  Celery is configured in `src/core/task_processing/celery_app.py`. Due to the async nature of the system, it uses the `eventlet` pool. Heavy tasks like Video Generation (`VeoVideoGenerator`) are offloaded here. Since the core logic in `celery_tasks.py` interacts with Motor (Asyncio DB), the synchronous Celery task wraps the execution in `asyncio.run()`.
- **WebSockets (`src/video_generation/websocket_manager.py`):**
  Uses FastAPI WebSockets to broadcast job status updates to connected clients at a set interval.
- **Server-Sent Events (`src/utils/common.py`):**
  Yields `text/event-stream` responses for seamless typewriter-style chat interfaces without WebSocket overhead.

## 6. AI/ML Integrations

- **LLM Abstraction (`src/llms/`):**
  The `LLMService` normalizes interactions across providers (OpenAI, Groq, Anthropic, HuggingFace). The system dynamically maps the requested model name to the correct provider class.
- **Image Generation (`src/services/imagen.py`):**
  Supports multiple models including OpenAI DALL-E and Fal AI using base abstraction classes.
- **Speech-to-Text & Text-to-Speech:**
  Integrated with ElevenLabs and Kokoro.
- **Deep Research / GPT Researcher (`src/deep_research/`):**
  A separate internal module adapted for exhaustive multi-step web scraping, data aggregation, and report generation using LLMs.

## 7. Error Handling Strategy

1. **AppError:** A base exception class (`src/utils/upgrade_auth/app_error.py`) for expected business logic violations (e.g., "User not found").
2. **Exception Handlers:** Defined in `src/api/setup_api.py`.
    - Intercepts `AppError` -> Returns proper HTTP Status and JSON detail.
    - Intercepts `RequestValidationError` (Pydantic) -> Formats validation errors cleanly.
    - Intercepts raw `Exception` -> Returns standard HTTP 500 without exposing internal stack traces to the client, logging heavily via `loguru`.

## 8. Deployment Architecture

- **Docker:** Configured via `Dockerfile` and `docker-compose.yml`.
- **PM2 / Gunicorn:** When not using Docker, the application runs via `pm2` using the `ecosystem.config.js` file, managing standard Uvicorn/Gunicorn processes.
- **Static Assets:** `os.makedirs("outputs")` runs at startup, and FastAPI mounts `/outputs` as a static directory to serve locally generated files.

## 9. Onboarding Guide

1. **Environment Setup:** Copy `.env.example` (or define required vars in `settings.py`) to `.env`. Ensure MongoDB, Redis, and Qdrant are running locally or via Docker.
2. **Install Dependencies:** `pip install -r requirements.txt` (or via pyproject.toml).
3. **Run Application:** Execute `./scripts/run.sh` or `pm2 start ecosystem.config.js --only dev-agent-workflow`.
4. **API Testing:** Navigate to `http://localhost:8000/upgrade/0329032` (custom swagger path based on `API_SWAGGER_PATH`) to view and test available endpoints.
5. **Adding new Services:** Always create an interface in `src/services/` rather than placing logic in routers. If your service requires heavy initialization, add it to the `lifespan` function in `src/api/setup_api.py`.
