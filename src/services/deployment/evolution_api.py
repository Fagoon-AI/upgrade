import asyncio
import httpx
from loguru import logger
from fastapi import WebSocket
from typing import Dict, Any, Optional
from src.core.settings import Settings

system_settings = Settings()

EVOLUTION_API_URL = system_settings.EVOLUTION_API_URL
EVOLUTION_API_KEY = system_settings.EVOLUTION_API_KEY
WEBHOOK_URL = system_settings.WEBHOOK_URL

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, agent_id: str):
        await websocket.accept()
        self.active_connections[agent_id] = websocket
        logger.info(f"WebSocket connected for agent: {agent_id}")

    def disconnect(self, agent_id: str):
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]
            logger.info(f"WebSocket disconnected for agent: {agent_id}")

    async def send_event(self, agent_id: str, event_type: str, data: dict):
        if agent_id in self.active_connections:
            websocket = self.active_connections[agent_id]
            try:
                await websocket.send_json({"event": event_type, "data": data})
            except Exception as e:
                logger.error(f"Failed to send WS event to {agent_id}: {e}")
                self.disconnect(agent_id)

ws_manager = ConnectionManager()

class EvolutionAPIService:
    def __init__(self):
        self.base_url = 'http://localhost:8080'
        self.headers = {
            'apikey': 'fagoon-super-secret-password-12345!',
            'Content-Type': 'application/json'
        }

    async def _make_request(self, method: str, endpoint: str, payload: dict = None) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}{endpoint}"
            print(f"!!! DEBUG: EXACT URL IS -> '{url}' !!!")
            try:
                if method == 'POST':
                    response = await client.post(url, json=payload, headers=self.headers, timeout=15.0)
                elif method == 'GET':
                    response = await client.get(url, headers=self.headers, timeout=15.0)
                elif method == 'DELETE':
                    response = await client.delete(url, headers=self.headers, timeout=15.0)
                else:
                    return None
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Evolution API Request Error [{method} {endpoint}]: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"EVOLUTION SAYS: {e.response.text}")
                return None

    async def create_instance(self, agent_id: str) -> dict:
        create_endpoint = '/instance/create'
        instance_name = agent_id if agent_id.startswith('agent-') else f"agent-{agent_id}"
        
        payload = {
            'instanceName': instance_name,
            'qrcode': True,
            'webhook': f"http://host.docker.internal:8000/api/v1/whatsapp-session/webhook/{instance_name}",
            'events': ['QRCODE_UPDATED', 'CONNECTION_UPDATE', 'MESSAGES_UPSERT']
        }
        
        await self._make_request('POST', create_endpoint, payload=payload)
        
        await asyncio.sleep(3.5)
        
        connect_endpoint = f"/instance/connect/{instance_name}?qr=true"
        connect_response = await self._make_request('GET', connect_endpoint)
        
        return connect_response if connect_response else {}

    async def delete_instance(self, agent_id: str) -> bool:
        instance_name = agent_id if agent_id.startswith('agent-') else f"agent-{agent_id}"
        
        await self._make_request('DELETE', f"/instance/logout/{instance_name}")
        response = await self._make_request('DELETE', f"/instance/delete/{instance_name}")
        
        return response is not None

    async def send_message(self, agent_id: str, phone_number: str, text: str) -> bool:
        instance_name = agent_id if agent_id.startswith('agent-') else f"agent-{agent_id}"
        
        payload = {
            'number': phone_number,
            'options': {
                'delay': 0,
                'presence': 'composing',
                'linkPreview': False,
                'checkNumber': False
            },
            'textMessage': {
                'text': text
            }
        }
        
        response = await self._make_request('POST', f'/message/sendText/{instance_name}', payload=payload)
        return response is not None