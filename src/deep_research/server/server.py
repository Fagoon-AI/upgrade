import os
import time
from typing import Optional, Dict
from datetime import datetime
from loguru import logger
from pydantic import Field
from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    Request
)
from pydantic import BaseModel
from src.deep_research.server.websocket_manager import WebSocketManager
from src.deep_research.server.server_utils import (
    sanitize_filename,
    handle_websocket_communication,
)
from src.deep_research.server.websocket_manager import run_agent
from src.deep_research.utils import write_md_to_word, write_md_to_pdf
from src.services.upgrade.chat import UpgradeChatService
from gpt_researcher.utils.enum import Tone
from src.services.document_processor import DocumentProcessor


class ResearchRequest(BaseModel):
    conversation_id: str = Field(..., description="The unique identifier for the conversation, provided by the client.")
    task: str
    report_type: Optional[str] = "research_report"
    report_source: Optional[str] = "web"
    tone: Optional[str] = "Objective"
    headers: Optional[Dict] = None

router = APIRouter()
manager = WebSocketManager()

DOC_PATH = os.getenv("DOC_PATH", "./my-docs")

async def write_report(research_request: ResearchRequest, postgres_manager, user_id: Optional[str] = None):
    """Runs the agent and stores the report using PostgreSQL."""
    conversation_id = research_request.conversation_id

    import uuid
    from src.services.api_key_resolver import setup_vibe_coder_environment

    resolved_user_id = None
    if user_id:
        try:
            resolved_user_id = uuid.UUID(str(user_id))
        except ValueError:
            pass

    if not resolved_user_id:
        try:
            from src.models.sql.models import UpgradeChatHistory
            from sqlalchemy import select
            async with postgres_manager.get_session() as session:
                res = await session.execute(
                    select(UpgradeChatHistory).where(UpgradeChatHistory.id == uuid.UUID(conversation_id))
                )
                history = res.scalars().first()
                if history:
                    resolved_user_id = history.user_id
        except Exception as e:
            logger.error(f"Error resolving user_id for vibe coder HTTP report: {e}")

    if resolved_user_id:
        await setup_vibe_coder_environment(resolved_user_id, postgres_manager)

    report_information = await run_agent(
        task=research_request.task, report_type=research_request.report_type,
        report_source=research_request.report_source, source_urls=[], document_urls=[],
        tone=Tone[research_request.tone], websocket=None, config_path="", return_researcher=True,
    )
    report, researcher = report_information

    chat_service_instance = UpgradeChatService(postgres_manager, DocumentProcessor())
    await chat_service_instance.store_user_research_request(conversation_id, research_request.task)

    research_data = {
        "research_id": conversation_id, "task": research_request.task,
        "report_type": research_request.report_type, "report_source": research_request.report_source,
        "tone": research_request.tone, "report_content": report,
        "research_images": researcher.get_research_images(), "source_urls": researcher.get_source_urls(),
        "research_costs": researcher.get_costs(), "visited_urls": list(researcher.visited_urls),
        "logs": []
    }
    await chat_service_instance.store_research_report_as_chat(research_data)

    docx_path = await write_md_to_word(report, conversation_id)
    pdf_path = await write_md_to_pdf(report, conversation_id)

    return {
        "conversation_id": conversation_id,
        "research_information": {
            "source_urls": researcher.get_source_urls(), "research_costs": researcher.get_costs(),
            "visited_urls": list(researcher.visited_urls), "research_images": researcher.get_research_images(),
        },
        "report": report, "docx_path": docx_path, "pdf_path": pdf_path,
    }

@router.post("/report/")
async def generate_report(request: Request, research_request: ResearchRequest):
    user_id = getattr(request.state, "user_id", None)
    if not user_id and getattr(request.state, "user", None):
        user_id = str(request.state.user.id)
    return await write_report(research_request, request.app.state.postgres_manager, user_id)

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try: await handle_websocket_communication(websocket, manager)
    except WebSocketDisconnect: await manager.disconnect(websocket)
