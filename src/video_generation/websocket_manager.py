import asyncio
from typing import Dict, Set
from loguru import logger

from fastapi import WebSocket, WebSocketDisconnect



class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.processing_job_ids: Set[str] = set()

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
        logger.info("WebSocket connected for job_id {}: {}", job_id, websocket.client)

    def disconnect(self, websocket: WebSocket, job_id: str):
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(
                websocket
            )
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
                self.processing_job_ids.discard(job_id)
        logger.info("WebSocket disconnected for job_id {}: {}", job_id, websocket.client)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            logger.warning(
                "Attempted to send to a disconnected WebSocket: {}", websocket.client
            )
        except Exception as e:
            logger.error("Error sending WebSocket message: {} to {}", e, websocket.client)

    async def broadcast_to_job_id(self, job_id: str, message: dict):
        if job_id not in self.active_connections:
            return

        disconnected_sockets = []
        for connection in list(self.active_connections[job_id]):
            try:
                await connection.send_json(message)
                logger.debug(
                    "Broadcasted update for job {} to {}", job_id, connection.client
                )
            except WebSocketDisconnect:
                logger.warning(
                    "WebSocket broadcast: Client {} for job {} disconnected during send.", connection.client, job_id
                )
                disconnected_sockets.append(connection)
            except Exception as e:
                logger.error(
                    "Error broadcasting to WebSocket for job {}: {} to {}", job_id, e, connection.client,
                    exc_info=True,
                )
                disconnected_sockets.append(
                    connection
                )

        for sock in disconnected_sockets:
            self.disconnect(sock, job_id)

    def add_processing_job(self, job_id: str):
        self.processing_job_ids.add(job_id)
        logger.debug("Added job {} to processing_job_ids set.", job_id)

    def remove_processing_job(self, job_id: str):
        self.processing_job_ids.discard(job_id)
        logger.debug("Removed job {} from processing_job_ids set.", job_id)


manager = ConnectionManager()


async def periodic_status_broadcaster():
    """
    Periodically checks the status of jobs that have active WebSocket listeners
    and are currently being processed (or were recently submitted).
    This is a simple polling mechanism. For high performance, use a Pub/Sub system (e.g., Redis).
    """
    from src.video_gen_crud.crud import get_video_job_from_db


    while True:
        await asyncio.sleep(3)
        job_ids_to_check = list(manager.active_connections.keys())

        if not job_ids_to_check:
            continue

        for job_id in job_ids_to_check:
            if job_id not in manager.active_connections:
                continue

            try:
                job_details = await get_video_job_from_db(job_id=job_id)
                if job_details:
                    if job_details.status in [
                        JobStatus.PENDING,
                        JobStatus.ENHANCING,
                        JobStatus.PROCESSING,
                    ]:
                        await manager.broadcast_to_job_id(
                            job_id, job_details.model_dump()
                        )
                    elif job_details.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                        await manager.broadcast_to_job_id(
                            job_id, job_details.model_dump()
                        )
            except Exception as e:
                logger.error(
                    "Error in periodic_status_broadcaster for job {}: {}", job_id, e,
                    exc_info=True,
                )
