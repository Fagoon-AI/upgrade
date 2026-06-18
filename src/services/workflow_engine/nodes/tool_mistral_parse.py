import asyncio
import base64
import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto
from src.services.workflow.storage_service import StorageService


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class MistralParseConfig:
    """Configuration for Mistral Parse operations."""
    timeout: float = 180.0
    max_retries: int = 3
    retry_delay: float = 2.0
    storage_threshold_bytes: int = 50_000
    max_file_size_mb: int = 100


OUTPUT_FORMATS = ["markdown", "text", "json", "structured"]

# Mistral OCR Pricing (per page)
MISTRAL_OCR_COST_PER_PAGE = Decimal("0.01")  # $0.01 per page


# ============================================================
# USAGE TRACKING
# ============================================================

@dataclass
class MistralUsage:
    """Usage tracking for Mistral OCR."""
    pages_processed: int = 0
    input_tokens: int = 0  # Estimated from content size
    output_tokens: int = 0  # Estimated from output size
    total_tokens: int = 0
    cost_usd: str = "0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "pages_processed": self.pages_processed
        }

    @staticmethod
    def calculate_cost(pages: int) -> Decimal:
        """Calculates cost based on pages processed."""
        return (MISTRAL_OCR_COST_PER_PAGE * pages).quantize(Decimal("0.000001"))

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimates tokens from text (approx 4 chars per token)."""
        return len(text) // 4 if text else 0


# ============================================================
# URL VALIDATOR
# ============================================================

class DocumentURLValidator:
    """Validates document URLs for OCR processing."""

    ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif'}

    @classmethod
    def validate(cls, url: str) -> tuple[bool, Optional[str]]:
        """Validates a document URL."""
        if not url:
            return False, "Document URL is required"

        url = url.strip()

        try:
            parsed = urlparse(url)
        except Exception:
            return False, "Invalid URL format"

        if parsed.scheme not in ['http', 'https']:
            return False, "URL must use HTTP or HTTPS"

        path = parsed.path.lower()
        has_valid_ext = any(path.endswith(ext) for ext in cls.ALLOWED_EXTENSIONS)

        if not has_valid_ext and '.' in path.split('/')[-1]:
            ext = '.' + path.split('.')[-1]
            if ext not in cls.ALLOWED_EXTENSIONS:
                logger.warning(f"Unusual file extension: {ext}")

        return True, None


# ============================================================
# MISTRAL PARSE CLIENT
# ============================================================

class MistralParseClient:
    """Robust Mistral OCR API client."""

    API_BASE = "https://api.mistral.ai/v1"

    def __init__(self, api_key: str, config: Optional[MistralParseConfig] = None):
        self.api_key = api_key
        self.config = config or MistralParseConfig()

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def parse_document(
            self,
            document: Dict[str, Any],
            model: str = "mistral-ocr-latest",
            pages: Optional[List[int]] = None,
            include_image_base64: bool = False
    ) -> Dict[str, Any]:
        """Parses a document using Mistral OCR."""
        payload = {
            "model": model,
            "document": document
        }

        if pages:
            payload["pages"] = pages

        if include_image_base64:
            payload["include_image_base64"] = True

        return await self._make_request("/ocr", payload)

    async def _make_request(
            self,
            endpoint: str,
            payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Makes API request with retry logic."""
        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    response = await client.post(
                        f"{self.API_BASE}{endpoint}",
                        headers=self.headers,
                        json=payload
                    )

                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 30))
                        logger.warning(f"Mistral rate limited. Waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status_code >= 500:
                        if attempt < self.config.max_retries:
                            logger.warning(f"Mistral server error {response.status_code}. Retrying...")
                            await asyncio.sleep(self.config.retry_delay * attempt)
                            continue

                    if response.status_code == 200:
                        return {
                            "success": True,
                            "data": response.json()
                        }

                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message") or error_data.get("error") or str(error_data)
                    except:
                        error_msg = response.text

                    return {
                        "success": False,
                        "error": f"API Error ({response.status_code}): {error_msg}"
                    }

            except httpx.TimeoutException:
                last_error = "Request timed out. Large documents may require more time."
                logger.warning(f"Mistral timeout (attempt {attempt})")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Mistral connection error: {e}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Mistral request error: {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"success": False, "error": last_error or "Max retries exceeded"}


# ============================================================
# CONTENT FORMATTER
# ============================================================

class ContentFormatter:
    """Formats OCR output in various formats."""

    @staticmethod
    def to_markdown(pages: List[Dict[str, Any]]) -> str:
        """Converts pages to markdown."""
        parts = []
        for i, page in enumerate(pages):
            content = page.get("markdown", "")
            if content:
                parts.append(f"<!-- Page {i + 1} -->\n{content}")
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def to_text(pages: List[Dict[str, Any]]) -> str:
        """Converts pages to plain text."""
        parts = []
        for page in pages:
            content = page.get("markdown", "")
            text = re.sub(r'[#*_`\[\]]', '', content)
            text = re.sub(r'\n{3,}', '\n\n', text)
            if text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts)

    @staticmethod
    def to_json(data: Dict[str, Any]) -> str:
        """Returns full response as JSON."""
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def to_structured(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extracts structured data from pages."""
        result = {
            "pages": [],
            "tables": [],
            "images": [],
            "metadata": {}
        }

        for i, page in enumerate(pages):
            page_data = {
                "page_number": i + 1,
                "content": page.get("markdown", ""),
                "dimensions": page.get("dimensions", {})
            }
            result["pages"].append(page_data)

            if "tables" in page:
                for table in page["tables"]:
                    table["source_page"] = i + 1
                    result["tables"].append(table)

            if "images" in page:
                for img in page["images"]:
                    img["source_page"] = i + 1
                    result["images"].append(img)

        return result


# ============================================================
# MISTRAL PARSE NODE
# ============================================================

class MistralParseNode(BaseNode):
    """
    Mistral OCR/Parse Node with Cost Tracking.

    Features:
    - Multi-format document input (URL, base64, upload)
    - Multiple output formats (markdown, text, json, structured)
    - Page range selection
    - Large content offloading to GCS
    - Usage tracking for billing
    """

    node_type = "mistralParseNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Mistral OCR",
            "icon": "FileSearch",
            "category": "AI & Documents",
            "description": "Extract text and structure from PDFs and images with cost tracking.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "Mistral Connection",
                    "type": "connection_select",
                    "provider": "MISTRAL",
                    "helper": "Or provide API key directly"
                },
                {
                    "name": "api_key",
                    "label": "API Key",
                    "type": "password",
                    "helper": "Required if not using connection"
                },
                {
                    "name": "input_method",
                    "label": "Input Method",
                    "type": "select",
                    "options": ["url", "base64", "upload"],
                    "default": "url"
                },
                {
                    "name": "document_url",
                    "label": "Document URL",
                    "type": "text",
                    "placeholder": "https://example.com/document.pdf",
                    "conditional": {"input_method": "url"}
                },
                {
                    "name": "document_base64",
                    "label": "Base64 Content",
                    "type": "textarea",
                    "conditional": {"input_method": "base64"},
                    "helper": "Base64 encoded document content"
                },
                {
                    "name": "upload_url",
                    "label": "Uploaded File URL",
                    "type": "text",
                    "conditional": {"input_method": "upload"},
                    "helper": "URL from file upload"
                },
                {
                    "name": "output_format",
                    "label": "Output Format",
                    "type": "select",
                    "options": ["markdown", "text", "json", "structured"],
                    "default": "markdown"
                },
                {
                    "name": "pages",
                    "label": "Page Range",
                    "type": "text",
                    "placeholder": "1,2,3 or 1-5",
                    "helper": "Leave empty for all pages (1-indexed)"
                },
                {
                    "name": "include_images",
                    "label": "Include Images",
                    "type": "boolean",
                    "default": False,
                    "helper": "Include base64 images in response"
                },
                {
                    "name": "offload_large",
                    "label": "Offload Large Results",
                    "type": "boolean",
                    "default": True,
                    "helper": "Store large results in cloud storage"
                }
            ],
            "outputs": ["status", "parsed_text", "page_count", "is_offloaded", "format", "usage"],
            "outputs_schema": {
                "status": {"type": "string", "description": "Execution status"},
                "parsed_text": {"type": "string", "description": "Extracted text"},
                "page_count": {"type": "number", "description": "Number of pages processed"},
                "is_offloaded": {"type": "boolean", "description": "Whether result was offloaded"},
                "format": {"type": "string", "description": "Output format used"},
                "usage": {"type": "object", "description": "Usage and cost information"}
            }
        }

    def __init__(self):
        super().__init__()
        self.config = MistralParseConfig()
        self.storage = StorageService()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any],
            node_id: str = None
    ) -> Dict[str, Any]:
        """Executes document parsing with cost tracking."""
        # Get API key
        api_key = await self._get_api_key(db, input_data)

        if not api_key:
            return {"status": "error", "error": "API key is required"}

        # Build document object
        try:
            document = self._build_document(input_data)
        except ValueError as e:
            return {"status": "error", "error": str(e)}

        # Parse page range
        pages = self._parse_pages(input_data.get("pages", ""))

        # Get options
        output_format = input_data.get("output_format", "markdown")
        include_images = input_data.get("include_images", False)
        offload_large = input_data.get("offload_large", True)

        # Create client and make request
        client = MistralParseClient(api_key, self.config)

        result = await client.parse_document(
            document=document,
            pages=pages,
            include_image_base64=include_images
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Parsing failed")
            }

        # Format output
        data = result.get("data", {})
        pages_data = data.get("pages", [])

        formatted = self._format_output(pages_data, data, output_format)

        # Calculate usage
        page_count = len(pages_data)
        output_size = len(formatted.encode('utf-8') if isinstance(formatted, str) else json.dumps(formatted).encode('utf-8'))

        usage = MistralUsage(
            pages_processed=page_count,
            input_tokens=0,  # OCR doesn't have input tokens
            output_tokens=MistralUsage.estimate_tokens(
                formatted if isinstance(formatted, str) else json.dumps(formatted)
            ),
            cost_usd=str(MistralUsage.calculate_cost(page_count))
        )
        usage.total_tokens = usage.output_tokens

        logger.debug(
            f"Mistral OCR usage: {page_count} pages, ~{usage.output_tokens} output tokens, ${usage.cost_usd}"
        )

        # Check if offloading is needed
        is_offloaded = False

        if offload_large and output_size > self.config.storage_threshold_bytes:
            try:
                ext = "json" if output_format in ["json", "structured"] else "md"
                content_str = formatted if isinstance(formatted, str) else json.dumps(formatted, indent=2)

                storage_uri = await self.storage.upload_artifact(
                    execution_id=context.execution_id,
                    node_id=self.node_type,
                    content=content_str,
                    filename=f"parsed_{context.execution_id[:8]}.{ext}"
                )

                if storage_uri:
                    formatted = storage_uri
                    is_offloaded = True
                    logger.info(f"Large content offloaded to: {storage_uri}")
            except Exception as e:
                logger.warning(f"Failed to offload content: {e}")

        return {
            "status": "success",
            "parsed_text": formatted,
            "page_count": page_count,
            "is_offloaded": is_offloaded,
            "format": output_format,
            "usage": usage.to_dict()  # Normalized format for executor
        }

    async def _get_api_key(
            self,
            db: AsyncSession,
            input_data: Dict[str, Any]
    ) -> Optional[str]:
        """Gets API key from connection or direct input."""
        connection_id = input_data.get("connection_id")

        if connection_id:
            result = await db.execute(
                select(Connection).where(Connection.id == connection_id)
            )
            conn = result.scalars().first()

            if conn:
                try:
                    creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
                    return creds.get("api_key")
                except Exception as e:
                    logger.error(f"Failed to decrypt connection: {e}")

        return input_data.get("api_key")

    def _build_document(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Builds document object for API request."""
        input_method = input_data.get("input_method", "url")

        if input_method == "url":
            url = input_data.get("document_url", "").strip()
            if not url:
                raise ValueError("Document URL is required")

            is_valid, error = DocumentURLValidator.validate(url)
            if not is_valid:
                raise ValueError(error)

            return {
                "type": "document_url",
                "document_url": url
            }

        elif input_method == "base64":
            base64_content = input_data.get("document_base64", "").strip()
            if not base64_content:
                raise ValueError("Base64 content is required")

            try:
                base64.b64decode(base64_content)
            except Exception:
                raise ValueError("Invalid base64 encoding")

            return {
                "type": "base64",
                "base64": base64_content
            }

        elif input_method == "upload":
            upload_url = input_data.get("upload_url", "").strip()
            if not upload_url:
                raise ValueError("Upload URL is required")

            return {
                "type": "document_url",
                "document_url": upload_url
            }

        raise ValueError(f"Unknown input method: {input_method}")

    def _parse_pages(self, pages_str: str) -> Optional[List[int]]:
        """Parses page range string to list of page numbers."""
        if not pages_str or not pages_str.strip():
            return None

        pages = set()
        parts = pages_str.replace(" ", "").split(",")

        for part in parts:
            if "-" in part:
                try:
                    start, end = part.split("-")
                    start = int(start)
                    end = int(end)
                    pages.update(range(start - 1, end))
                except ValueError:
                    continue
            else:
                try:
                    pages.add(int(part) - 1)
                except ValueError:
                    continue

        if not pages:
            return None

        return sorted(list(pages))

    def _format_output(
            self,
            pages: List[Dict[str, Any]],
            data: Dict[str, Any],
            format_type: str
    ) -> Any:
        """Formats parsed output."""
        if format_type == "markdown":
            return ContentFormatter.to_markdown(pages)
        elif format_type == "text":
            return ContentFormatter.to_text(pages)
        elif format_type == "json":
            return ContentFormatter.to_json(data)
        elif format_type == "structured":
            return ContentFormatter.to_structured(pages)
        else:
            return ContentFormatter.to_markdown(pages)