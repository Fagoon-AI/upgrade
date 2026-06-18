"""
Twilio Integration Node.

Enterprise-grade Twilio API integration for SMS, MMS, and voice calls.
"""

import asyncio
import json
import re
import base64
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode, NodeExecutionError, ConnectionError
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class TwilioConfig:
    """Configuration for Twilio operations."""
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    max_sms_length: int = 1600  # Concatenated SMS limit
    max_mms_media: int = 10


# Twilio API base URL
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

# Rate limit codes
RATE_LIMIT_CODES = [429]

# Retryable status codes
RETRYABLE_CODES = [500, 502, 503, 504, 429]

# Phone number validation regex
PHONE_REGEX = re.compile(r'^\+?[1-9]\d{1,14}$')


# ============================================================
# TWILIO CLIENT
# ============================================================

class TwilioClient:
    """
    Robust Twilio API client with retry logic.
    """

    def __init__(
            self,
            account_sid: str,
            auth_token: str,
            config: Optional[TwilioConfig] = None
    ):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.config = config or TwilioConfig()

    def _get_auth_header(self) -> str:
        """Gets Basic auth header."""
        credentials = f"{self.account_sid}:{self.auth_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def _make_request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Dict[str, Any]] = None,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Makes API request with retry logic."""
        url = f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/{endpoint}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded"
        }

        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=headers, params=params)
                    elif method.upper() == "POST":
                        response = await client.post(url, headers=headers, data=data)
                    elif method.upper() == "DELETE":
                        response = await client.delete(url, headers=headers)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    # Handle rate limiting
                    if response.status_code in RATE_LIMIT_CODES:
                        retry_after = float(response.headers.get("Retry-After", 5))
                        logger.warning(f"Twilio rate limited. Waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    # Handle retryable errors
                    if response.status_code in RETRYABLE_CODES and attempt < self.config.max_retries:
                        logger.warning(f"Twilio API error {response.status_code}. Retrying...")
                        await asyncio.sleep(self.config.retry_delay * attempt)
                        continue

                    # Parse response
                    result = response.json()

                    if response.status_code >= 400:
                        return {
                            "success": False,
                            "error": result.get("message", f"HTTP {response.status_code}"),
                            "code": result.get("code"),
                            "more_info": result.get("more_info")
                        }

                    result["success"] = True
                    return result

            except httpx.TimeoutException:
                last_error = "Request timeout"
                logger.warning(f"Twilio request timeout (attempt {attempt})")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Twilio connection error: {e}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Twilio request error: {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"success": False, "error": last_error or "max_retries_exceeded"}

    # ============================================================
    # SMS/MMS OPERATIONS
    # ============================================================

    async def send_sms(
            self,
            to: str,
            from_: str,
            body: str,
            media_urls: Optional[List[str]] = None,
            status_callback: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sends SMS or MMS message."""
        data: Dict[str, Any] = {
            "To": to,
            "From": from_,
            "Body": body[:self.config.max_sms_length]
        }

        # Add media URLs for MMS
        if media_urls:
            for i, url in enumerate(media_urls[:self.config.max_mms_media]):
                data[f"MediaUrl{i}"] = url

        if status_callback:
            data["StatusCallback"] = status_callback

        return await self._make_request("POST", "Messages.json", data=data)

    async def get_message(self, message_sid: str) -> Dict[str, Any]:
        """Gets message details."""
        return await self._make_request("GET", f"Messages/{message_sid}.json")

    async def list_messages(
            self,
            to: Optional[str] = None,
            from_: Optional[str] = None,
            date_sent: Optional[str] = None,
            page_size: int = 50
    ) -> Dict[str, Any]:
        """Lists messages with filters."""
        params: Dict[str, Any] = {"PageSize": min(page_size, 1000)}

        if to:
            params["To"] = to
        if from_:
            params["From"] = from_
        if date_sent:
            params["DateSent"] = date_sent

        return await self._make_request("GET", "Messages.json", params=params)

    # ============================================================
    # VOICE CALL OPERATIONS
    # ============================================================

    async def make_call(
            self,
            to: str,
            from_: str,
            twiml: Optional[str] = None,
            url: Optional[str] = None,
            status_callback: Optional[str] = None,
            timeout: int = 30,
            record: bool = False
    ) -> Dict[str, Any]:
        """Initiates a voice call."""
        data: Dict[str, Any] = {
            "To": to,
            "From": from_,
            "Timeout": timeout
        }

        if twiml:
            data["Twiml"] = twiml
        elif url:
            data["Url"] = url
        else:
            # Default TwiML for simple announcement
            data["Twiml"] = "<Response><Say>This is an automated call from your workflow.</Say></Response>"

        if status_callback:
            data["StatusCallback"] = status_callback

        if record:
            data["Record"] = "true"

        return await self._make_request("POST", "Calls.json", data=data)

    async def get_call(self, call_sid: str) -> Dict[str, Any]:
        """Gets call details."""
        return await self._make_request("GET", f"Calls/{call_sid}.json")

    async def update_call(
            self,
            call_sid: str,
            status: Optional[str] = None,
            twiml: Optional[str] = None,
            url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Updates an in-progress call."""
        data: Dict[str, Any] = {}

        if status:
            data["Status"] = status  # completed, canceled

        if twiml:
            data["Twiml"] = twiml
        elif url:
            data["Url"] = url

        return await self._make_request("POST", f"Calls/{call_sid}.json", data=data)

    async def list_calls(
            self,
            to: Optional[str] = None,
            from_: Optional[str] = None,
            status: Optional[str] = None,
            page_size: int = 50
    ) -> Dict[str, Any]:
        """Lists calls with filters."""
        params: Dict[str, Any] = {"PageSize": min(page_size, 1000)}

        if to:
            params["To"] = to
        if from_:
            params["From"] = from_
        if status:
            params["Status"] = status

        return await self._make_request("GET", "Calls.json", params=params)

    # ============================================================
    # PHONE NUMBER OPERATIONS
    # ============================================================

    async def lookup_phone(self, phone_number: str, type_: str = "carrier") -> Dict[str, Any]:
        """Looks up phone number information."""
        # Lookup API uses different base URL
        url = f"https://lookups.twilio.com/v1/PhoneNumbers/{phone_number}"
        params = {"Type": type_}

        headers = {
            "Authorization": self._get_auth_header()
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(url, headers=headers, params=params)
                result = response.json()

                if response.status_code >= 400:
                    return {
                        "success": False,
                        "error": result.get("message", f"HTTP {response.status_code}")
                    }

                result["success"] = True
                return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_incoming_numbers(self, page_size: int = 50) -> Dict[str, Any]:
        """Lists available phone numbers."""
        params = {"PageSize": min(page_size, 1000)}
        return await self._make_request("GET", "IncomingPhoneNumbers.json", params=params)


# ============================================================
# TWIML BUILDER
# ============================================================

class TwiMLBuilder:
    """
    Builds TwiML documents for voice calls.
    """

    def __init__(self):
        self._elements: List[str] = []

    def say(
            self,
            text: str,
            voice: str = "alice",
            language: str = "en-US",
            loop: int = 1
    ) -> "TwiMLBuilder":
        """Adds a Say verb."""
        self._elements.append(
            f'<Say voice="{voice}" language="{language}" loop="{loop}">{self._escape(text)}</Say>'
        )
        return self

    def play(self, url: str, loop: int = 1) -> "TwiMLBuilder":
        """Adds a Play verb."""
        self._elements.append(f'<Play loop="{loop}">{self._escape(url)}</Play>')
        return self

    def pause(self, length: int = 1) -> "TwiMLBuilder":
        """Adds a Pause verb."""
        self._elements.append(f'<Pause length="{length}"/>')
        return self

    def gather(
            self,
            action_url: str,
            num_digits: int = 1,
            timeout: int = 5,
            input_type: str = "dtmf",
            speech_timeout: str = "auto"
    ) -> "TwiMLBuilder":
        """Adds a Gather verb for input collection."""
        self._elements.append(
            f'<Gather action="{self._escape(action_url)}" numDigits="{num_digits}" '
            f'timeout="{timeout}" input="{input_type}" speechTimeout="{speech_timeout}"/>'
        )
        return self

    def dial(
            self,
            number: str,
            caller_id: Optional[str] = None,
            timeout: int = 30
    ) -> "TwiMLBuilder":
        """Adds a Dial verb."""
        attrs = f'timeout="{timeout}"'
        if caller_id:
            attrs += f' callerId="{caller_id}"'
        self._elements.append(f'<Dial {attrs}>{self._escape(number)}</Dial>')
        return self

    def record(
            self,
            action_url: Optional[str] = None,
            max_length: int = 60,
            play_beep: bool = True
    ) -> "TwiMLBuilder":
        """Adds a Record verb."""
        attrs = f'maxLength="{max_length}" playBeep="{str(play_beep).lower()}"'
        if action_url:
            attrs += f' action="{self._escape(action_url)}"'
        self._elements.append(f'<Record {attrs}/>')
        return self

    def hangup(self) -> "TwiMLBuilder":
        """Adds a Hangup verb."""
        self._elements.append('<Hangup/>')
        return self

    def redirect(self, url: str) -> "TwiMLBuilder":
        """Adds a Redirect verb."""
        self._elements.append(f'<Redirect>{self._escape(url)}</Redirect>')
        return self

    def build(self) -> str:
        """Builds the TwiML document."""
        content = "".join(self._elements)
        return f'<?xml version="1.0" encoding="UTF-8"?><Response>{content}</Response>'

    def _escape(self, text: str) -> str:
        """Escapes XML special characters."""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))

    @classmethod
    def simple_message(cls, text: str, voice: str = "alice") -> str:
        """Creates a simple TwiML message."""
        return cls().say(text, voice=voice).build()

    @classmethod
    def voicemail(
            cls,
            greeting: str,
            recording_url: str,
            max_length: int = 120
    ) -> str:
        """Creates a voicemail TwiML."""
        return (cls()
                .say(greeting)
                .pause(1)
                .say("Please leave your message after the beep.")
                .record(action_url=recording_url, max_length=max_length)
                .say("Thank you for your message.")
                .hangup()
                .build())


# ============================================================
# TWILIO NODE
# ============================================================

class TwilioNode(BaseNode):
    """
    Enterprise-Grade Twilio Integration Node.

    Features:
    - SMS and MMS messaging
    - Voice calls with TwiML
    - Phone number lookup
    - Retry with exponential backoff
    - Rate limit handling
    - Phone number validation

    Operations:
    - send_sms: Send SMS/MMS message
    - make_call: Initiate voice call
    - get_message: Get message status
    - get_call: Get call status
    - lookup_phone: Lookup phone number info
    - list_messages: List sent messages
    """

    node_type = "twilioNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Twilio",
            "icon": "Phone",
            "category": "Communication",
            "description": "Full Twilio integration for SMS, MMS, and voice calls.",
            "fields": [
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": [
                        "send_sms",
                        "make_call",
                        "get_message",
                        "get_call",
                        "lookup_phone",
                        "list_messages"
                    ],
                    "default": "send_sms"
                },
                {
                    "name": "connection_id",
                    "label": "Twilio Connection",
                    "type": "connection_select",
                    "provider": "TWILIO",
                    "required": True
                },
                {
                    "name": "to",
                    "label": "To Phone Number",
                    "type": "text",
                    "placeholder": "+1234567890",
                    "conditional": {"operation": ["send_sms", "make_call", "lookup_phone"]},
                    "helper": "E.164 format (+country code)"
                },
                {
                    "name": "from",
                    "label": "From Phone Number",
                    "type": "text",
                    "placeholder": "+1234567890",
                    "conditional": {"operation": ["send_sms", "make_call"]},
                    "helper": "Your Twilio phone number"
                },
                {
                    "name": "message",
                    "label": "Message",
                    "type": "textarea",
                    "conditional": {"operation": "send_sms"},
                    "helper": "SMS message body (max 1600 chars)"
                },
                {
                    "name": "media_urls",
                    "label": "Media URLs (MMS)",
                    "type": "text",
                    "conditional": {"operation": "send_sms"},
                    "helper": "Comma-separated media URLs for MMS"
                },
                {
                    "name": "call_type",
                    "label": "Call Type",
                    "type": "select",
                    "options": ["text_to_speech", "twiml", "url"],
                    "default": "text_to_speech",
                    "conditional": {"operation": "make_call"}
                },
                {
                    "name": "call_message",
                    "label": "Call Message",
                    "type": "textarea",
                    "conditional": {"call_type": "text_to_speech"},
                    "helper": "Text to be spoken"
                },
                {
                    "name": "twiml",
                    "label": "TwiML",
                    "type": "code",
                    "language": "xml",
                    "conditional": {"call_type": "twiml"},
                    "helper": "Custom TwiML document"
                },
                {
                    "name": "webhook_url",
                    "label": "Webhook URL",
                    "type": "text",
                    "conditional": {"call_type": "url"},
                    "helper": "URL returning TwiML"
                },
                {
                    "name": "voice",
                    "label": "Voice",
                    "type": "select",
                    "options": ["alice", "man", "woman", "Polly.Joanna", "Polly.Matthew", "Polly.Amy"],
                    "default": "alice",
                    "conditional": {"call_type": "text_to_speech"}
                },
                {
                    "name": "language",
                    "label": "Language",
                    "type": "select",
                    "options": ["en-US", "en-GB", "es-ES", "fr-FR", "de-DE", "it-IT", "ja-JP", "ko-KR", "pt-BR", "zh-CN"],
                    "default": "en-US",
                    "conditional": {"call_type": "text_to_speech"}
                },
                {
                    "name": "record_call",
                    "label": "Record Call",
                    "type": "boolean",
                    "default": False,
                    "conditional": {"operation": "make_call"}
                },
                {
                    "name": "call_timeout",
                    "label": "Call Timeout (seconds)",
                    "type": "number",
                    "default": 30,
                    "conditional": {"operation": "make_call"}
                },
                {
                    "name": "message_sid",
                    "label": "Message SID",
                    "type": "text",
                    "conditional": {"operation": "get_message"},
                    "helper": "Message identifier"
                },
                {
                    "name": "call_sid",
                    "label": "Call SID",
                    "type": "text",
                    "conditional": {"operation": "get_call"},
                    "helper": "Call identifier"
                },
                {
                    "name": "lookup_type",
                    "label": "Lookup Type",
                    "type": "select",
                    "options": ["carrier", "caller-name"],
                    "default": "carrier",
                    "conditional": {"operation": "lookup_phone"}
                },
                {
                    "name": "status_callback",
                    "label": "Status Callback URL",
                    "type": "text",
                    "helper": "URL for status updates (optional)"
                }
            ],
            "outputs": ["status", "sid", "price", "price_unit", "direction", "messages", "call_status"]
        }

    def __init__(self):
        super().__init__()
        self.config = TwilioConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes Twilio operation."""
        operation = input_data.get("operation", "send_sms")

        # Get client
        client = await self._get_client(db, input_data)

        # Execute operation
        if operation == "send_sms":
            return await self._send_sms(client, input_data)
        elif operation == "make_call":
            return await self._make_call(client, input_data)
        elif operation == "get_message":
            return await self._get_message(client, input_data)
        elif operation == "get_call":
            return await self._get_call(client, input_data)
        elif operation == "lookup_phone":
            return await self._lookup_phone(client, input_data)
        elif operation == "list_messages":
            return await self._list_messages(client, input_data)
        else:
            raise NodeExecutionError(
                message=f"Unknown operation: {operation}",
                node_type=self.node_type,
                retryable=False
            )

    async def _get_client(
            self,
            db: AsyncSession,
            input_data: Dict[str, Any]
    ) -> TwilioClient:
        """Gets authenticated Twilio client."""
        connection_id = input_data.get("connection_id")

        if not connection_id:
            raise NodeExecutionError(
                message="Connection ID is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await db.execute(
            select(Connection).where(Connection.id == connection_id)
        )
        conn = result.scalars().first()

        if not conn:
            raise ConnectionError(
                message=f"Connection {connection_id} not found",
                node_type=self.node_type,
                provider="twilio"
            )

        try:
            creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
            account_sid = creds.get("account_sid")
            auth_token = creds.get("auth_token")
        except Exception as e:
            raise ConnectionError(
                message="Failed to decrypt credentials",
                node_type=self.node_type,
                provider="twilio"
            )

        if not account_sid or not auth_token:
            raise ConnectionError(
                message="Connection missing Twilio credentials",
                node_type=self.node_type,
                provider="twilio"
            )

        return TwilioClient(account_sid, auth_token, self.config)

    def _validate_phone(self, phone: str) -> str:
        """Validates and normalizes phone number."""
        phone = phone.strip()

        # Add + if not present
        if not phone.startswith("+"):
            phone = f"+{phone}"

        if not PHONE_REGEX.match(phone):
            raise NodeExecutionError(
                message=f"Invalid phone number format: {phone}. Use E.164 format (+1234567890)",
                node_type=self.node_type,
                retryable=False
            )

        return phone

    async def _send_sms(
            self,
            client: TwilioClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Sends SMS or MMS message."""
        to = self._validate_phone(input_data.get("to", ""))
        from_ = self._validate_phone(input_data.get("from", ""))
        body = input_data.get("message", "").strip()
        status_callback = input_data.get("status_callback")

        if not body:
            raise NodeExecutionError(
                message="Message body is required",
                node_type=self.node_type,
                retryable=False
            )

        # Parse media URLs
        media_urls = None
        media_str = input_data.get("media_urls", "").strip()
        if media_str:
            media_urls = [url.strip() for url in media_str.split(",") if url.strip()]

        result = await client.send_sms(
            to=to,
            from_=from_,
            body=body,
            media_urls=media_urls,
            status_callback=status_callback
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "SMS send failed"),
                "code": result.get("code")
            }

        return {
            "status": "success",
            "sid": result.get("sid"),
            "to": result.get("to"),
            "from": result.get("from"),
            "body": result.get("body"),
            "num_segments": result.get("num_segments"),
            "price": result.get("price"),
            "price_unit": result.get("price_unit"),
            "direction": result.get("direction"),
            "message_status": result.get("status")
        }

    async def _make_call(
            self,
            client: TwilioClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Makes a voice call."""
        to = self._validate_phone(input_data.get("to", ""))
        from_ = self._validate_phone(input_data.get("from", ""))
        call_type = input_data.get("call_type", "text_to_speech")
        status_callback = input_data.get("status_callback")
        timeout = int(input_data.get("call_timeout", 30))
        record = bool(input_data.get("record_call", False))

        # Build TwiML based on call type
        twiml = None
        url = None

        if call_type == "text_to_speech":
            message = input_data.get("call_message", "").strip()
            if not message:
                raise NodeExecutionError(
                    message="Call message is required for text-to-speech",
                    node_type=self.node_type,
                    retryable=False
                )

            voice = input_data.get("voice", "alice")
            language = input_data.get("language", "en-US")

            twiml = TwiMLBuilder().say(message, voice=voice, language=language).build()

        elif call_type == "twiml":
            twiml = input_data.get("twiml", "").strip()
            if not twiml:
                raise NodeExecutionError(
                    message="TwiML is required",
                    node_type=self.node_type,
                    retryable=False
                )

        elif call_type == "url":
            url = input_data.get("webhook_url", "").strip()
            if not url:
                raise NodeExecutionError(
                    message="Webhook URL is required",
                    node_type=self.node_type,
                    retryable=False
                )

        result = await client.make_call(
            to=to,
            from_=from_,
            twiml=twiml,
            url=url,
            status_callback=status_callback,
            timeout=timeout,
            record=record
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Call failed"),
                "code": result.get("code")
            }

        return {
            "status": "success",
            "sid": result.get("sid"),
            "to": result.get("to"),
            "from": result.get("from"),
            "call_status": result.get("status"),
            "direction": result.get("direction"),
            "price": result.get("price"),
            "price_unit": result.get("price_unit"),
            "duration": result.get("duration")
        }

    async def _get_message(
            self,
            client: TwilioClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Gets message details."""
        message_sid = input_data.get("message_sid", "").strip()

        if not message_sid:
            raise NodeExecutionError(
                message="Message SID is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.get_message(message_sid)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to get message")
            }

        return {
            "status": "success",
            "sid": result.get("sid"),
            "to": result.get("to"),
            "from": result.get("from"),
            "body": result.get("body"),
            "message_status": result.get("status"),
            "error_code": result.get("error_code"),
            "error_message": result.get("error_message"),
            "price": result.get("price"),
            "price_unit": result.get("price_unit"),
            "date_sent": result.get("date_sent")
        }

    async def _get_call(
            self,
            client: TwilioClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Gets call details."""
        call_sid = input_data.get("call_sid", "").strip()

        if not call_sid:
            raise NodeExecutionError(
                message="Call SID is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.get_call(call_sid)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to get call")
            }

        return {
            "status": "success",
            "sid": result.get("sid"),
            "to": result.get("to"),
            "from": result.get("from"),
            "call_status": result.get("status"),
            "duration": result.get("duration"),
            "price": result.get("price"),
            "price_unit": result.get("price_unit"),
            "answered_by": result.get("answered_by"),
            "start_time": result.get("start_time"),
            "end_time": result.get("end_time")
        }

    async def _lookup_phone(
            self,
            client: TwilioClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Looks up phone number information."""
        phone = self._validate_phone(input_data.get("to", ""))
        lookup_type = input_data.get("lookup_type", "carrier")

        result = await client.lookup_phone(phone, type_=lookup_type)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Lookup failed")
            }

        return {
            "status": "success",
            "phone_number": result.get("phone_number"),
            "national_format": result.get("national_format"),
            "country_code": result.get("country_code"),
            "carrier": result.get("carrier", {}),
            "caller_name": result.get("caller_name", {})
        }

    async def _list_messages(
            self,
            client: TwilioClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Lists sent messages."""
        to = input_data.get("to")
        from_ = input_data.get("from")

        # Validate if provided
        if to:
            to = self._validate_phone(to)
        if from_:
            from_ = self._validate_phone(from_)

        result = await client.list_messages(to=to, from_=from_)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to list messages")
            }

        messages = []
        for msg in result.get("messages", []):
            messages.append({
                "sid": msg.get("sid"),
                "to": msg.get("to"),
                "from": msg.get("from"),
                "body": msg.get("body"),
                "status": msg.get("status"),
                "date_sent": msg.get("date_sent"),
                "price": msg.get("price")
            })

        return {
            "status": "success",
            "messages": messages,
            "count": len(messages)
        }
