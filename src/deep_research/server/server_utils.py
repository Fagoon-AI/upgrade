import asyncio
import json
import os
import re
import time
import traceback
from typing import Awaitable, Dict, Any, List, TYPE_CHECKING
from src.deep_research.utils import write_md_to_pdf, write_md_to_word, write_text_to_md
from datetime import datetime
from loguru import logger
import uuid

if TYPE_CHECKING:
    from src.deep_research.server.websocket_manager import WebSocketManager

from src.services.upgrade.chat import UpgradeChatService
from gpt_researcher.utils.enum import Tone
from src.services.document_processor import DocumentProcessor
from src.services.nosql.postgres_services import PostgresServices

class CustomLogsHandler:
    def __init__(self, websocket: Any):
        self.websocket = websocket
        self.log_buffer: List[Dict[str, Any]] = []

    async def send_json(self, data: Dict[str, Any]) -> None:
        if data.get('type') == 'logs':
            output = data.get('output', '')
            if "Researching" in output: formatted_output = f"🤔 {output}"
            elif "Scraping" in output: formatted_output = f"🌐 {output}"
            elif "Analyzing" in output: formatted_output = f"Analysing {output}"
            elif "Generating" in output: formatted_output = f"✍️ {output}"
            else: formatted_output = f"ℹ️ {output}"

            websocket_data = {"type": "logs", "output": formatted_output}
            self.log_buffer.append({"type": "log", "data": output})

            if self.websocket: await self.websocket.send_json(websocket_data)
        else:
            if self.websocket: await self.websocket.send_json(data)

    def get_buffered_logs(self) -> List[Dict[str, Any]]:
        return self.log_buffer


def sanitize_filename(filename: str) -> str:
    prefix, timestamp, *task_parts = filename.split('_')
    task = '_'.join(task_parts)
    max_task_length = 255 - len(os.getcwd()) - 24 - 5 - 10 - 6 - 5
    truncated_task = task[:max_task_length] if len(task) > max_task_length else task
    sanitized = f"{prefix}_{timestamp}_{truncated_task}"
    return re.sub(r"[^\w\s-]", "", sanitized).strip()

async def handle_start_command(websocket, data: str, manager: 'WebSocketManager'):
    logger.info("Received start command via websocket: {}", data)
    try:
        json_data = json.loads(data[len("start") :].strip())
        (
            conversation_id, task, report_type, source_urls, document_urls,
            tone_str, headers, report_source, query_domains,
        ) = extract_command_data(json_data)

        if not conversation_id or not task or not report_type:
            await websocket.send_json({"type": "logs", "output": "Error: Missing conversation_id, task, or report_type."})
            return

        logger.info("Starting research for conversation_id: {}", conversation_id)

        postgres_manager = websocket.app.state.postgres_manager
        chat_service_instance = UpgradeChatService(postgres_manager, DocumentProcessor())
        await chat_service_instance.store_user_research_request(conversation_id, task)

        logs_handler = CustomLogsHandler(websocket)
        report_info = await manager.start_streaming(
            task=task, report_type=report_type, report_source=report_source,
            source_urls=source_urls, document_urls=document_urls, tone=tone_str,
            websocket=logs_handler, headers=headers, query_domains=query_domains,
        )
        report_content, researcher = report_info

        research_data = {
            "research_id": conversation_id,
            "task": task,
            "report_type": report_type,
            "report_source": report_source,
            "tone": tone_str,
            "report_content": report_content,
            "research_images": researcher.get_research_images(),
            "source_urls": researcher.get_source_urls(),
            "research_costs": researcher.get_costs(),
            "visited_urls": list(researcher.visited_urls),
            "logs": logs_handler.get_buffered_logs()
        }

        await chat_service_instance.store_research_report_as_chat(research_data)

        await websocket.send_json({"type": "logs", "output": f"✅ Research report saved to DB with ID: {conversation_id}"})
        await websocket.send_json({"type": "report_complete", "report": report_content})
        await websocket.send_json({"type": "logs", "output": "[DONE]"})

    except json.JSONDecodeError:
        await websocket.send_json({"type": "logs", "output": "Error: Invalid JSON format."})
    except Exception as e:
        logger.error("Error handling start command: {}", e, exc_info=True)
        await websocket.send_json({"type": "logs", "output": f"An unexpected error occurred: {e}"})

async def handle_human_feedback(data: str):
    feedback_data = json.loads(data[14:])  # Remove "human_feedback" prefix
    print(f"Received human feedback: {feedback_data}")

async def handle_chat(websocket, data: str, manager):
    json_data = json.loads(data[4:])
    print(f"Received chat message: {json_data.get('message')}")
    await manager.chat(json_data.get("message"), websocket)

async def generate_report_files(report: str, filename: str) -> Dict[str, str]:
    pdf_path = await write_md_to_pdf(report, filename)
    docx_path = await write_md_to_word(report, filename)
    md_path = await write_text_to_md(report, filename)
    return {"pdf": pdf_path, "docx": docx_path, "md": md_path}


async def send_file_paths(websocket, file_paths: Dict[str, str]):
    await websocket.send_json({"type": "path", "output": file_paths})


async def handle_websocket_communication(websocket, manager):
    running_task: asyncio.Task | None = None

    def run_long_running_task(awaitable: Awaitable) -> asyncio.Task:
        async def safe_run():
            try:
                await awaitable
            except asyncio.CancelledError:
                logger.info("Task cancelled.")
                raise
            except Exception as e:
                logger.error("Error running task: {}\n{}", e, traceback.format_exc())
                await websocket.send_json(
                    {
                        "type": "logs",
                        "content": "error",
                        "output": f"Error: {e}",
                    }
                )

        return asyncio.create_task(safe_run())

    try:
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")

                elif running_task and not running_task.done():
                    logger.warning(
                        "Received request while task is already running. Request data preview: {}...", data[: min(20, len(data))]
                    )
                    await websocket.send_json(
                        {
                            "types": "logs",
                            "output": "Task already running. Please wait.",
                        }
                    )

                elif data.startswith("start"):
                    running_task = run_long_running_task(
                        handle_start_command(websocket, data, manager)
                    )

                elif data.startswith("human_feedback"):
                    running_task = run_long_running_task(handle_human_feedback(data))

                elif data.startswith("chat"):
                    running_task = run_long_running_task(
                        handle_chat(websocket, data, manager)
                    )

                else:
                    print("Error: Unknown command or not enough parameters provided.")

            except Exception as e:
                print(f"WebSocket error: {e}")
                break
    finally:
        if running_task and not running_task.done():
            running_task.cancel()

def extract_command_data(json_data: Dict) -> tuple:
    return (
        json_data.get("conversation_id"),
        json_data.get("task"),
        json_data.get("report_type"),
        json_data.get("source_urls"),
        json_data.get("document_urls"),
        json_data.get("tone"),
        json_data.get("headers", {}),
        json_data.get("report_source"),
        json_data.get("query_domains", []),
    )
