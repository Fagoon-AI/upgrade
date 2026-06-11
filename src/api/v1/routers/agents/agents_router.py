import asyncio
import uuid
import httpx
from fastapi import APIRouter, Depends, status, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from loguru import logger
from typing import Optional, Dict

from src.agents.agent_manager import AgentManager
from src.schemas.common import SuccessResponse, FailureResponse
from src.schemas.channel import ChannelConfigRequest
from src.services.rag.ingestion_manager import IngestionManager
from src.core.settings import system_setting
from src.storages.file_storage import FileStorageService
from src.storages.vectordb_storages.pgvector import PgVectorStorage
from src.services.crawl4ai_service import Crawl4AIService
from src.services.channel_adapter.channel_config_service import (
    build_channel_status,
    ensure_channel_tokens,
    get_channel_config,
    merge_channel_config,
)
from src.schemas.agents import AgentDefaultModel, KnowledgeBase

agents_router = APIRouter()


async def _register_telegram_webhook(request: Request, agent_id: str, bot_token: str, webhook_secret_token: str) -> bool:
    webhook_url = str(request.url_for("verify_webhook", channel="telegram", agent_id=agent_id))
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": webhook_secret_token,
                "allowed_updates": ["message", "edited_channel_post", "callback_query"],
            },
        )
        if response.is_success:
            data = response.json()
            return data.get("ok", False)

    return False


@agents_router.get(
    "/{agent_id}/status",
    operation_id="get_ingestion_status",
    response_model=SuccessResponse,
)
async def get_ingestion_status(
        request: Request,
        agent_id: str,
):
    """
    Retrieves the ingestion status for a given agent.
    """
    try:
        agent_manager = request.app.state.agent_manager
        # Assuming get_agent returns config with status
        agent = await agent_manager.get_agent(agent_id)

        if agent:
            channel_status = {
                channel: build_channel_status(agent.get("channel_integration", {}), channel)
                for channel in ["whatsapp", "messenger", "telegram"]
            }
            response = SuccessResponse(
                status="success",
                data={
                    "agent_id": agent_id,
                    "ingestion_status": agent.get("ingestion_status", "unknown"),
                    "channel_status": channel_status,
                },
                message="Ingestion status retrieved successfully.",
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK, content=response.model_dump()
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=FailureResponse(
                    status="fail",
                    message="Agent not found or status not available.",
                ).model_dump(),
            )
    except Exception as e:
        logger.error("Error occurred while fetching ingestion status: {}", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FailureResponse(
                status="fail",
                message="An error occurred while fetching ingestion status.",
            ).model_dump(),
        )


@agents_router.get(
    "/{agent_id}/webhook-config",
    operation_id="get_agent_webhook_config",
    response_model=SuccessResponse,
)
async def get_agent_webhook_config(request: Request, agent_id: str):
    """
    Returns generated webhook URLs and verification tokens for an agent.
    """
    try:
        agent_manager = request.app.state.agent_manager
        agent = await agent_manager.get_agent(agent_id)

        if not agent:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=FailureResponse(status="fail", message="Agent not found.").model_dump(),
            )

        agent_config = agent.get("channel_integration", {}) or {}
        changed = False

        for channel in ["whatsapp", "messenger", "telegram"]:
            before = get_channel_config(agent_config, channel)
            agent_config = ensure_channel_tokens(agent_config, channel)
            after = get_channel_config(agent_config, channel)
            if after != before:
                changed = True

        if changed:
            await agent_manager.update_agent(agent_id, {"channel_integration": agent_config})

        webhook_urls = {
            channel: str(request.url_for("verify_webhook", channel=channel, agent_id=agent_id))
            for channel in ["whatsapp", "messenger", "telegram"]
        }

        response_data = {
            "webhook_urls": webhook_urls,
            "tokens": {
                "whatsapp": get_channel_config(agent_config, "whatsapp").get("verify_token"),
                "messenger": get_channel_config(agent_config, "messenger").get("verify_token"),
                "telegram": get_channel_config(agent_config, "telegram").get("webhook_secret_token"),
            },
        }

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=SuccessResponse(
                status="success",
                data=response_data,
                message="Webhook configuration retrieved successfully.",
            ).model_dump(),
        )
    except Exception as e:
        logger.error("Error occurred while fetching webhook config: {}", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FailureResponse(
                status="fail",
                message="An error occurred while fetching webhook config.",
            ).model_dump(),
        )


