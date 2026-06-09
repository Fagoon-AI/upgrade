import asyncio
import uuid
from fastapi import APIRouter, Depends, status, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from loguru import logger
from typing import Optional, Dict

from src.agents.agent_manager import AgentManager
from src.schemas.common import SuccessResponse, FailureResponse
from src.services.rag.ingestion_manager import IngestionManager
from src.core.settings import system_setting
from src.storages.file_storage import FileStorageService
from src.storages.vectordb_storages.pgvector import PgVectorStorage
from src.services.crawl4ai_service import Crawl4AIService
from src.schemas.agents import AgentDefaultModel, KnowledgeBase

agents_router = APIRouter()

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
            response = SuccessResponse(
                status="success",
                data={"agent_id": agent_id, "ingestion_status": agent.get("ingestion_status", "unknown")},
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
