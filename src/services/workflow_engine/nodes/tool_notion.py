"""
Notion Integration Node.

Enterprise-grade Notion API integration for database and page operations.
"""

import asyncio
import json
import re
from typing import Dict, Any, List, Optional, Tuple
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
class NotionConfig:
    """Configuration for Notion operations."""
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    page_size: int = 100
    max_page_size: int = 100
    api_version: str = "2022-06-28"


# Notion API base URL
NOTION_API_BASE = "https://api.notion.com/v1"

# Rate limit codes
RATE_LIMIT_CODES = [429]

# Retryable status codes
RETRYABLE_CODES = [500, 502, 503, 504, 429]


# ============================================================
# NOTION CLIENT
# ============================================================

class NotionClient:
    """
    Robust Notion API client with retry logic and pagination.
    """

    def __init__(self, token: str, config: Optional[NotionConfig] = None):
        self.token = token
        self.config = config or NotionConfig()

    def _get_headers(self) -> Dict[str, str]:
        """Gets API headers."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": self.config.api_version
        }

    async def _make_request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Dict[str, Any]] = None,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Makes API request with retry logic."""
        url = f"{NOTION_API_BASE}/{endpoint}"
        headers = self._get_headers()

        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, headers=headers, params=params)
                    elif method.upper() == "POST":
                        response = await client.post(url, headers=headers, json=data)
                    elif method.upper() == "PATCH":
                        response = await client.patch(url, headers=headers, json=data)
                    elif method.upper() == "DELETE":
                        response = await client.delete(url, headers=headers)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    # Handle rate limiting
                    if response.status_code in RATE_LIMIT_CODES:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"Notion rate limited. Waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    # Handle retryable errors
                    if response.status_code in RETRYABLE_CODES and attempt < self.config.max_retries:
                        logger.warning(f"Notion API error {response.status_code}. Retrying...")
                        await asyncio.sleep(self.config.retry_delay * attempt)
                        continue

                    # Parse response
                    if response.status_code == 204:
                        return {"success": True}

                    result = response.json()

                    if response.status_code >= 400:
                        return {
                            "success": False,
                            "error": result.get("message", f"HTTP {response.status_code}"),
                            "code": result.get("code", "unknown_error")
                        }

                    result["success"] = True
                    return result

            except httpx.TimeoutException:
                last_error = "Request timeout"
                logger.warning(f"Notion request timeout (attempt {attempt})")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Notion connection error: {e}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Notion request error: {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"success": False, "error": last_error or "max_retries_exceeded"}

    # ============================================================
    # DATABASE OPERATIONS
    # ============================================================

    async def query_database(
            self,
            database_id: str,
            filter_obj: Optional[Dict] = None,
            sorts: Optional[List[Dict]] = None,
            page_size: int = 100,
            start_cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """Queries a database with filtering and sorting."""
        database_id = self._clean_id(database_id)

        payload: Dict[str, Any] = {
            "page_size": min(page_size, self.config.max_page_size)
        }

        if filter_obj:
            payload["filter"] = filter_obj

        if sorts:
            payload["sorts"] = sorts

        if start_cursor:
            payload["start_cursor"] = start_cursor

        return await self._make_request("POST", f"databases/{database_id}/query", data=payload)

    async def get_database(self, database_id: str) -> Dict[str, Any]:
        """Gets database schema and metadata."""
        database_id = self._clean_id(database_id)
        return await self._make_request("GET", f"databases/{database_id}")

    async def create_database(
            self,
            parent_page_id: str,
            title: str,
            properties: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Creates a new database in a page."""
        parent_page_id = self._clean_id(parent_page_id)

        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties
        }

        return await self._make_request("POST", "databases", data=payload)

    # ============================================================
    # PAGE OPERATIONS
    # ============================================================

    async def create_page(
            self,
            parent_id: str,
            parent_type: str,
            properties: Dict[str, Any],
            children: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Creates a new page in database or page."""
        parent_id = self._clean_id(parent_id)

        if parent_type == "database":
            parent = {"database_id": parent_id}
        else:
            parent = {"page_id": parent_id}

        payload: Dict[str, Any] = {
            "parent": parent,
            "properties": properties
        }

        if children:
            payload["children"] = children

        return await self._make_request("POST", "pages", data=payload)

    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """Gets a page by ID."""
        page_id = self._clean_id(page_id)
        return await self._make_request("GET", f"pages/{page_id}")

    async def update_page(
            self,
            page_id: str,
            properties: Dict[str, Any],
            archived: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Updates a page's properties."""
        page_id = self._clean_id(page_id)

        payload: Dict[str, Any] = {"properties": properties}

        if archived is not None:
            payload["archived"] = archived

        return await self._make_request("PATCH", f"pages/{page_id}", data=payload)

    async def archive_page(self, page_id: str) -> Dict[str, Any]:
        """Archives (soft deletes) a page."""
        return await self.update_page(page_id, {}, archived=True)

    async def get_page_content(self, page_id: str) -> Dict[str, Any]:
        """Gets page content blocks."""
        page_id = self._clean_id(page_id)
        return await self._make_request("GET", f"blocks/{page_id}/children")

    async def append_blocks(
            self,
            page_id: str,
            blocks: List[Dict]
    ) -> Dict[str, Any]:
        """Appends content blocks to a page."""
        page_id = self._clean_id(page_id)

        payload = {"children": blocks}

        return await self._make_request("PATCH", f"blocks/{page_id}/children", data=payload)

    # ============================================================
    # SEARCH
    # ============================================================

    async def search(
            self,
            query: str,
            filter_type: Optional[str] = None,
            sort_direction: str = "descending",
            page_size: int = 100
    ) -> Dict[str, Any]:
        """Searches across all pages and databases."""
        payload: Dict[str, Any] = {
            "query": query,
            "page_size": min(page_size, self.config.max_page_size),
            "sort": {
                "direction": sort_direction,
                "timestamp": "last_edited_time"
            }
        }

        if filter_type in ["page", "database"]:
            payload["filter"] = {"value": filter_type, "property": "object"}

        return await self._make_request("POST", "search", data=payload)

    # ============================================================
    # UTILITIES
    # ============================================================

    def _clean_id(self, id_str: str) -> str:
        """Cleans and validates Notion ID."""
        # Remove URL prefix if present
        if "notion.so" in id_str or "notion.site" in id_str:
            # Extract ID from URL
            match = re.search(r'([a-f0-9]{32}|[a-f0-9-]{36})', id_str)
            if match:
                id_str = match.group(1)

        # Remove dashes and ensure lowercase
        id_str = id_str.replace("-", "").lower()

        # Add dashes back in standard format
        if len(id_str) == 32:
            return f"{id_str[:8]}-{id_str[8:12]}-{id_str[12:16]}-{id_str[16:20]}-{id_str[20:]}"

        return id_str


# ============================================================
# PROPERTY BUILDERS
# ============================================================

class NotionPropertyBuilder:
    """Builds Notion property objects for page creation/update."""

    @staticmethod
    def title(text: str) -> Dict:
        """Creates a title property."""
        return {
            "title": [{"text": {"content": text}}]
        }

    @staticmethod
    def rich_text(text: str) -> Dict:
        """Creates a rich text property."""
        return {
            "rich_text": [{"text": {"content": text}}]
        }

    @staticmethod
    def number(value: float) -> Dict:
        """Creates a number property."""
        return {"number": value}

    @staticmethod
    def select(option: str) -> Dict:
        """Creates a select property."""
        return {"select": {"name": option}}

    @staticmethod
    def multi_select(options: List[str]) -> Dict:
        """Creates a multi-select property."""
        return {"multi_select": [{"name": opt} for opt in options]}

    @staticmethod
    def date(start: str, end: Optional[str] = None) -> Dict:
        """Creates a date property."""
        date_obj: Dict[str, Any] = {"start": start}
        if end:
            date_obj["end"] = end
        return {"date": date_obj}

    @staticmethod
    def checkbox(checked: bool) -> Dict:
        """Creates a checkbox property."""
        return {"checkbox": checked}

    @staticmethod
    def url(url: str) -> Dict:
        """Creates a URL property."""
        return {"url": url}

    @staticmethod
    def email(email: str) -> Dict:
        """Creates an email property."""
        return {"email": email}

    @staticmethod
    def phone(phone: str) -> Dict:
        """Creates a phone property."""
        return {"phone_number": phone}

    @staticmethod
    def relation(page_ids: List[str]) -> Dict:
        """Creates a relation property."""
        return {"relation": [{"id": pid} for pid in page_ids]}

    @staticmethod
    def status(status: str) -> Dict:
        """Creates a status property."""
        return {"status": {"name": status}}


# ============================================================
# BLOCK BUILDERS
# ============================================================

class NotionBlockBuilder:
    """Builds Notion block objects for page content."""

    @staticmethod
    def paragraph(text: str) -> Dict:
        """Creates a paragraph block."""
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }

    @staticmethod
    def heading_1(text: str) -> Dict:
        """Creates a heading 1 block."""
        return {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }

    @staticmethod
    def heading_2(text: str) -> Dict:
        """Creates a heading 2 block."""
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }

    @staticmethod
    def heading_3(text: str) -> Dict:
        """Creates a heading 3 block."""
        return {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }

    @staticmethod
    def bulleted_list_item(text: str) -> Dict:
        """Creates a bulleted list item."""
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }

    @staticmethod
    def numbered_list_item(text: str) -> Dict:
        """Creates a numbered list item."""
        return {
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }

    @staticmethod
    def to_do(text: str, checked: bool = False) -> Dict:
        """Creates a to-do block."""
        return {
            "object": "block",
            "type": "to_do",
            "to_do": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "checked": checked
            }
        }

    @staticmethod
    def code(code: str, language: str = "plain text") -> Dict:
        """Creates a code block."""
        return {
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": code}}],
                "language": language
            }
        }

    @staticmethod
    def divider() -> Dict:
        """Creates a divider block."""
        return {"object": "block", "type": "divider", "divider": {}}

    @staticmethod
    def callout(text: str, emoji: str = "💡") -> Dict:
        """Creates a callout block."""
        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "icon": {"type": "emoji", "emoji": emoji}
            }
        }

    @staticmethod
    def quote(text: str) -> Dict:
        """Creates a quote block."""
        return {
            "object": "block",
            "type": "quote",
            "quote": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }


