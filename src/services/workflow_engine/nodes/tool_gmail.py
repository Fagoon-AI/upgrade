import asyncio
import base64
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

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
class GmailConfig:
    """Configuration for Gmail operations."""
    max_retries: int = 3
    retry_delay: float = 1.0
    max_attachment_size: int = 25 * 1024 * 1024  # 25MB Gmail limit
    max_recipients: int = 100
    max_body_length: int = 1_000_000


# Email regex pattern
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


# ============================================================
# EMAIL VALIDATOR
# ============================================================

class EmailValidator:
    """Validates email addresses and content."""

    @staticmethod
    def validate_email(email: str) -> Tuple[bool, Optional[str]]:
        """Validates a single email address."""
        if not email:
            return False, "Email is required"

        email = email.strip()

        if len(email) > 254:
            return False, "Email address too long"

        if not EMAIL_PATTERN.match(email):
            return False, f"Invalid email format: {email}"

        return True, None

    @staticmethod
    def validate_recipients(recipients: str) -> Tuple[List[str], Optional[str]]:
        """
        Validates and parses recipient list.

        Accepts comma or semicolon separated emails.
        """
        if not recipients:
            return [], "At least one recipient is required"

        # Split by comma or semicolon
        emails = re.split(r'[,;]\s*', recipients.strip())
        validated = []

        for email in emails:
            email = email.strip()
            if not email:
                continue

            # Handle "Name <email>" format
            match = re.search(r'<([^>]+)>', email)
            if match:
                email = match.group(1)

            is_valid, error = EmailValidator.validate_email(email)
            if not is_valid:
                return [], error

            validated.append(email)

        if not validated:
            return [], "No valid recipients found"

        if len(validated) > GmailConfig().max_recipients:
            return [], f"Too many recipients (max: {GmailConfig().max_recipients})"

        return validated, None


# ============================================================
# GMAIL CLIENT
# ============================================================

