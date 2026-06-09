from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.api.v1.routers.misc import files_router
from src.api.v1.routers.workflow import (
    image_generation,
    llm,
    text_to_speech,
    web_loader,
    speech_to_text,
)
from src.api.v1.routers import webhook_router
from src.api.v1.routers.agents import (
    agents_router,
    modelcard_router,
    agent_chat,
)
from src.api.v1.routers.upgrade import chat, support_bot
from src.api.v1.routers.external import rfm_support_bot
from src.api.v1.routers.upgrade import upgrade_agents
from src.deep_research.server import server
from src.api.v1.routers.workspace import ai, google_auth, docs, drive, gmail
from src.api.v1.routers.video_gen.video_gen_routes import router as video_gen_router
from src.api.v1.routers.authentication import auth_router, user_router


def setup_and_combine_all_routers() -> APIRouter:
    router = APIRouter()

    router.include_router(
        image_generation.router,
        prefix="/generate-image",
        tags=["Image Generation", "Workflow"],
    )

    router.include_router(
        llm.router,
        prefix="/chat",
        tags=["LLM", "Workflow"],
    )

    router.include_router(
        speech_to_text.router,
        prefix="/transcribe",
        tags=["Speech-To-Text", "Workflow"],
    )

    router.include_router(
        text_to_speech.router,
        prefix="/tts",
        tags=["Text-To-Speech", "Workflow"],
    )

    router.include_router(
        web_loader.router,
        prefix="/fetch",
        tags=["Web Loader", "Workflow"],
        default_response_class=JSONResponse,
    )

    router.include_router(
        agents_router.agents_router,
        prefix="/agent",
        tags=["Manage Agents", "Agents"],
    )

    router.include_router(
        agent_chat.chat_router,
        prefix="/agent/chat",
        tags=["Agent Conversation", "Manage Agent", "Agents"],
    )

    router.include_router(
        files_router.router,
        prefix="/file",
        tags=["File Upload", "Agents"],
    )

    router.include_router(
        webhook_router.router,
        prefix="/webhook",
        tags=["Channel Webhooks"],
    )

    router.include_router(
        modelcard_router.router,
        prefix="/models",
        tags=["Available LLM Models", "Upgrade"],
    )

    router.include_router(
        chat.router,
        prefix="/upgrade/chat",
        tags=["Chat", "Upgrade"],
    )

    router.include_router(
        support_bot.router,
        prefix="/service",
        tags=["Support Bot", "Upgrade"],
    )

    router.include_router(
        upgrade_agents.router,
        prefix="/enhance",
        tags=["Upgrade Prompt Enhance", "Upgrade"],
    )

    router.include_router(
        rfm_support_bot.router,
        prefix="/service",
        tags=["Support Bot", "RFM"],
    )

    router.include_router(
        server.router, 
        tags=["GPT Researcher, Upgrade"]
    )

    # Google Workspace
    router.include_router(
        google_auth.router,
        prefix="/google-auth",
        tags=["Google Workspace Authorization"]
    )
    router.include_router(gmail.router, prefix="/gmail", tags=["Gmail"])
    router.include_router(drive.router, prefix="/drive", tags=["Drive"])
    router.include_router(docs.router, prefix="/docs", tags=["Docs"])
    router.include_router(ai.router, prefix="/ai", tags=["AI Services"])

    # Video Gen Routes
    router.include_router(
        video_gen_router,
        prefix="/video-generation",
        tags=["Video Generation"],
    )

    # Upgrade Auth Routes
    router.include_router(auth_router.router, prefix="/auth", tags=["Upgrade Authentication"])
    router.include_router(user_router.router, prefix="/users", tags=["User Management"])


    return router
