import asyncio
import re
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone

import httpx
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.services.workflow_engine.nodes.base import BaseNode, NodeExecutionError, ConnectionError
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class BrowserConfig:
    """Configuration for browser operations."""
    default_timeout: float = 60.0       # Request timeout
    max_retries: int = 3                # Max retry attempts
    retry_delay: float = 2.0            # Base delay between retries
    max_content_size: int = 500_000     # 500KB max content
    truncate_content: bool = True       # Truncate if over limit
    wait_until: str = "networkidle2"    # Page load wait condition
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# Browserless endpoints (primary and fallbacks)
BROWSERLESS_ENDPOINTS = [
    "https://production-sfo.browserless.io",
    "https://chrome.browserless.io",
]

# Common HTTP errors and whether to retry
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}


# ============================================================
# URL VALIDATION
# ============================================================

class URLValidator:
    """Validates and sanitizes URLs for browser requests."""

    # Blocked URL patterns (security)
    BLOCKED_PATTERNS = [
        r'^file://',           # Local files
        r'^javascript:',       # JavaScript injection
        r'^data:',             # Data URIs
        r'localhost',          # Localhost
        r'127\.0\.0\.1',       # Loopback
        r'0\.0\.0\.0',         # All interfaces
        r'192\.168\.',         # Private network
        r'10\.',               # Private network
        r'172\.(1[6-9]|2[0-9]|3[0-1])\.', # Private network
    ]

    # Allowed schemes
    ALLOWED_SCHEMES = {'http', 'https'}

    @classmethod
    def validate(cls, url: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validates a URL for browser fetching.

        Returns:
            Tuple of (is_valid, normalized_url, error_message)
        """
        if not url:
            return False, "", "URL is required"

        url = url.strip()

        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            return False, "", f"Invalid URL format: {e}"

        # Check scheme
        if parsed.scheme.lower() not in cls.ALLOWED_SCHEMES:
            return False, "", f"Invalid scheme: {parsed.scheme}"

        # Check for blocked patterns
        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return False, "", f"URL blocked for security: matches {pattern}"

        # Check hostname exists
        if not parsed.netloc:
            return False, "", "URL missing hostname"

        return True, url, None


# CONTENT EXTRACTOR

class ContentExtractor:
    """Extracts and processes content from browser responses."""

    @staticmethod
    def extract_text_from_html(html: str, max_length: int = 100_000) -> str:
        """
        Extracts readable text from HTML.

        Simple extraction without external dependencies.
        """
        if not html:
            return ""

        # Remove script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)

        # Decode HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)

        # Clean whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        # Truncate if needed
        if len(text) > max_length:
            text = text[:max_length] + "...[truncated]"

        return text

    @staticmethod
    def extract_metadata(html: str) -> Dict[str, Any]:
        """Extracts metadata from HTML."""
        metadata = {}

        # Title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            metadata['title'] = title_match.group(1).strip()

        # Meta description
        desc_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        if desc_match:
            metadata['description'] = desc_match.group(1).strip()

        # OG tags
        og_matches = re.findall(
            r'<meta[^>]+property=["\']og:(\w+)["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE
        )
        for key, value in og_matches:
            metadata[f'og_{key}'] = value

        return metadata


# ============================================================
# BROWSER USE NODE
# ============================================================

class BrowserUseNode(BaseNode):
    """
    Web Browser Node.

    Features:
    - Robust error handling with retry logic
    - URL validation and security checks
    - Content extraction and sanitization
    - Multiple browser service fallbacks
    - Configurable wait conditions
    - Screenshot support

    Supported Operations:
    - fetch: Get page content
    - screenshot: Capture page image
    - extract_text: Get readable text only
    """

    node_type = "browserUseNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Web Browser",
            "icon": "Globe",
            "category": "Intelligence Tools",
            "description": "Extract content from URLs with anti-bot bypass and retry logic.",
            "fields": [
                {
                    "name": "url",
                    "label": "Target URL",
                    "type": "text",
                    "required": True,
                    "placeholder": "https://example.com"
                },
                {
                    "name": "connection_id",
                    "label": "Browserless Connection",
                    "type": "connection_select",
                    "provider": "BROWSERLESS",
                    "helper": "Or provide API key directly below"
                },
                {
                    "name": "api_key",
                    "label": "Browserless API Key",
                    "type": "password",
                    "helper": "Used if no connection selected"
                },
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": ["fetch", "extract_text", "screenshot"],
                    "default": "fetch"
                },
                {
                    "name": "wait_until",
                    "label": "Wait Until",
                    "type": "select",
                    "options": ["load", "domcontentloaded", "networkidle0", "networkidle2"],
                    "default": "networkidle2",
                    "helper": "When to consider page loaded"
                },
                {
                    "name": "timeout",
                    "label": "Timeout (seconds)",
                    "type": "number",
                    "default": 60
                },
                {
                    "name": "use_proxy",
                    "label": "Use Residential Proxy",
                    "type": "boolean",
                    "default": True,
                    "helper": "Better bypass but slower"
                },
                {
                    "name": "max_content_size",
                    "label": "Max Content Size",
                    "type": "number",
                    "default": 100000,
                    "helper": "Characters to return (0 = unlimited)"
                },
                {
                    "name": "extract_metadata",
                    "label": "Extract Metadata",
                    "type": "boolean",
                    "default": True
                }
            ],
            "outputs": ["page_content", "text_content", "metadata", "url", "status"]
        }

    def __init__(self):
        super().__init__()
        self.config = BrowserConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes browser fetch with comprehensive error handling."""

        # 1. Extract and validate configuration
        url = input_data.get("url", "").strip()
        operation = input_data.get("operation", "fetch")
        wait_until = input_data.get("wait_until", "networkidle2")
        timeout = float(input_data.get("timeout", 60))
        use_proxy = input_data.get("use_proxy", True)
        max_content = int(input_data.get("max_content_size", 100000))
        extract_meta = input_data.get("extract_metadata", True)

        # 2. Validate URL
        is_valid, normalized_url, url_error = URLValidator.validate(url)
        if not is_valid:
            raise NodeExecutionError(
                message=f"Invalid URL: {url_error}",
                node_type=self.node_type,
                retryable=False
            )

        # 3. Get API key
        api_key = await self._get_api_key(db, input_data)
        if not api_key:
            raise NodeExecutionError(
                message="Browser node requires API key (via connection or direct input)",
                node_type=self.node_type,
                retryable=False
            )

        # 4. Execute with retry
        result = await self._fetch_with_retry(
            url=normalized_url,
            api_key=api_key,
            operation=operation,
            wait_until=wait_until,
            timeout=timeout,
            use_proxy=use_proxy
        )

        if result.get("error"):
            return {
                "status": "error",
                "error": result["error"],
                "url": normalized_url,
                "attempts": result.get("attempts", 1)
            }

        # 5. Process content
        html_content = result.get("content", "")

        # Extract text if requested
        text_content = ""
        if operation == "extract_text" or operation == "fetch":
            text_content = ContentExtractor.extract_text_from_html(
                html_content,
                max_content if max_content > 0 else 100000
            )

        # Truncate HTML if needed
        if max_content > 0 and len(html_content) > max_content:
            html_content = html_content[:max_content] + "...[truncated]"

        # Extract metadata
        metadata = {}
        if extract_meta:
            metadata = ContentExtractor.extract_metadata(result.get("content", ""))

        return {
            "status": "success",
            "url": normalized_url,
            "page_content": html_content if operation != "extract_text" else "",
            "text_content": text_content,
            "metadata": metadata,
            "unblocked": result.get("unblocked", False),
            "attempts": result.get("attempts", 1),
            "content_length": len(html_content)
        }

    async def _get_api_key(
            self,
            db: AsyncSession,
            input_data: Dict[str, Any]
    ) -> Optional[str]:
        """Gets API key from connection or direct input."""

        # Try direct API key first
        api_key = input_data.get("api_key")
        if api_key:
            return api_key

        # Try connection
        connection_id = input_data.get("connection_id")
        if not connection_id:
            return None

        try:
            result = await db.execute(
                select(Connection).where(Connection.id == connection_id)
            )
            conn = result.scalars().first()

            if conn:
                creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
                return creds.get("api_key") or creds.get("token")
        except Exception as e:
            logger.warning(f"Failed to get connection credentials: {e}")

        return None

    async def _fetch_with_retry(
            self,
            url: str,
            api_key: str,
            operation: str,
            wait_until: str,
            timeout: float,
            use_proxy: bool
    ) -> Dict[str, Any]:
        """Fetches URL with retry logic across endpoints."""

        last_error = None
        total_attempts = 0

        # Try each endpoint
        for endpoint in BROWSERLESS_ENDPOINTS:
            for attempt in range(1, self.config.max_retries + 1):
                total_attempts += 1

                try:
                    result = await self._make_request(
                        endpoint=endpoint,
                        url=url,
                        api_key=api_key,
                        operation=operation,
                        wait_until=wait_until,
                        timeout=timeout,
                        use_proxy=use_proxy
                    )

                    if result.get("success"):
                        result["attempts"] = total_attempts
                        return result

                    last_error = result.get("error", "Unknown error")

                    # Check if we should retry
                    status_code = result.get("status_code", 0)
                    if status_code in NON_RETRYABLE_STATUS_CODES:
                        return {
                            "error": last_error,
                            "attempts": total_attempts,
                            "status_code": status_code
                        }

                except asyncio.TimeoutError:
                    last_error = f"Request timeout ({timeout}s)"
                    logger.warning(f"Browser timeout for {url} (attempt {attempt})")
                except httpx.ConnectError as e:
                    last_error = f"Connection failed: {e}"
                    logger.warning(f"Browser connection error: {e}")
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Browser error (attempt {attempt}): {e}")

                # Exponential backoff
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

        return {
            "error": f"All attempts failed. Last error: {last_error}",
            "attempts": total_attempts
        }

    async def _make_request(
            self,
            endpoint: str,
            url: str,
            api_key: str,
            operation: str,
            wait_until: str,
            timeout: float,
            use_proxy: bool
    ) -> Dict[str, Any]:
        """Makes a single request to browserless."""

        # Build request
        params = {"token": api_key}
        if use_proxy:
            params["proxy"] = "residential"

        payload = {
            "url": url,
            "gotoOptions": {
                "waitUntil": wait_until,
                "timeout": int(timeout * 1000)  # Convert to ms
            }
        }

        # Choose endpoint based on operation
        if operation == "screenshot":
            api_endpoint = f"{endpoint}/screenshot"
            payload["options"] = {"fullPage": True, "type": "png"}
        else:
            api_endpoint = f"{endpoint}/unblock"
            payload["content"] = True

        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_endpoint,
                params=params,
                json=payload,
                timeout=timeout + 10,  # Extra buffer
                headers={"User-Agent": self.config.user_agent}
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text[:200]}",
                    "status_code": response.status_code
                }

            try:
                data = response.json()
            except json.JSONDecodeError:
                # For screenshots, content is binary
                if operation == "screenshot":
                    return {
                        "success": True,
                        "content": response.content,
                        "unblocked": True
                    }
                return {
                    "success": False,
                    "error": "Invalid JSON response"
                }

            return {
                "success": True,
                "content": data.get("content", data.get("html", "")),
                "unblocked": data.get("unblocked", True)
            }