class GmailClient:
    """
    Robust Gmail API client with token refresh.
    """

    def __init__(self, credentials_data: Dict[str, Any], config: Optional[GmailConfig] = None):
        self.creds_data = credentials_data
        self.config = config or GmailConfig()
        self._service = None
        self._credentials = None

    async def _get_service(self):
        """Gets Gmail service with fresh credentials."""
        if self._service:
            return self._service

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from google.auth.transport.requests import Request
        except ImportError:
            raise NodeExecutionError(
                message="Google API libraries not installed",
                node_type="gmailNode",
                retryable=False
            )

        # Build credentials
        self._credentials = Credentials(
            token=self.creds_data.get("token"),
            refresh_token=self.creds_data.get("refresh_token"),
            token_uri=self.creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=self.creds_data.get("client_id"),
            client_secret=self.creds_data.get("client_secret"),
            scopes=self.creds_data.get("scopes", ["https://mail.google.com/"])
        )

        # Refresh if expired
        if self._credentials.expired and self._credentials.refresh_token:
            try:
                request = Request()
                await asyncio.to_thread(self._credentials.refresh, request)
                logger.info("Gmail token refreshed successfully")
            except Exception as e:
                raise ConnectionError(
                    message=f"Token refresh failed: {e}",
                    node_type="gmailNode",
                    provider="google"
                )

        # Build service
        self._service = build(
            'gmail', 'v1',
            credentials=self._credentials,
            cache_discovery=False
        )

        return self._service

    async def send_email(
            self,
            to: List[str],
            subject: str,
            body: str,
            html_body: Optional[str] = None,
            cc: Optional[List[str]] = None,
            bcc: Optional[List[str]] = None,
            reply_to: Optional[str] = None,
            attachments: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Sends an email with retry logic."""
        service = await self._get_service()

        # Create message
        if html_body or attachments:
            message = self._create_multipart_message(
                to, subject, body, html_body, cc, bcc, reply_to, attachments
            )
        else:
            message = self._create_simple_message(
                to, subject, body, cc, bcc, reply_to
            )

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        # Send with retry
        last_error = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = await asyncio.to_thread(
                    service.users().messages().send(
                        userId="me",
                        body={'raw': raw_message}
                    ).execute
                )

                return {
                    "success": True,
                    "message_id": result.get('id'),
                    "thread_id": result.get('threadId'),
                    "labels": result.get('labelIds', [])
                }

            except Exception as e:
                error_str = str(e).lower()
                last_error = str(e)

                # Check for rate limit
                if "rate limit" in error_str or "quota" in error_str:
                    logger.warning(f"Gmail rate limited (attempt {attempt})")
                    await asyncio.sleep(self.config.retry_delay * attempt * 2)
                    continue

                # Check for auth errors (non-retryable)
                if "invalid_grant" in error_str or "unauthorized" in error_str:
                    return {"success": False, "error": last_error, "auth_error": True}

                logger.warning(f"Gmail send error (attempt {attempt}): {e}")

                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay * attempt)

        return {"success": False, "error": last_error or "Max retries exceeded"}

    def _create_simple_message(
            self,
            to: List[str],
            subject: str,
            body: str,
            cc: Optional[List[str]] = None,
            bcc: Optional[List[str]] = None,
            reply_to: Optional[str] = None
    ) -> MIMEText:
        """Creates a simple text email."""
        message = MIMEText(body, 'plain', 'utf-8')
        message['to'] = ', '.join(to)
        message['subject'] = subject

        if cc:
            message['cc'] = ', '.join(cc)
        if bcc:
            message['bcc'] = ', '.join(bcc)
        if reply_to:
            message['reply-to'] = reply_to

        return message

    def _create_multipart_message(
            self,
            to: List[str],
            subject: str,
            body: str,
            html_body: Optional[str] = None,
            cc: Optional[List[str]] = None,
            bcc: Optional[List[str]] = None,
            reply_to: Optional[str] = None,
            attachments: Optional[List[Dict]] = None
    ) -> MIMEMultipart:
        """Creates a multipart email with HTML and/or attachments."""
        if attachments:
            message = MIMEMultipart('mixed')
            body_part = MIMEMultipart('alternative')
        else:
            message = MIMEMultipart('alternative')
            body_part = message

        # Add plain text
        body_part.attach(MIMEText(body, 'plain', 'utf-8'))

        # Add HTML if provided
        if html_body:
            body_part.attach(MIMEText(html_body, 'html', 'utf-8'))

        # If we have attachments, add body part and attachments
        if attachments:
            message.attach(body_part)

            for att in attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(att.get('content', b''))
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{att.get("filename", "attachment")}"'
                )
                message.attach(part)

        message['to'] = ', '.join(to)
        message['subject'] = subject

        if cc:
            message['cc'] = ', '.join(cc)
        if bcc:
            message['bcc'] = ', '.join(bcc)
        if reply_to:
            message['reply-to'] = reply_to

        return message

    async def read_emails(
            self,
            max_results: int = 10,
            query: Optional[str] = None,
            label_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Reads emails from inbox."""
        service = await self._get_service()

        try:
            # List messages
            params = {'userId': 'me', 'maxResults': max_results}
            if query:
                params['q'] = query
            if label_ids:
                params['labelIds'] = label_ids

            result = await asyncio.to_thread(
                service.users().messages().list(**params).execute
            )

            messages = []
            for msg in result.get('messages', []):
                # Get full message
                full_msg = await asyncio.to_thread(
                    service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='metadata',
                        metadataHeaders=['From', 'To', 'Subject', 'Date']
                    ).execute
                )

                headers = {h['name']: h['value'] for h in full_msg.get('payload', {}).get('headers', [])}

                messages.append({
                    'id': msg['id'],
                    'thread_id': full_msg.get('threadId'),
                    'from': headers.get('From'),
                    'to': headers.get('To'),
                    'subject': headers.get('Subject'),
                    'date': headers.get('Date'),
                    'snippet': full_msg.get('snippet'),
                    'labels': full_msg.get('labelIds', [])
                })

            return {
                'success': True,
                'messages': messages,
                'count': len(messages),
                'next_page_token': result.get('nextPageToken')
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def get_labels(self) -> Dict[str, Any]:
        """Gets all labels."""
        service = await self._get_service()

        try:
            result = await asyncio.to_thread(
                service.users().labels().list(userId='me').execute
            )

            return {
                'success': True,
                'labels': result.get('labels', [])
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


# ============================================================
# GMAIL NODE
# ============================================================

class GmailNode(BaseNode):
    """
    Gmail Integration Node.

    Features:
    - OAuth2 authentication with token refresh
    - HTML email support
    - Multiple recipients (to, cc, bcc)
    - File attachments
    - Email reading operations
    - Query-based search

    Operations:
    - send_email: Send text or HTML emails
    - read_emails: Read inbox messages
    - get_labels: List available labels
    """

    node_type = "gmailNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Gmail",
            "icon": "Mail",
            "category": "Communication",
            "description": "Gmail with HTML support and attachments.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "Gmail Connection",
                    "type": "connection_select",
                    "provider": "GMAIL_OAUTH",
                    "required": True
                },
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": ["send_email", "read_emails", "get_labels"],
                    "default": "send_email"
                },
                {
                    "name": "to_email",
                    "label": "To",
                    "type": "text",
                    "placeholder": "email@example.com, another@example.com",
                    "conditional": {"operation": "send_email"},
                    "helper": "Comma-separated for multiple recipients"
                },
                {
                    "name": "cc",
                    "label": "CC",
                    "type": "text",
                    "conditional": {"operation": "send_email"}
                },
                {
                    "name": "bcc",
                    "label": "BCC",
                    "type": "text",
                    "conditional": {"operation": "send_email"}
                },
                {
                    "name": "subject",
                    "label": "Subject",
                    "type": "text",
                    "conditional": {"operation": "send_email"}
                },
                {
                    "name": "body",
                    "label": "Body",
                    "type": "textarea",
                    "conditional": {"operation": "send_email"}
                },
                {
                    "name": "html_body",
                    "label": "HTML Body",
                    "type": "textarea",
                    "conditional": {"operation": "send_email"},
                    "helper": "Optional: HTML version of email"
                },
                {
                    "name": "reply_to",
                    "label": "Reply-To",
                    "type": "text",
                    "conditional": {"operation": "send_email"}
                },
                {
                    "name": "query",
                    "label": "Search Query",
                    "type": "text",
                    "placeholder": "from:someone@example.com is:unread",
                    "conditional": {"operation": "read_emails"},
                    "helper": "Gmail search syntax"
                },
                {
                    "name": "max_results",
                    "label": "Max Results",
                    "type": "number",
                    "default": 10,
                    "conditional": {"operation": "read_emails"}
                }
            ],
            "outputs": ["status", "message_id", "thread_id", "messages", "count", "labels", "sent_to"],
            "outputs_schema": {
                "status": {"type": "string", "description": "Execution status ('success', 'error', or 'requires_auth')"},
                "message_id": {"type": "string", "description": "ID of sent message (send_email)"},
                "thread_id": {"type": "string", "description": "Thread ID of sent message (send_email)"},
                "sent_to": {"type": "array", "description": "List of recipients (send_email)"},
                "messages": {"type": "array", "description": "List of retrieved messages (read_emails)"},
                "count": {"type": "number", "description": "Number of messages/labels returned"},
                "labels": {"type": "array", "description": "List of Gmail labels (get_labels)"}
            }
        }

    def __init__(self):
        super().__init__()
        self.config = GmailConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes Gmail operation."""
        connection_id = input_data.get("connection_id")
        operation = input_data.get("operation", "send_email")

        if not connection_id:
            raise NodeExecutionError(
                message="Connection ID is required",
                node_type=self.node_type,
                retryable=False
            )

        # Get credentials
        creds_data = await self._get_credentials(db, connection_id)
        client = GmailClient(creds_data, self.config)

        if operation == "send_email":
            return await self._send_email(client, input_data)
        elif operation == "read_emails":
            return await self._read_emails(client, input_data)
        elif operation == "get_labels":
            return await self._get_labels(client)
        else:
            raise NodeExecutionError(
                message=f"Unknown operation: {operation}",
                node_type=self.node_type,
                retryable=False
            )

    async def _get_credentials(self, db: AsyncSession, connection_id: str) -> Dict[str, Any]:
        """Gets credentials from connection."""
        result = await db.execute(
            select(Connection).where(Connection.id == connection_id)
        )
        connection = result.scalars().first()

        if not connection:
            raise ConnectionError(
                message=f"Connection {connection_id} not found",
                node_type=self.node_type,
                provider="google"
            )

        # Validate provider
        if connection.provider not in ["GMAIL_OAUTH", "GOOGLE"]:
            raise ConnectionError(
                message=f"Invalid connection type: {connection.provider}",
                node_type=self.node_type,
                provider="google"
            )

        try:
            return json.loads(crypto.decrypt(connection.encrypted_credentials))
        except Exception as e:
            raise ConnectionError(
                message="Failed to decrypt credentials",
                node_type=self.node_type,
                provider="google"
            )

    async def _send_email(
            self,
            client: GmailClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Sends an email."""
        # Validate recipients
        to_str = input_data.get("to_email", "")
        to_list, error = EmailValidator.validate_recipients(to_str)
        if error:
            raise NodeExecutionError(
                message=error,
                node_type=self.node_type,
                retryable=False
            )

        # Parse CC and BCC
        cc_list = []
        bcc_list = []

        if input_data.get("cc"):
            cc_list, error = EmailValidator.validate_recipients(input_data["cc"])
            if error:
                raise NodeExecutionError(message=f"CC: {error}", node_type=self.node_type, retryable=False)

        if input_data.get("bcc"):
            bcc_list, error = EmailValidator.validate_recipients(input_data["bcc"])
            if error:
                raise NodeExecutionError(message=f"BCC: {error}", node_type=self.node_type, retryable=False)

        subject = input_data.get("subject", "No Subject")
        body = input_data.get("body", "")
        html_body = input_data.get("html_body")
        reply_to = input_data.get("reply_to")

        # Validate body length
        if len(body) > self.config.max_body_length:
            raise NodeExecutionError(
                message=f"Email body too long (max: {self.config.max_body_length} chars)",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.send_email(
            to=to_list,
            subject=subject,
            body=body,
            html_body=html_body,
            cc=cc_list or None,
            bcc=bcc_list or None,
            reply_to=reply_to
        )

        if not result.get("success"):
            if result.get("auth_error"):
                return {
                    "status": "requires_auth",
                    "error": result.get("error"),
                    "selected_branch": "paused"
                }
            return {
                "status": "error",
                "error": result.get("error", "Failed to send email")
            }

        return {
            "status": "success",
            "message_id": result.get("message_id"),
            "thread_id": result.get("thread_id"),
            "sent_to": to_list,
            "cc": cc_list,
            "bcc": bcc_list
        }

    async def _read_emails(
            self,
            client: GmailClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reads emails."""
        query = input_data.get("query")
        max_results = min(int(input_data.get("max_results", 10)), 100)

        result = await client.read_emails(
            max_results=max_results,
            query=query
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to read emails")
            }

        return {
            "status": "success",
            "messages": result.get("messages", []),
            "count": result.get("count", 0),
            "has_more": result.get("next_page_token") is not None
        }

    async def _get_labels(self, client: GmailClient) -> Dict[str, Any]:
        """Gets available labels."""
        result = await client.get_labels()

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Failed to get labels")
            }

        return {
            "status": "success",
            "labels": result.get("labels", []),
            "count": len(result.get("labels", []))
        }