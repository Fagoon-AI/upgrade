import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, status, Form, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import select

from src.constants import MAX_FILE_SIZE
from src.core.globals import get_postgres_services
from src.schemas.common import SuccessResponse, FailureResponse
from src.services.agents.file_service import FileService
from src.storages.file_storage import FileStorageService
from src.services.nosql.postgres_services import PostgresServices
from src.services.upgrade.chat import UpgradeChatService
from src.services.document_processor import DocumentProcessor
from src.utils.common import generate_id, generate_uuid
from src.models.sql.models import GeneratedImage

router = APIRouter()

@router.get("/image/{image_id}", operation_id="get_generated_image")
async def get_generated_image(
    request: Request,
    image_id: str
):
    try:
        import uuid
        parsed_id = uuid.UUID(image_id)
        async with request.app.state.postgres_manager.get_session() as session:
            stmt = select(GeneratedImage).where(GeneratedImage.id == parsed_id)
            result = await session.execute(stmt)
            image_record = result.scalar_one_or_none()
            
            if not image_record:
                raise HTTPException(status_code=404, detail="Image not found")
                
            return Response(content=image_record.image_data, media_type=image_record.content_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid image ID format")
    except Exception as e:
        logger.error(f"Failed to retrieve image {image_id}: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving image")

file_storage_service = FileStorageService()
file_service = FileService(file_storage_service)


@router.post("", operation_id="upload_agent_file_to_storage")
async def upload_agent_file_to_storage(
    request: Request,
    user_id: Optional[str] = Form(None),
    agent_id: Optional[str] = Form(None),
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

    if not agent_id or agent_id == "" or agent_id == "undefined":
        agent_id = str(uuid.uuid4())

    try:
        # Pass pg_services for automatic registration in user Knowledge Base
        uploaded_files = await file_service.process_and_upload_files(
            user_id=effective_user_id,
            agent_id=agent_id,
            files=files,
            pg_services=pg_services
        )
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


@router.get("/knowledge", operation_id="list_knowledge_base_files")
async def list_knowledge_base_files(
    request: Request,
    pg_services: PostgresServices = Depends(get_postgres_services)
):
    effective_user_id = getattr(request.state, "user_id", None)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="User identification missing.")

    try:
        user_uuid = uuid.UUID(effective_user_id)
        file_refs = await pg_services.get_file_references_by_user_id(user_uuid)
        
        result = []
        for ref in file_refs:
            download_url = file_storage_service.generate_signed_url(ref.file_id)
            result.append({
                "id": str(ref.id),
                "file_id": ref.file_id,
                "created_at": ref.created_at.isoformat(),
                "metadata": ref.extra_metadata,
                "url": download_url
            })
            
        return JSONResponse(status_code=200, content={"status": "success", "files": result})
    except Exception as e:
        logger.exception("Failed to list knowledge base files: {}", e)
        return JSONResponse(status_code=500, content={"status": "fail", "message": "Failed to list files."})


@router.post("/knowledge", operation_id="upload_files_to_knowledge_base")
async def upload_files_to_knowledge_base(
    request: Request,
    files: List[UploadFile] = File(...),
    pg_services: PostgresServices = Depends(get_postgres_services)
):
    effective_user_id = getattr(request.state, "user_id", None)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="User identification missing.")

    try:
        general_kb_id = "general_knowledge"
        uploaded_files = await file_service.process_and_upload_files(
            user_id=effective_user_id,
            agent_id=general_kb_id,
            files=files,
            pg_services=pg_services
        )
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "Files uploaded to general Knowledge Base successfully.",
            "files": uploaded_files
        })
    except Exception as e:
        logger.exception("Failed to upload files to Knowledge Base: {}", e)
        return JSONResponse(status_code=500, content={"status": "fail", "message": str(e)})


@router.delete("/knowledge/{file_id:path}", operation_id="delete_knowledge_base_file")
async def delete_knowledge_base_file(
    request: Request,
    file_id: str,
    pg_services: PostgresServices = Depends(get_postgres_services)
):
    effective_user_id = getattr(request.state, "user_id", None)
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="User identification missing.")

    try:
        user_uuid = uuid.UUID(effective_user_id)
        
        # 1. Delete from DB
        success = await pg_services.delete_file_reference(file_id, user_uuid)
        if not success:
            raise HTTPException(status_code=404, detail="File reference not found.")
            
        # 2. Try to delete the physical file if it's local
        try:
            local_path = os.path.join("outputs", file_id)
            if os.path.exists(local_path):
                os.remove(local_path)
                logger.info(f"Deleted physical file locally from {local_path}")
        except Exception as file_err:
            logger.warning(f"Failed to delete local physical file: {file_err}")

        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "File successfully deleted from Knowledge Base."
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("Failed to delete Knowledge Base file: {}", e)
        return JSONResponse(status_code=500, content={"status": "fail", "message": str(e)})
