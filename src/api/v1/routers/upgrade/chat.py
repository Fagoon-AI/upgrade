import time
import base64
import asyncio
from datetime import datetime, timezone
from pydantic import ValidationError
from loguru import logger
from fastapi import APIRouter, Depends, File, status, UploadFile , Form, Request, Query, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse

from typing import Annotated, Any, Dict, List, Optional
from urllib.parse import unquote
from fastapi.encoders import jsonable_encoder

from src.schemas.users import Preference
from src.schemas.common import SuccessResponse, FailureResponse
from src.schemas.chat import ChatCompletionInputRequest
from src.services.nosql.postgres_services import PostgresServices
from src.core.globals import get_postgres_services

from src.utils.misc import validate_request_body
from src.schemas.upgrade_chat import ChatEventType as EventType
from src.services.upgrade.chat import UpgradeChatService
from src.models.auth_models.user_model import UserInDB
from src.storages.file_storage import FileStorageService
from src.services.document_processor import DocumentProcessor
from src.utils.common import generate_uuid

from src.schemas.chat_context import ChatContext
from src.services.chat_stream_orchestrator import ChatStreamOrchestrator
import uuid

router = APIRouter()

MAX_FILES_PER_REQUEST = 2


@router.post("", operation_id="create_upgrade_chat_session")
async def create_chat(
    request:Request,
    pg_services: PostgresServices = Depends(get_postgres_services),
):
    user_id = request.state.user_id
    try:
        document_processor = DocumentProcessor()
        chat_service = UpgradeChatService(request.app.state.postgres_manager, document_processor)
        conversation_id = await chat_service.create_upgrade_conversation(user_id)

        response = SuccessResponse(
            status="success",
            message="Successfully initiated user conversation session",
            data={"conversation_id": conversation_id}
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED, content=response.model_dump()
        )

    except Exception as e:
        logger.error(f"Unable to create chat entrypoint: {str(e)}")
        response = FailureResponse(
            status="fail",
            data=None,
            message="Unable to initiate user conversation session"
        )
        return JSONResponse(
            content=response.model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get("/{user_id}/conversations", operation_id="get_upgrade_chat")
async def get_user_conversation_history(
    request: Request,
    user_id: str,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    pg_services: PostgresServices = Depends(get_postgres_services),
):
    try:
        from src.models.sql.models import UpgradeChatHistory
        from sqlalchemy import select, func
        
        async with request.app.state.postgres_manager.get_session() as session:
            stmt = select(UpgradeChatHistory).where(UpgradeChatHistory.user_id == uuid.UUID(user_id), UpgradeChatHistory.is_deleted == False).order_by(UpgradeChatHistory.updated_at.desc()).limit(limit).offset(offset)
            res = await session.execute(stmt)
            chat_history = res.scalars().all()
            
            count_stmt = select(func.count(UpgradeChatHistory.id)).where(UpgradeChatHistory.user_id == uuid.UUID(user_id), UpgradeChatHistory.is_deleted == False)
            total_count = await session.scalar(count_stmt)

        response = SuccessResponse(
            status="success",
            data={
                "history": jsonable_encoder(chat_history),
                "total": total_count,
                "limit": limit,
                "offset": offset,
            },
            message="Successfully retrieved conversations",
        )

        return JSONResponse(
            content=response.model_dump(), status_code=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Unable to get conversation history: {str(e)}")
        response = FailureResponse(
            status="fail",
            data=None,
            message="An error occurred while retrieving conversation list",
        )
        return JSONResponse(
            content=response.model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get("/{conversation_id}", operation_id="get_upgrade_conversation_by_id")
async def get_user_conversation_by_id(
    conversation_id: str,
    request: Request,
    pg_services: PostgresServices = Depends(get_postgres_services),
):
    try:
        document_processor = DocumentProcessor()
        chat_service = UpgradeChatService(request.app.state.postgres_manager, document_processor)
        
        messages = await chat_service.get_upgrade_history(conversation_id)

        response = SuccessResponse(
            status="success",
            data={"messages": messages},
            message="Successfully retrieved conversation history"
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=response.model_dump()
        )

    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content=FailureResponse(status="fail", message="Error fetching history").model_dump()
        )


@router.delete("/{conversation_id}", operation_id="delete_upgrade_conversation")
async def delete_conversation(
    request: Request,
    conversation_id: str, 
    pg_services: PostgresServices = Depends(get_postgres_services)
):
    try:
        from src.models.sql.models import UpgradeChatHistory
        from sqlalchemy import update
        async with request.app.state.postgres_manager.get_session() as session:
            stmt = update(UpgradeChatHistory).where(UpgradeChatHistory.id == uuid.UUID(conversation_id)).values(is_deleted=True, updated_at=datetime.now(timezone.utc))
            await session.execute(stmt)
            await session.commit()
            
        response = SuccessResponse(
            status="success",
            data=dict(),
            message="Successfully deleted conversation",
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=response.model_dump()
        )

    except Exception as e:
        logger.error(f"Unable to delete conversation: {str(e)}")
        return JSONResponse(
            content=FailureResponse(status="fail", message="Error deleting conversation").model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.post("/stream", operation_id="upgrade_chat_streaming")
async def stream_chat_completion_request(
        request: Request,
        background_tasks: BackgroundTasks,
        pg_services: PostgresServices = Depends(get_postgres_services),
):
    """
    Endpoint to stream LLM Chat responses using PostgreSQL context.
    """
    input_request = None
    try:
        input_request = await validate_request_body(request, ChatCompletionInputRequest)
        user_id = request.state.user_id
        
        user_preferences = Preference() 

        chat_context = ChatContext(
            request=input_request,
            user=request.state.user,
            user_preferences=user_preferences,
            db_services=pg_services,
            postgres_manager=request.app.state.postgres_manager,
            user_id=user_id,
            http_client=request.app.state.httpx_client,
            crawl_service=request.app.state.crawl_service
        )

        orchestrator = ChatStreamOrchestrator(chat_context, background_tasks)
        return StreamingResponse(orchestrator.stream(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Error during chat streaming: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during streaming.")


@router.post("/upload-file", operation_id="upload_file_for_chat")
async def upload_file(
    request: Request,
    conversation_id: str = Form(...),
    file: UploadFile = File(...)
):
    user_id = request.state.user_id
    storage_service = FileStorageService()
    pg_manager = request.app.state.postgres_manager

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    file_id = str(uuid.uuid4())
    destination_path = f"{user_id}/{conversation_id}/{file_id}-{file.filename}"

    try:
        gcs_path = storage_service.upload_file_to_upgrade_folder(
            file_bytes=file_bytes,
            destination_path=destination_path,
            content_type=file.content_type
        )

        # Save to Postgres
        async with pg_manager.get_session() as session:
            from src.models.sql.models import FileReference
            new_file_ref = FileReference(
                id=uuid.uuid4(),
                file_id=file_id,
                user_id=uuid.UUID(user_id),
                extra_metadata={
                    "conversation_id": conversation_id,
                    "gcs_path": gcs_path,
                    "filename": file.filename,
                    "mime_type": file.content_type
                }
            )
            session.add(new_file_ref)
            await session.commit()

        return SuccessResponse(
            status="success",
            message="File uploaded successfully",
            data={"file_id": file_id, "filename": file.filename}
        )

    except Exception as e:
        logger.error(f"Failed to upload file: {e}", exc_info=True)
        return FailureResponse(status="fail", message=f"Upload failed: {e}")
