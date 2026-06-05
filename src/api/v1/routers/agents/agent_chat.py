import asyncio
from fastapi import APIRouter, Depends, status, Request, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
import uuid

from src.schemas.agents_chat import (
    AgentChatResponseModel,
    AgentChatInputRequest,
    CreateAgentChatInputRequest,
    EventType,
    TitleGenerationInputRequest
)
from src.agents.agent_manager import AgentManager
from src.schemas.agent_enums import ToolType
from src.schemas.llm import BaseLLMConfig
from src.schemas.common import SuccessResponse, FailureResponse, ConversationRoleEnum
from src.services.agents.chat import AgentChatService
from src.services.nosql.postgres_services import PostgresServices
from src.core.globals import get_postgres_services
from src.utils.common import send_event_data


chat_router = APIRouter()

class ConversationSummary(BaseModel):
    id: str
    agent_id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime

@chat_router.post("", operation_id="create_agent_chat_entrypoint")
async def create_chat(
    request: Request,
    input_request: CreateAgentChatInputRequest,
):
    try:
        chat_service = request.app.state.agent_chat_service
        conversation_id = await chat_service.create_conversation(
            user_id=input_request.user_id,
            agent_id=input_request.agent_id
        )
        
        response = SuccessResponse(
            status="success",
            message="Successfully created chat entry",
            data=AgentChatResponseModel(conversation_id=conversation_id).model_dump(),
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED, content=response.model_dump()
        )

    except Exception as e:
        logger.error(f"Unable to create chat entrypoint: {str(e)}")
        response = FailureResponse(
            status="fail", data=None, message="Unable to create chat entrypoint"
        )
        return JSONResponse(
            content=response.model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@chat_router.get("/{agent_id}/conversations", operation_id="get_all_chat_history")
async def get_all_conversations_list(
        request: Request,
        agent_id: str
):
    try:
        chat_service = request.app.state.agent_chat_service
        user_id = request.state.user_id
        
        chat_list = await chat_service.list_user_conversations(user_id, agent_id)

        response = SuccessResponse(
            status="success",
            data={"history": chat_list, "total": len(chat_list)},
            message="Successfully retrieved conversations",
        )
        return JSONResponse(
            content=response.model_dump(), status_code=status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Unable to get conversation history: {e}", exc_info=True)
        return JSONResponse(
            content=FailureResponse(status="fail", message="An error occurred").model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@chat_router.get("/{conversation_id}", operation_id="get_chat_by_id")
async def get_chat(
    request: Request,
    conversation_id: str
):
    try:
        chat_service = request.app.state.agent_chat_service
        messages = await chat_service.get_history(conversation_id)
        
        response = SuccessResponse(
            status="success",
            data=messages,
            message="Successfully retrieved conversation history",
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=response.model_dump()
        )

    except Exception as e:
        logger.error(f"Failed to get conversation history: {str(e)}")
        return JSONResponse(
            content=FailureResponse(status="fail", message="An error occurred").model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@chat_router.delete("/{conversation_id}", operation_id="delete_agent_conversation")
async def delete_conversation(
    request: Request,
    conversation_id: str
):
    try:
        chat_service = request.app.state.agent_chat_service
        await chat_service.delete_conversation(conversation_id)
        
        response = SuccessResponse(
            status="success",
            data=dict(),
            message="Successfully deleted agent conversation",
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=response.model_dump()
        )

    except Exception as e:
        logger.error(f"Unable to delete conversation: {str(e)}")
        return JSONResponse(
            content=FailureResponse(status="fail", message="An error occurred").model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@chat_router.post("/stream", operation_id="agent_chat_streaming_rag")
async def agent_chat_streaming(
        request: Request,
        input_request: AgentChatInputRequest,
):
    """
    Handles RAG chat streaming using ChatOrchestrator and PostgreSQL.
    """
    orchestrator = request.app.state.chat_orchestrator
    user_id = request.state.user_id
    
    # Optional LLM Config override
    llm_config = BaseLLMConfig(
        model=system_setting.SMART_MODEL_ID,
        provider=system_setting.SMART_MODEL_PROVIDER
    )

    async def event_generator():
        async for token in orchestrator.stream_chat(
            user_id=user_id,
            agent_id=input_request.agent_id,
            history_id=input_request.conversation_id,
            message=input_request.message,
            llm_config=llm_config
        ):
            # Wrap token in SSE event
            yield f"data: {token}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