# ============================================================
# NOTION NODE
# ============================================================

class NotionNode(BaseNode):
    """
    Enterprise-Grade Notion Integration Node.

    Features:
    - Database query with filters and sorts
    - Page CRUD operations
    - Block content management
    - Search across workspace
    - Property type support
    - Retry with exponential backoff
    - Rate limit handling

    Operations:
    - query_database: Query database with filters
    - create_page: Create new page/database row
    - update_page: Update page properties
    - get_page: Get page details
    - archive_page: Archive/delete page
    - append_content: Add blocks to page
    - search: Search workspace
    """

    node_type = "notionNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Notion",
            "icon": "FileText",
            "category": "Data & Storage",
            "description": "Full Notion workspace integration with databases and pages.",
            "fields": [
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": [
                        "query_database",
                        "create_page",
                        "update_page",
                        "get_page",
                        "archive_page",
                        "append_content",
                        "search"
                    ],
                    "default": "query_database"
                },
                {
                    "name": "connection_id",
                    "label": "Notion Connection",
                    "type": "connection_select",
                    "provider": "NOTION",
                    "required": True
                },
                {
                    "name": "database_id",
                    "label": "Database ID",
                    "type": "text",
                    "placeholder": "Enter database ID or URL",
                    "conditional": {"operation": ["query_database", "create_page"]},
                    "helper": "Database ID or full Notion URL"
                },
                {
                    "name": "page_id",
                    "label": "Page ID",
                    "type": "text",
                    "placeholder": "Enter page ID or URL",
                    "conditional": {"operation": ["update_page", "get_page", "archive_page", "append_content"]},
                    "helper": "Page ID or full Notion URL"
                },
                {
                    "name": "filter",
                    "label": "Filter (JSON)",
                    "type": "code",
                    "language": "json",
                    "conditional": {"operation": "query_database"},
                    "helper": "Notion filter object (optional)"
                },
                {
                    "name": "sorts",
                    "label": "Sorts (JSON)",
                    "type": "code",
                    "language": "json",
                    "conditional": {"operation": "query_database"},
                    "helper": "Array of sort objects (optional)"
                },
                {
                    "name": "properties",
                    "label": "Properties (JSON)",
                    "type": "code",
                    "language": "json",
                    "conditional": {"operation": ["create_page", "update_page"]},
                    "helper": "Page properties object"
                },
                {
                    "name": "content_blocks",
                    "label": "Content Blocks (JSON)",
                    "type": "code",
                    "language": "json",
                    "conditional": {"operation": ["create_page", "append_content"]},
                    "helper": "Array of block objects"
                },
                {
                    "name": "search_query",
                    "label": "Search Query",
                    "type": "text",
                    "conditional": {"operation": "search"},
                    "placeholder": "Search term"
                },
                {
                    "name": "search_filter",
                    "label": "Search Filter",
                    "type": "select",
                    "options": ["all", "page", "database"],
                    "default": "all",
                    "conditional": {"operation": "search"}
                },
                {
                    "name": "page_size",
                    "label": "Page Size",
                    "type": "number",
                    "default": 100,
                    "helper": "Number of results (max 100)"
                }
            ],
            "outputs": ["results", "page", "count", "has_more", "next_cursor", "status"]
        }

    def __init__(self):
        super().__init__()
        self.config = NotionConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes Notion operation."""
        operation = input_data.get("operation", "query_database")

        # Get client
        client = await self._get_client(db, input_data)

        # Execute operation
        if operation == "query_database":
            return await self._query_database(client, input_data)
        elif operation == "create_page":
            return await self._create_page(client, input_data)
        elif operation == "update_page":
            return await self._update_page(client, input_data)
        elif operation == "get_page":
            return await self._get_page(client, input_data)
        elif operation == "archive_page":
            return await self._archive_page(client, input_data)
        elif operation == "append_content":
            return await self._append_content(client, input_data)
        elif operation == "search":
            return await self._search(client, input_data)
        else:
            raise NodeExecutionError(
                message=f"Unknown operation: {operation}",
                node_type=self.node_type,
                retryable=False
            )

    async def _get_client(self, db: AsyncSession, input_data: Dict[str, Any]) -> NotionClient:
        """Gets authenticated Notion client."""
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
                provider="notion"
            )

        try:
            creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
            token = creds.get("access_token")
        except Exception as e:
            raise ConnectionError(
                message="Failed to decrypt credentials",
                node_type=self.node_type,
                provider="notion"
            )

        if not token:
            raise ConnectionError(
                message="Connection missing access token",
                node_type=self.node_type,
                provider="notion"
            )

        return NotionClient(token, self.config)

    async def _query_database(
            self,
            client: NotionClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Queries a database."""
        database_id = input_data.get("database_id", "").strip()

        if not database_id:
            raise NodeExecutionError(
                message="Database ID is required",
                node_type=self.node_type,
                retryable=False
            )

        # Parse filter and sorts
        filter_obj = None
        sorts = None

        filter_str = input_data.get("filter", "").strip()
        if filter_str:
            try:
                filter_obj = json.loads(filter_str)
            except json.JSONDecodeError as e:
                raise NodeExecutionError(
                    message=f"Invalid filter JSON: {e}",
                    node_type=self.node_type,
                    retryable=False
                )

        sorts_str = input_data.get("sorts", "").strip()
        if sorts_str:
            try:
                sorts = json.loads(sorts_str)
            except json.JSONDecodeError as e:
                raise NodeExecutionError(
                    message=f"Invalid sorts JSON: {e}",
                    node_type=self.node_type,
                    retryable=False
                )

        page_size = int(input_data.get("page_size", 100))

        result = await client.query_database(
            database_id=database_id,
            filter_obj=filter_obj,
            sorts=sorts,
            page_size=page_size
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Query failed")
            }

        # Extract and format results
        results = []
        for page in result.get("results", []):
            results.append(self._format_page(page))

        return {
            "status": "success",
            "results": results,
            "count": len(results),
            "has_more": result.get("has_more", False),
            "next_cursor": result.get("next_cursor")
        }

    async def _create_page(
            self,
            client: NotionClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Creates a new page."""
        database_id = input_data.get("database_id", "").strip()
        page_id = input_data.get("page_id", "").strip()

        if not database_id and not page_id:
            raise NodeExecutionError(
                message="Database ID or Page ID is required",
                node_type=self.node_type,
                retryable=False
            )

        # Parse properties
        properties = {}
        props_str = input_data.get("properties", "").strip()
        if props_str:
            try:
                properties = json.loads(props_str)
            except json.JSONDecodeError as e:
                raise NodeExecutionError(
                    message=f"Invalid properties JSON: {e}",
                    node_type=self.node_type,
                    retryable=False
                )

        # Parse content blocks
        children = None
        blocks_str = input_data.get("content_blocks", "").strip()
        if blocks_str:
            try:
                children = json.loads(blocks_str)
            except json.JSONDecodeError as e:
                raise NodeExecutionError(
                    message=f"Invalid content blocks JSON: {e}",
                    node_type=self.node_type,
                    retryable=False
                )

        parent_id = database_id or page_id
        parent_type = "database" if database_id else "page"

        result = await client.create_page(
            parent_id=parent_id,
            parent_type=parent_type,
            properties=properties,
            children=children
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Page creation failed")
            }

        return {
            "status": "success",
            "page": self._format_page(result),
            "page_id": result.get("id"),
            "url": result.get("url")
        }

    async def _update_page(
            self,
            client: NotionClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Updates a page."""
        page_id = input_data.get("page_id", "").strip()

        if not page_id:
            raise NodeExecutionError(
                message="Page ID is required",
                node_type=self.node_type,
                retryable=False
            )

        # Parse properties
        properties = {}
        props_str = input_data.get("properties", "").strip()
        if props_str:
            try:
                properties = json.loads(props_str)
            except json.JSONDecodeError as e:
                raise NodeExecutionError(
                    message=f"Invalid properties JSON: {e}",
                    node_type=self.node_type,
                    retryable=False
                )

        result = await client.update_page(page_id=page_id, properties=properties)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Page update failed")
            }

        return {
            "status": "success",
            "page": self._format_page(result),
            "page_id": result.get("id")
        }

    async def _get_page(
            self,
            client: NotionClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Gets a page."""
        page_id = input_data.get("page_id", "").strip()

        if not page_id:
            raise NodeExecutionError(
                message="Page ID is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.get_page(page_id)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Page retrieval failed")
            }

        # Also get content
        content_result = await client.get_page_content(page_id)
        content = content_result.get("results", []) if content_result.get("success") else []

        formatted = self._format_page(result)
        formatted["content"] = content

        return {
            "status": "success",
            "page": formatted,
            "page_id": result.get("id"),
            "url": result.get("url")
        }

    async def _archive_page(
            self,
            client: NotionClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Archives a page."""
        page_id = input_data.get("page_id", "").strip()

        if not page_id:
            raise NodeExecutionError(
                message="Page ID is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.archive_page(page_id)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Page archive failed")
            }

        return {
            "status": "success",
            "page_id": page_id,
            "archived": True
        }

    async def _append_content(
            self,
            client: NotionClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Appends content blocks to a page."""
        page_id = input_data.get("page_id", "").strip()

        if not page_id:
            raise NodeExecutionError(
                message="Page ID is required",
                node_type=self.node_type,
                retryable=False
            )

        # Parse content blocks
        blocks = []
        blocks_str = input_data.get("content_blocks", "").strip()
        if blocks_str:
            try:
                blocks = json.loads(blocks_str)
            except json.JSONDecodeError as e:
                raise NodeExecutionError(
                    message=f"Invalid content blocks JSON: {e}",
                    node_type=self.node_type,
                    retryable=False
                )

        if not blocks:
            raise NodeExecutionError(
                message="Content blocks are required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.append_blocks(page_id, blocks)

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Content append failed")
            }

        return {
            "status": "success",
            "page_id": page_id,
            "blocks_added": len(blocks)
        }

    async def _search(
            self,
            client: NotionClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Searches workspace."""
        query = input_data.get("search_query", "").strip()
        filter_type = input_data.get("search_filter", "all")
        page_size = int(input_data.get("page_size", 100))

        if filter_type == "all":
            filter_type = None

        result = await client.search(
            query=query,
            filter_type=filter_type,
            page_size=page_size
        )

        if not result.get("success"):
            return {
                "status": "error",
                "error": result.get("error", "Search failed")
            }

        # Format results
        results = []
        for item in result.get("results", []):
            results.append(self._format_page(item))

        return {
            "status": "success",
            "results": results,
            "count": len(results),
            "has_more": result.get("has_more", False),
            "next_cursor": result.get("next_cursor")
        }

    def _format_page(self, page: Dict) -> Dict[str, Any]:
        """Formats a page/database item for output."""
        formatted = {
            "id": page.get("id"),
            "object": page.get("object"),
            "url": page.get("url"),
            "created_time": page.get("created_time"),
            "last_edited_time": page.get("last_edited_time"),
            "archived": page.get("archived", False),
            "properties": {}
        }

        # Extract property values
        for prop_name, prop_value in page.get("properties", {}).items():
            formatted["properties"][prop_name] = self._extract_property_value(prop_value)

        return formatted

    def _extract_property_value(self, prop: Dict) -> Any:
        """Extracts the actual value from a Notion property."""
        prop_type = prop.get("type")

        if prop_type == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", []))
        elif prop_type == "rich_text":
            return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
        elif prop_type == "number":
            return prop.get("number")
        elif prop_type == "select":
            sel = prop.get("select")
            return sel.get("name") if sel else None
        elif prop_type == "multi_select":
            return [s.get("name") for s in prop.get("multi_select", [])]
        elif prop_type == "date":
            date = prop.get("date")
            return date if date else None
        elif prop_type == "checkbox":
            return prop.get("checkbox", False)
        elif prop_type == "url":
            return prop.get("url")
        elif prop_type == "email":
            return prop.get("email")
        elif prop_type == "phone_number":
            return prop.get("phone_number")
        elif prop_type == "status":
            status = prop.get("status")
            return status.get("name") if status else None
        elif prop_type == "relation":
            return [r.get("id") for r in prop.get("relation", [])]
        elif prop_type == "formula":
            formula = prop.get("formula", {})
            return formula.get(formula.get("type"))
        elif prop_type == "rollup":
            rollup = prop.get("rollup", {})
            return rollup.get(rollup.get("type"))
        else:
            return prop.get(prop_type)
