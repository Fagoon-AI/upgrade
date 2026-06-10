import asyncio
from typing import Dict, List
from loguru import logger
from fastapi import WebSocket

from src.deep_research.report_type import BasicReport, DetailedReport
from src.deep_research.chat import ChatAgentWithMemory

from gpt_researcher.utils.enum import ReportType, Tone
from gpt_researcher.actions import stream_output  
from src.deep_research.server.server_utils import CustomLogsHandler


class WebSocketManager:
    """Manage websockets"""

    def __init__(self):
        """Initialize the WebSocketManager class."""
        self.active_connections: List[WebSocket] = []
        self.sender_tasks: Dict[WebSocket, asyncio.Task] = {}
        self.message_queues: Dict[WebSocket, asyncio.Queue] = {}
        self.chat_agent = None

    async def start_sender(self, websocket: WebSocket):
        """Start the sender task."""
        queue = self.message_queues.get(websocket)
        if not queue:
            return

        while True:
            try:
                message = await queue.get()
                if message is None:  # Shutdown signal
                    break

                if websocket in self.active_connections:
                    if message == "ping":
                        await websocket.send_text("pong")
                    else:
                        await websocket.send_text(message)
                else:
                    break
            except Exception as e:
                print(f"Error in sender task: {e}")
                break

    async def connect(self, websocket: WebSocket):
        """Connect a websocket."""
        try:
            await websocket.accept()
            self.active_connections.append(websocket)
            self.message_queues[websocket] = asyncio.Queue()
            self.sender_tasks[websocket] = asyncio.create_task(
                self.start_sender(websocket)
            )
        except Exception as e:
            print(f"Error connecting websocket: {e}")
            if websocket in self.active_connections:
                await self.disconnect(websocket)

    async def disconnect(self, websocket: WebSocket):
        """Disconnect a websocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            if websocket in self.sender_tasks:
                self.sender_tasks[websocket].cancel()
                await self.message_queues[websocket].put(None)
                del self.sender_tasks[websocket]
            if websocket in self.message_queues:
                del self.message_queues[websocket]
            try:
                await websocket.close()
            except:
                pass  # Connection might already be closed

    # async def start_streaming(
    #     self,
    #     task,
    #     report_type,
    #     report_source,
    #     source_urls,
    #     document_urls,
    #     tone,
    #     websocket,
    #     headers=None,
    #     query_domains=[],
    # ):
    #     """Start streaming the output."""
    #     tone = Tone[tone]
    #     # add customized JSON config file path here
    #     config_path = "default"
    #     report = await run_agent(
    #         task,
    #         report_type,
    #         report_source,
    #         source_urls,
    #         document_urls,
    #         tone,
    #         websocket,
    #         headers=headers,
    #         query_domains=query_domains,
    #         config_path=config_path,
    #     )
    #     # Create new Chat Agent whenever a new report is written
    #     self.chat_agent = ChatAgentWithMemory(report, config_path, headers)
    #     return report


    # NEW CODE
    async def start_streaming(
            self,
            task,
            report_type,
            report_source,
            source_urls,
            document_urls,
            tone, # This will be the string version of tone (e.g., "Objective")
            websocket,
            headers=None,
            query_domains=[],
    ):
        """Start streaming the output and return the report and researcher."""
        try:
            # Convert tone string to Tone enum if it's not already
            if isinstance(tone, str):
                tone_enum = Tone[tone]
            else:
                tone_enum = tone # Assume it's already a Tone enum if not a string

            config_path = "default" # Using the "default" config path as provided in your snippet

            report_information = await run_agent(
                task=task,
                report_type=report_type,
                report_source=report_source,
                source_urls=source_urls,
                document_urls=document_urls,
                tone=tone_enum,
                websocket=websocket,
                headers=headers,
                query_domains=query_domains,
                config_path=config_path,
                return_researcher=True
            )

            logger.debug("Report information from run_agent: Type={}, Content={}", type(report_information), report_information)

            if report_type != "multi_agents" and isinstance(report_information, tuple) and len(report_information) == 2:
                report, researcher = report_information
            else:
                report = report_information
                researcher = None

            self.chat_agent = ChatAgentWithMemory(report, config_path, headers)

            logger.debug("Returning from start_streaming: Report={}, Researcher={}", report, researcher)
            return report, researcher

        except Exception as e:
            logger.error("Error in start_streaming: {}", e, exc_info=True)
            return "An error occurred during research generation.", None

    async def chat(self, message, websocket):
        """Chat with the agent based message diff"""
        if self.chat_agent:
            await self.chat_agent.chat(message, websocket)
        else:
            await websocket.send_json(
                {
                    "type": "chat",
                    "content": "Knowledge empty, please run the research first to obtain knowledge",
                }
            )


async def run_agent(
    task,
    report_type,
    report_source,
    source_urls,
    document_urls,
    tone: Tone,
    websocket,
    stream_output=stream_output,
    headers=None,
    query_domains=[],
    config_path="",
    return_researcher=False,
):
    """Run the agent."""
    logs_handler = CustomLogsHandler(websocket, task)

    if report_type == ReportType.DetailedReport.value:
        researcher = DetailedReport(
            query=task,
            query_domains=query_domains,
            report_type=report_type,
            report_source=report_source,
            source_urls=source_urls,
            document_urls=document_urls,
            tone=tone,
            config_path=config_path,
            websocket=logs_handler,  # Use logs_handler instead of raw websocket
            headers=headers,
        )
        report = await researcher.run()

    else:
        researcher = BasicReport(
            query=task,
            query_domains=query_domains,
            report_type=report_type,
            report_source=report_source,
            source_urls=source_urls,
            document_urls=document_urls,
            tone=tone,
            config_path=config_path,
            websocket=logs_handler,  # Use logs_handler instead of raw websocket
            headers=headers,
        )
        report = await researcher.run()

    if report_type != "multi_agents" and return_researcher:
        return report, researcher.gpt_researcher
    else:
        return report
