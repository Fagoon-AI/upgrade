from typing import List, Optional
import uuid
from fastapi import APIRouter, UploadFile, File, status, Form, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from src.constants import MAX_FILE_SIZE
from src.core.globals import get_postgres_services
from src.schemas.common import SuccessResponse, FailureResponse
from src.services.agents.file_service import FileService
from src.storages.file_storage import FileStorageService
from src.services.nosql.postgres_services import PostgresServices
from src.services.upgrade.chat import UpgradeChatService
from src.services.document_processor import DocumentProcessor
from src.utils.common import generate_id, generate_uuid


router = APIRouter()

file_storage_service = FileStorageService()
file_service = FileService(file_storage_service)


@router.post("", operation_id="upload_agent_file_to_storage")
async def upload_agent_file_to_storage(
    request: Request,
    user_id: Optional[str] = Form(None),
    agent_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
):
    # Use request.state.user_id if Form user_id is missing or 'undefined'
    effective_user_id = user_id
    if not effective_user_id or effective_user_id == "undefined":
        effective_user_id = getattr(request.state, "user_id", None)
    
    if not effective_user_id:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "User identification missing."}
        )

    if not agent_id or agent_id == "" or agent_id == "undefined":
        agent_id = str(uuid.uuid4())

    try:
        uploaded_files = await file_service.process_and_upload_files(effective_user_id, agent_id, files)
        has_errors = any(item.get("error") for item in uploaded_files)
        message = "Files uploaded successfully."
        if has_errors:
            message = "Files processed, but some uploads failed. Check file metadata for details."

        result = SuccessResponse(
            status="success",
            message=message,
            data={"agent_id": agent_id, "files": uploaded_files},
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=result.model_dump())

    except Exception as e:
        logger.exception("Failed to upload files: {}", e)
        result = FailureResponse(status="fail", message="File upload failed.")
        return JSONResponse(status_code=500, content=result.model_dump())


@router.post("/upload", operation_id="upload_upgrade_file_to_storage")
async def upload_upgrade_file_to_storage(
    request: Request,
    user_id: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    pg_services: PostgresServices = Depends(get_postgres_services)
):
    # Use request.state.user_id if Form user_id is missing or 'undefined'
    effective_user_id = user_id
    if not effective_user_id or effective_user_id == "undefined":
        effective_user_id = getattr(request.state, "user_id", None)

    if not effective_user_id:
         return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "User identification missing."}
        )

    for file in files:
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File '{file.filename}' too large.")
        file.file.seek(0)

    convo_id = conversation_id
    if not convo_id or not convo_id.strip() or convo_id == "undefined":
        convo_id = str(uuid.uuid4())
        chat_service = UpgradeChatService(request.app.state.postgres_manager, DocumentProcessor())
        await chat_service.create_upgrade_conversation(effective_user_id)

    try:
        uploaded_files = await file_service.save_file_to_bucket(effective_user_id, convo_id, files)
        result = SuccessResponse(
            status="success",
            message="Files uploaded successfully.",
            data={"files": uploaded_files, "conversation_id": convo_id}
        )
        return JSONResponse(status_code=200, content=result.model_dump())

    except Exception as e:
        logger.exception("Failed to upload files: {}", e)
        return JSONResponse(status_code=500, content={"detail": "Upload failed"})