@agents_router.post(
    "/{agent_id}/channel-config",
    operation_id="set_agent_channel_config",
    response_model=SuccessResponse,
)
async def set_agent_channel_config(request: Request, agent_id: str, request_body: ChannelConfigRequest):
    """
    Stores encrypted per-agent channel credentials and webhook support state.
    """
    try:
        agent_manager = request.app.state.agent_manager
        agent = await agent_manager.get_agent(agent_id)

        if not agent:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=FailureResponse(status="fail", message="Agent not found.").model_dump(),
            )

        agent_config = agent.get("channel_integration", {}) or {}
        channel = request_body.channel

        payload = {}
        if channel == "whatsapp":
            payload = {
                "phone_number_id": request_body.phone_number_id,
                "app_secret": request_body.app_secret,
                "access_token": request_body.access_token,
            }
        elif channel == "messenger":
            payload = {
                "page_id": request_body.page_id,
                "app_secret": request_body.app_secret,
                "page_access_token": request_body.page_access_token,
            }
        elif channel == "telegram":
            payload = {
                "bot_token": request_body.bot_token,
            }

        updated_config = merge_channel_config(agent_config, channel, payload)
        await agent_manager.update_agent(agent_id, {"channel_integration": updated_config})

        telegram_registered = False
        if channel == "telegram":
            telegram_config = get_channel_config(updated_config, "telegram")
            webhook_secret_token = telegram_config.get("webhook_secret_token")
            if webhook_secret_token:
                telegram_registered = await _register_telegram_webhook(
                    request,
                    agent_id,
                    request_body.bot_token,
                    webhook_secret_token,
                )
                if telegram_registered:
                    updated_config = merge_channel_config(agent_config, channel, {**payload, "verified": True})
                    await agent_manager.update_agent(agent_id, {"channel_integration": updated_config})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=SuccessResponse(
                status="success",
                data={"channel": channel, "configured": True, "telegram_registered": telegram_registered},
                message="Channel configuration stored successfully.",
            ).model_dump(),
        )
    except Exception as e:
        logger.error("Error occurred while saving channel config: {}", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FailureResponse(
                status="fail",
                message="An error occurred while saving channel configuration.",
            ).model_dump(),
        )


async def background_ingestion_task(
        agent_id: str,
        knowledge_base_data: Dict,
        postgres_manager,
        agent_manager_instance: AgentManager
):
    """Isolated background task for knowledge base ingestion using PostgreSQL."""
    logger.info(f"Isolated background task starting for agent {agent_id}.")

    try:
        vector_store = PgVectorStorage(postgres_manager=postgres_manager)
        ingestion_manager = IngestionManager(vector_store=vector_store)
        knowledge_base = KnowledgeBase(**knowledge_base_data)

        await ingestion_manager.ingest_knowledge_base(
            agent_id=agent_id,
            knowledge_base=knowledge_base
        )
        logger.info(f"Background ingestion task completed for agent {agent_id}.")

    except Exception as e:
        logger.error("Error in isolated background task for agent {}: {}", agent_id, e, exc_info=True)

