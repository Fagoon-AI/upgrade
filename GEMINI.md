# Fagoon Agents Workflow

This repository contains the backend for the Fagoon AI Agents Workflow platform, built with FastAPI. It handles complex AI orchestration, including RAG-enabled chat, background video generation, image generation, text-to-speech, and deep integration with Google Workspace.

## Tech Stack & Architecture

- **Framework:** FastAPI (Python 3.12+)
- **Package Management:** `pip` with `pyproject.toml`
- **Primary Database:** MongoDB (accessed via Motor/PyMongo async)
- **Vector Database:** Qdrant (for RAG document chunks)
- **Background Jobs:** Celery (with Redis broker, Eventlet execution pool)
- **Real-time:** Server-Sent Events (SSE) for streaming LLM responses, WebSockets for video generation status.
- **LLM/AI Integrations:** OpenAI, Anthropic, Google GenAI (Gemini/Veo), Groq, Hugging Face, Fal AI, ElevenLabs, Kokoro.
- **Architecture Pattern:** Layered/Modular (Routers -> Services -> Providers -> Data/Storage).

## Strict Layer & Module Rules

- `src/api/v1/routers/`: ONLY routing and request validation (Pydantic). Dependency injection happens here. No business logic.
- `src/services/`: Core business logic. Orchestrates calls to models, storage, and external providers.
- `src/models/` & `src/schemas/`: Pydantic models for request/response validation and MongoDB document mapping. Keep them strictly typed.
- `src/storages/`: Abstractions for file storage (Local/Cloud) and Vector DBs (`vectordb_storages/qdrant.py`).
- `src/llms/` & `src/providers/`: Wrappers for external AI API clients.
- `src/core/`: Application globals, settings (`settings.py`), database connection singletons, exception handlers.

## Key Patterns & Conventions

- **Dependency Injection:** Use FastAPI `Depends` for passing `Request` state, DB services, and current user.
- **Async First:** Almost all IO-bound operations (DB calls, external API calls) must be `async`. Blocking synchronous code (like BM25 reranking) should be offloaded to `asyncio.to_thread`.
- **Singletons in Lifespan:** Heavy clients (`httpx.AsyncClient`, `MongoDBManager`, `QdrantStorage`, `AgentManager`) are initialized once in `src/launch_server.py` lifespan and attached to `app.state`.
- **Response Streaming:** Use `async generator` functions with `send_sse_token()` and `send_sse_event()` from `src.utils.common` to stream LLM responses.

## External Services and Integrations

- **Google Workspace:** OAuth2 authentication. Can query Gmail, Drive, and Docs.
- **Crawl4AI:** Web scraping and extraction service (`src/services/crawl4ai_service.py`).
- **GPT Researcher:** Integrated for deep research capabilities (`src/deep_research/`).

## Common Commands

- **Run Dev Server:** `pm2 start ecosystem.config.js --only dev-agent-workflow` OR `./scripts/run.sh`
- **Run Celery Worker:** Typically run via standard Celery commands (e.g., `celery -A src.core.task_processing.celery_app worker -P eventlet -c 4`)

## Required Environment Variables (from `settings.py`)

- `mongodb_connection_string`, `mongodb_database_name`
- `QDRANT_DATABASE_HOST_URL`
- `JWT_SECRET`, `JWT_ALGORITHM`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, etc. (for respective features)

## What NOT to do (Anti-patterns)

- **Do NOT** put business logic inside FastAPI router functions.
- **Do NOT** use `sync` functions for database or network calls; always use async variants or thread executors.
- **Do NOT** instantiate heavy clients (like DB connections or Vector DB clients) per request. Use the `app.state` singletons.
- **Do NOT** bypass the custom `AuthMiddleware` for protected routes. Check `ALLOWED_URL_PATH_WITHOUT_AUTHORIZATION` for exceptions.
- **Do NOT** suppress or bypass Pydantic validation errors. Use `RequestValidationError` correctly.
