from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# ==========================================
# FRONTEND REQUEST/RESPONSE SCHEMAS
# ==========================================

class StartWhatsAppSessionRequest(BaseModel):
    agent_id: str = Field(..., description="The UUID of the agent to deploy")

class WhatsAppSessionStatusResponse(BaseModel):
    state: str = Field(..., description="idle, initializing, qr_ready, connecting, connected, disconnected")
    phone_number: Optional[str] = Field(None, description="The connected WhatsApp phone number")
    session_id: Optional[str] = Field(None, description="The internal Evolution API instance name")

# ==========================================
# EVOLUTION API WEBHOOK INCOMING SCHEMAS
# ==========================================

class WebhookDataInstance(BaseModel):
    instanceName: str
    state: Optional[str] = None
    phoneNumber: Optional[str] = None

class WebhookDataMessageKey(BaseModel):
    remoteJid: str
    fromMe: bool
    id: str

class WebhookDataMessageContent(BaseModel):
    conversation: Optional[str] = None

class WebhookDataMessageDetail(BaseModel):
    key: WebhookDataMessageKey
    message: Optional[WebhookDataMessageContent] = None
    messageType: Optional[str] = None

class WebhookDataQRCode(BaseModel):
    qrcode: Optional[str] = None
    base64: Optional[str] = None

class EvolutionWebhookPayload(BaseModel):
    event: str = Field(..., description="e.g., qrcode.updated, connection.update, messages.upsert")
    instance: Optional[str] = None
    data: Dict[str, Any] = Field(..., description="Raw inner data block that changes depending on the event")