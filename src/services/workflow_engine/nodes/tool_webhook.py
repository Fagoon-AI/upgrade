import asyncio
import base64
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
import ipaddress

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class WebhookConfig:
    """Configuration for webhook operations."""
    default_timeout: float = 30.0
    max_timeout: float = 120.0
    max_retries: int = 3
    retry_delay: float = 1.0
    max_response_size: int = 10 * 1024 * 1024  # 10MB
    max_payload_size: int = 5 * 1024 * 1024  # 5MB


# HTTP methods
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# Retryable status codes
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Content types
CONTENT_TYPES = {
    "json": "application/json",
    "form": "application/x-www-form-urlencoded",
    "text": "text/plain",
    "xml": "application/xml"
}


# ============================================================
# URL VALIDATOR
# ============================================================

class WebhookURLValidator:
    """
    Validates webhook URLs for security.

    Blocks:
    - Private/internal IPs
    - Localhost
    - File URLs
    - Non-HTTP(S) protocols
    """

    # Private IP ranges
    PRIVATE_NETWORKS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    # Blocked hostnames
    BLOCKED_HOSTS = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
        "169.254.169.254",  # Cloud metadata
    }

    @classmethod
    def validate(cls, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validates a webhook URL.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url:
            return False, "URL is required"

        url = url.strip()

        try:
            parsed = urlparse(url)
        except Exception:
            return False, "Invalid URL format"

        # Must have scheme
        if parsed.scheme not in ["http", "https"]:
            return False, "URL must use HTTP or HTTPS"

        # Must have host
        if not parsed.netloc:
            return False, "URL must have a host"

        # Extract hostname (without port)
        hostname = parsed.hostname or ""

        # Check blocked hostnames
        if hostname.lower() in cls.BLOCKED_HOSTS:
            return False, f"Blocked host: {hostname}"

        # Check if IP address
        try:
            ip = ipaddress.ip_address(hostname)
            for network in cls.PRIVATE_NETWORKS:
                if ip in network:
                    return False, f"Private/internal IP addresses are not allowed: {hostname}"
        except ValueError:
            # Not an IP address, that's fine
            pass

        return True, None

    @classmethod
    def normalize(cls, url: str) -> str:
        """Normalizes a URL."""
        return url.strip()


# ============================================================
# HEADER SANITIZER
# ============================================================

class HeaderSanitizer:
    """Sanitizes HTTP headers for security."""

    # Forbidden headers that could cause issues
    FORBIDDEN_HEADERS = {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "upgrade"
    }

    @classmethod
    def sanitize(cls, headers: Dict[str, str]) -> Dict[str, str]:
        """Removes forbidden headers and normalizes values."""
        if not headers:
            return {}

        sanitized = {}
        for key, value in headers.items():
            # Skip forbidden headers
            if key.lower() in cls.FORBIDDEN_HEADERS:
                logger.warning(f"Removed forbidden header: {key}")
                continue

            # Ensure string values
            sanitized[key] = str(value) if value is not None else ""

        return sanitized


# ============================================================
# WEBHOOK CLIENT
# ============================================================

class WebhookClient:
    """
    Robust HTTP client for webhook requests.
    """

    def __init__(self, config: Optional[WebhookConfig] = None):
        self.config = config or WebhookConfig()

    async def request(
            self,
            url: str,
            method: str = "POST",
            payload: Optional[Any] = None,
            headers: Optional[Dict[str, str]] = None,
            auth_type: Optional[str] = None,
            auth_value: Optional[str] = None,
            content_type: str = "json",
            timeout: Optional[float] = None,
            follow_redirects: bool = True
    ) -> Dict[str, Any]:
        """
        Makes HTTP request with retry logic.

        Args:
            url: Target URL
            method: HTTP method
            payload: Request body
            headers: Custom headers
            auth_type: Authentication type (bearer, basic, api_key)
            auth_value: Authentication value
            content_type: Content type (json, form, text, xml)
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow redirects
        """
        # Validate URL
        is_valid, error = WebhookURLValidator.validate(url)
        if not is_valid:
            return {"success": False, "error": error}

        url = WebhookURLValidator.normalize(url)

        # Validate method
        method = method.upper()
        if method not in ALLOWED_METHODS:
            return {"success": False, "error": f"Invalid HTTP method: {method}"}

        # Build headers
        request_headers = HeaderSanitizer.sanitize(headers or {})

        # Add content type
        if content_type in CONTENT_TYPES and method in ["POST", "PUT", "PATCH"]:
            request_headers.setdefault("Content-Type", CONTENT_TYPES[content_type])

        # Add authentication
        if auth_type and auth_value:
            auth_header = self._build_auth_header(auth_type, auth_value)
            if auth_header:
                request_headers["Authorization"] = auth_header

        # Determine timeout
        request_timeout = min(
            timeout or self.config.default_timeout,
            self.config.max_timeout
        )

        # Prepare request body
        request_body = self._prepare_body(payload, content_type)

        # Check payload size
        if request_body:
            body_size = len(json.dumps(request_body).encode() if isinstance(request_body, dict) else str(request_body).encode())
            if body_size > self.config.max_payload_size:
                return {
                    "success": False,
                    "error": f"Payload too large: {body_size} bytes (max: {self.config.max_payload_size})"
                }

        # Execute with retry
        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                        timeout=request_timeout,
                        follow_redirects=follow_redirects
                ) as client:
                    # Prepare request kwargs
                    kwargs = {
                        "method": method,
                        "url": url,
                        "headers": request_headers
                    }

                    # Add body based on content type
                    if request_body is not None and method in ["POST", "PUT", "PATCH"]:
                        if content_type == "json":
                            kwargs["json"] = request_body
                        elif content_type == "form":
                            kwargs["data"] = request_body
                        else:
                            kwargs["content"] = str(request_body)

                    # Make request
                    response = await client.request(**kwargs)

                    # Handle rate limiting
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"Rate limited. Waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    # Handle retryable errors
                    if response.status_code in RETRYABLE_STATUS_CODES:
                        if attempt < self.config.max_retries:
                            logger.warning(f"Retryable error {response.status_code}. Attempt {attempt}")
                            await asyncio.sleep(self.config.retry_delay * attempt)
                            continue

                    # Parse response
                    return self._parse_response(response)

            except httpx.TimeoutException:
                last_error = f"Request timed out after {request_timeout}s"
                logger.warning(f"Webhook timeout (attempt {attempt})")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Webhook connection error: {e}")
            except httpx.TooManyRedirects:
                return {"success": False, "error": "Too many redirects"}
            except Exception as e:
                last_error = str(e)
                logger.error(f"Webhook error: {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"success": False, "error": last_error or "Max retries exceeded"}

    def _build_auth_header(self, auth_type: str, auth_value: str) -> Optional[str]:
        """Builds authentication header."""
        auth_type = auth_type.lower()

        if auth_type == "bearer":
            return f"Bearer {auth_value}"

        elif auth_type == "basic":
            # auth_value should be "username:password"
            if ":" not in auth_value:
                return f"Basic {auth_value}"  # Assume already encoded
            encoded = base64.b64encode(auth_value.encode()).decode()
            return f"Basic {encoded}"

        elif auth_type == "api_key":
            return auth_value

        return None

    def _prepare_body(self, payload: Any, content_type: str) -> Any:
        """Prepares request body."""
        if payload is None:
            return None

        # Parse string JSON
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return payload

        return payload

    def _parse_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Parses HTTP response."""
        result = {
            "success": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "headers": dict(response.headers)
        }

        # Check response size
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self.config.max_response_size:
            result["response_data"] = {"error": "Response too large"}
            result["truncated"] = True
            return result

        # Parse response body
        content_type = response.headers.get("content-type", "")

        try:
            if "application/json" in content_type:
                result["response_data"] = response.json()
            elif "text/" in content_type or "xml" in content_type:
                result["response_data"] = {"text": response.text[:100000]}  # Limit text
            else:
                # Binary or unknown - return limited text
                result["response_data"] = {"raw": response.text[:10000]}
        except Exception:
            result["response_data"] = {"raw": response.text[:10000]}

        return result


# ============================================================
# WEBHOOK NODE
# ============================================================

class WebhookNode(BaseNode):
    """
    Outbound Webhook Node.

    Features:
    - Multiple HTTP methods (GET, POST, PUT, PATCH, DELETE)
    - Authentication support (Bearer, Basic, API Key)
    - Custom headers
    - URL validation (blocks internal IPs)
    - Retry with exponential backoff
    - Response parsing
    - Timeout configuration

    Use Cases:
    - External API integration
    - Slack/Discord notifications
    - CRM updates
    - Third-party service triggers
    """

    node_type = "webhookNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "HTTP Webhook",
            "icon": "Globe",
            "category": "Integration",
            "description": "Send HTTP requests to external APIs and webhooks.",
            "fields": [
                {
                    "name": "url",
                    "label": "URL",
                    "type": "text",
                    "required": True,
                    "placeholder": "https://api.example.com/webhook"
                },
                {
                    "name": "method",
                    "label": "HTTP Method",
                    "type": "select",
                    "options": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "default": "POST"
                },
                {
                    "name": "content_type",
                    "label": "Content Type",
                    "type": "select",
                    "options": ["json", "form", "text", "xml"],
                    "default": "json"
                },
                {
                    "name": "payload",
                    "label": "Request Body",
                    "type": "json_editor",
                    "placeholder": '{"key": "value"}',
                    "helper": "JSON payload for POST/PUT/PATCH requests"
                },
                {
                    "name": "headers",
                    "label": "Custom Headers",
                    "type": "json_editor",
                    "placeholder": '{"X-Custom-Header": "value"}',
                    "helper": "Additional HTTP headers"
                },
                {
                    "name": "auth_type",
                    "label": "Authentication",
                    "type": "select",
                    "options": ["none", "bearer", "basic", "api_key"],
                    "default": "none"
                },
                {
                    "name": "auth_value",
                    "label": "Auth Token/Credentials",
                    "type": "password",
                    "conditional": {"auth_type": ["bearer", "basic", "api_key"]},
                    "helper": "Bearer: token | Basic: user:pass | API Key: key value"
                },
                {
                    "name": "timeout",
                    "label": "Timeout (seconds)",
                    "type": "number",
                    "default": 30,
                    "helper": "Request timeout (max 120s)"
                },
                {
                    "name": "follow_redirects",
                    "label": "Follow Redirects",
                    "type": "boolean",
                    "default": True
                },
                {
                    "name": "retry_on_failure",
                    "label": "Retry on Failure",
                    "type": "boolean",
                    "default": True,
                    "helper": "Retry on 5xx errors and timeouts"
                }
            ],
            "outputs": ["status", "status_code", "response_data", "headers"],
            "outputs_schema": {
                "status": {"type": "string", "description": "Execution status ('success' or 'error')"},
                "status_code": {"type": "number", "description": "HTTP response status code"},
                "response_data": {"type": "object", "description": "Parsed response body (JSON, text, or raw)"},
                "headers": {"type": "object", "description": "Response headers"}
            }
        }

    def __init__(self):
        super().__init__()
        self.config = WebhookConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes webhook request."""
        url = input_data.get("url", "").strip()

        if not url:
            return {"status": "error", "error": "URL is required"}

        # Get parameters
        method = input_data.get("method", "POST")
        content_type = input_data.get("content_type", "json")
        payload = self._parse_json_field(input_data.get("payload"))
        headers = self._parse_json_field(input_data.get("headers")) or {}

        # Authentication
        auth_type = input_data.get("auth_type", "none")
        auth_value = input_data.get("auth_value")
        if auth_type == "none":
            auth_type = None
            auth_value = None

        # Options
        timeout = input_data.get("timeout", 30)
        follow_redirects = input_data.get("follow_redirects", True)
        retry_on_failure = input_data.get("retry_on_failure", True)

        # Adjust config for no retry
        config = self.config
        if not retry_on_failure:
            config = WebhookConfig(
                default_timeout=config.default_timeout,
                max_timeout=config.max_timeout,
                max_retries=1,
                retry_delay=config.retry_delay,
                max_response_size=config.max_response_size,
                max_payload_size=config.max_payload_size
            )

        # Create client and make request
        client = WebhookClient(config)

        result = await client.request(
            url=url,
            method=method,
            payload=payload,
            headers=headers,
            auth_type=auth_type,
            auth_value=auth_value,
            content_type=content_type,
            timeout=timeout,
            follow_redirects=follow_redirects
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error"),
                "status_code": result.get("status_code")
            }

        return {
            "status": "success",
            "status_code": result.get("status_code"),
            "response_data": result.get("response_data"),
            "headers": result.get("headers", {})
        }

    def _parse_json_field(self, value: Any) -> Any:
        """Parses a JSON field that might be a string."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value