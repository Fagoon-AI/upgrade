import sys
import types

# --- Monkey Patch for older gpt-researcher compatibility ---
try:
    import langchain_core.documents
    import langchain
    
    # Patch docstore only, as Langchain 0.2 handles the rest natively with deprecation aliases
    docstore = types.ModuleType("langchain.docstore")
    docstore_document = types.ModuleType("langchain.docstore.document")
    docstore_document.Document = langchain_core.documents.Document
    docstore.document = docstore_document
    langchain.docstore = docstore
    sys.modules["langchain.docstore"] = docstore
    sys.modules["langchain.docstore.document"] = docstore_document
except ImportError:
    pass
# -----------------------------------------------------------

import os
import asyncio
import httpx
from loguru import logger
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from typing import Optional
from src.api.custom_middleware import LoggingMiddleware, AuthMiddleware
from src.api.logging_config import setup_logging
from src.api.setup_api import setup_and_combine_all_routers
from src.core.settings import system_setting
from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices
from src.utils.upgrade_auth.app_error import AppError
from src.upgrade_authentication.exceptions import app_error_handler, validation_exception_handler, generic_exception_handler
from src.video_generation.websocket_manager import periodic_status_broadcaster

from src.storages.file_storage import FileStorageService
from src.storages.vectordb_storages.pgvector import PgVectorStorage
from src.agents.agent_manager import AgentManager
from src.services.agents.chat_orchestrator import ChatOrchestrator
from src.services.crawl4ai_service import Crawl4AIService
from src.services.agents.chat import AgentChatService
import logging

logging.getLogger("passlib").setLevel(logging.WARNING)
logging.getLogger("pdfminer").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.INFO)

setup_logging()

postgres_manager_instance_local: Optional[PostgresManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global postgres_manager_instance_local
    logger.info("Application starting (Strict PostgreSQL Mode)...")

    # Create 'outputs' directory and mount static files
    os.makedirs("outputs", exist_ok=True)
    app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

    app.state.httpx_client = httpx.AsyncClient(
        http2=True,
        follow_redirects=True,
        timeout=httpx.Timeout(10.0, connect=3.0),
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
    )
    logger.info("Singleton httpx.AsyncClient initialized.")

    # Initialize PostgresManager
    if system_setting.DATABASE_URL:
        postgres_manager_instance_local = PostgresManager(system_setting.DATABASE_URL)
        app.state.postgres_manager = postgres_manager_instance_local
        logger.info("PostgresManager initialized and connected via lifespan.")
    else:
        logger.critical("DATABASE_URL is not set! PostgreSQL is required for this application.")
        raise RuntimeError("DATABASE_URL is missing.")

    # Starts the periodic status broadcaster
    asyncio.create_task(periodic_status_broadcaster())

    app.state.crawl_service = Crawl4AIService()
    logger.info("Singleton Crawl4AIService initialized.")

    app.state.file_storage = FileStorageService()
    logger.info("Singleton FileStorageService initialized.")

    app.state.vector_store = PgVectorStorage(
        postgres_manager=postgres_manager_instance_local,
        vector_dim=1536
    )
    logger.info("Singleton PgVectorStorage initialized.")

    app.state.agent_manager = AgentManager(
        postgres_manager_instance_local,
        app.state.file_storage
    )
    logger.info("Singleton AgentManager initialized.")

    app.state.agent_chat_service = AgentChatService(
        postgres_manager_instance_local
    )
    logger.info("Singleton AgentChatService initialized.")

    app.state.chat_orchestrator = ChatOrchestrator(
        agent_manager=app.state.agent_manager,
        vector_store=app.state.vector_store,
        chat_service=app.state.agent_chat_service
    )
    logger.info("Singleton ChatOrchestrator initialized.")

    yield

    logger.info("Application shutting down...")
    if hasattr(app.state, "httpx_client"):
        await app.state.httpx_client.aclose()
        logger.info("Singleton httpx.AsyncClient connection closed.")

    if hasattr(app.state, "crawl_service"):
        await app.state.crawl_service.close()
        logger.info("Crawl4AIService instance closed.")

    if postgres_manager_instance_local:
        await postgres_manager_instance_local.close()
        logger.info("PostgresManager connection closed during shutdown.")

app = FastAPI(
    title=system_setting.PROJECT_NAME,
    lifespan=lifespan,
    redoc_url=None,
    docs_url=system_setting.API_SWAGGER_PATH,
    exception_handlers={
            AppError: app_error_handler,
            RequestValidationError: validation_exception_handler,
            Exception: generic_exception_handler,
    },
    openapi_tags=[
        {"name": "Google Authorization", "description": "Endpoints for Google OAuth2.0"},
        {"name": "Gmail", "description": "Endpoints for Gmail operations"},
        {"name": "Drive", "description": "Endpoints for Google Drive operations"},
        {"name": "Docs", "description": "Endpoints for Google Docs operations"},
        {"name": "AI Services", "description": "Endpoints for AI-powered features like summarization and reply generation"},
    ],
    security=[{"APIKeyHeader": []}],
    swagger_ui_parameters={"docExpansion": "none"},
    swagger_ui_init_oauth={
        "clientId": system_setting.GOOGLE_CLIENT_ID,
        "scopes": " ".join(system_setting.GOOGLE_AUTH_SCOPES),
    }
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=system_setting.ALLOWED_CORS_ORIGIN,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
)

app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
app.include_router(setup_and_combine_all_routers(), prefix=system_setting.API_V1_STR)