@agents_router.post(path="", operation_id="create_agent_with_knowledge_base")
async def create_requested_agent(
        request: Request,
        background_tasks: BackgroundTasks,
        request_body: AgentDefaultModel,
):
    """
    Creates an agent and dispatches a background task for knowledge base ingestion.
    """
    try:
        agent_manager = request.app.state.agent_manager
        user_id = request.state.user_id
        
        agent_data = await agent_manager.create_agent(user_id, request_body)
        agent_id = agent_data["id"]

        if request_body.knowledge_base and (request_body.knowledge_base.uploaded_files or request_body.knowledge_base.urls):
            logger.info(f"Knowledge base found for agent {agent_id}. Dispatching background task.")
            background_tasks.add_task(
                background_ingestion_task,
                agent_id=agent_id,
                knowledge_base_data=request_body.knowledge_base.model_dump(),
                postgres_manager=request.app.state.postgres_manager,
                agent_manager_instance=agent_manager
            )

        response = SuccessResponse(status="success", data={"agent_id": agent_id}, message="Agent created successfully.")
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=response.model_dump(mode="json"))

    except Exception as e:
        logger.error("Failed to create agent: {}", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FailureResponse(
                status="fail",
                message="An error occurred while creating an agent.",
            ).model_dump(),
        )

@agents_router.get(
    "",
    operation_id="get_all_agent",
    response_model=SuccessResponse,
)
async def get_all_agents(
        request: Request,
):
    """
    Retrieves all agents for the current user.
    """
    try:
        agent_manager = request.app.state.agent_manager
        user_id = request.state.user_id
        all_agents = await agent_manager.list_agents(user_id)

        response = SuccessResponse(
            status="success",
            data={"agents": all_agents, "total_agents": len(all_agents)},
            message="All agents retrieved successfully.",
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=response.model_dump()
        )
    except Exception as e:
        logger.error("Error occurred while fetching agents: {}", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FailureResponse(
                status="fail",
                message="An error occurred while fetching all agents.",
            ).model_dump(),
        )


@agents_router.get(
    "/{agent_id}",
    operation_id="get_agent_details",
    response_model=SuccessResponse,
)
async def get_requested_agent_details(
        request: Request,
        agent_id: str,
):
    """
    Retrieves agent details using PostgreSQL.
    """
    try:
        agent_manager = request.app.state.agent_manager
        agent_detail = await agent_manager.get_agent(agent_id)

        if not agent_detail:
             return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=FailureResponse(status="fail", message="Agent not found.").model_dump(),
            )

        response = SuccessResponse(
            status="success",
            data={"agent": agent_detail},
            message="Agent details retrieved successfully.",
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=response.model_dump(mode="json")
        )
    except Exception as e:
        logger.error("Error occurred while fetching agent detail: {}", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FailureResponse(
                status="fail",
                message="An error occurred while fetching agent detail.",
            ).model_dump(),
        )


@agents_router.patch(
    "/{agent_id}",
    operation_id="update_agent_details",
    response_model=SuccessResponse,
)
async def update_requested_agent_details(
        request: Request,
        agent_id: str,
        data: dict,
):
    """
    Updates agent details using PostgreSQL.
    """
    try:
        from src.schemas.agents import AgentUpdateModel
        update_model = AgentUpdateModel(**data)
        
        agent_manager = request.app.state.agent_manager
        await agent_manager.update_agent(agent_id, update_model)

        response = SuccessResponse(
            status="success", data=dict(), message="Successfully updated agent detail."
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=response.model_dump()
        )
    except Exception as e:
        logger.error("Error occurred while updating agent detail: {}", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FailureResponse(
                status="fail",
                message="An error occurred while updating agent detail.",
            ).model_dump(),
        )


@agents_router.delete(
    "/{agent_id}",
    operation_id="delete_agent",
    response_model=SuccessResponse,
)
async def delete_requested_agent(
        request: Request,
        agent_id: str,
):
    """
    Deletes an agent using PostgreSQL.
    """
    try:
        agent_manager = request.app.state.agent_manager
        await agent_manager.delete_agent(agent_id)

        response = SuccessResponse(
            status="success",
            data=dict(),
            message="The requested agent has been successfully deleted.",
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=response.model_dump()
        )
    except Exception as e:
        logger.error("Error occurred while deleting agent: {}", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FailureResponse(
                status="fail",
                message="An error occurred while deleting agent.",
            ).model_dump(),
        )
