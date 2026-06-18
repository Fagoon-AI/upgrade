import asyncio
import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class SupabaseConfig:
    """Configuration for Supabase operations."""
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    max_batch_size: int = 1000


# Retryable HTTP status codes
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


# ============================================================
# URL VALIDATOR
# ============================================================

class SupabaseURLValidator:
    """Validates Supabase project URLs."""

    # Pattern for valid Supabase URLs
    SUPABASE_PATTERN = re.compile(
        r'^https://[a-z0-9-]+\.supabase\.co$',
        re.IGNORECASE
    )

    @classmethod
    def validate(cls, url: str) -> tuple[bool, Optional[str]]:
        """Validates a Supabase project URL."""
        if not url:
            return False, "Project URL is required"

        url = url.strip().rstrip('/')

        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception:
            return False, "Invalid URL format"

        # Must be HTTPS
        if parsed.scheme != 'https':
            return False, "URL must use HTTPS"

        # Must be a Supabase domain
        if not cls.SUPABASE_PATTERN.match(url):
            return False, "Invalid Supabase URL format. Expected: https://xxx.supabase.co"

        return True, None

    @classmethod
    def normalize(cls, url: str) -> str:
        """Normalizes a Supabase URL."""
        return url.strip().rstrip('/')


# ============================================================
# SUPABASE CLIENT
# ============================================================

class SupabaseClient:
    """
    Robust Supabase REST API client.
    """

    def __init__(
            self,
            project_url: str,
            api_key: str,
            config: Optional[SupabaseConfig] = None
    ):
        self.project_url = SupabaseURLValidator.normalize(project_url)
        self.api_key = api_key
        self.config = config or SupabaseConfig()

        self.headers = {
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Any] = None,
            params: Optional[Dict[str, str]] = None,
            headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Makes HTTP request with retry logic."""
        url = f"{self.project_url}/rest/v1/{endpoint}"
        request_headers = {**self.headers, **(headers or {})}

        last_error = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        json=data,
                        params=params,
                        headers=request_headers
                    )

                    # Check for rate limiting
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"Supabase rate limited. Waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    # Check for retryable errors
                    if response.status_code in RETRYABLE_STATUS_CODES:
                        if attempt < self.config.max_retries:
                            await asyncio.sleep(self.config.retry_delay * attempt)
                            continue

                    # Parse response
                    if response.status_code in [200, 201, 204]:
                        try:
                            result = response.json() if response.content else None
                        except json.JSONDecodeError:
                            result = None

                        return {
                            "success": True,
                            "data": result,
                            "status_code": response.status_code
                        }

                    # Error response
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message") or error_data.get("error") or str(error_data)
                    except:
                        error_msg = response.text

                    return {
                        "success": False,
                        "error": error_msg,
                        "status_code": response.status_code
                    }

            except httpx.TimeoutException:
                last_error = "Request timed out"
                logger.warning(f"Supabase timeout (attempt {attempt})")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Supabase connection error: {e}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Supabase request error: {e}")

            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay * attempt)

        return {"success": False, "error": last_error or "Max retries exceeded"}

    async def select(
            self,
            table: str,
            columns: str = "*",
            filters: Optional[Dict[str, Any]] = None,
            order: Optional[str] = None,
            limit: Optional[int] = None,
            offset: Optional[int] = None
    ) -> Dict[str, Any]:
        """Selects data from a table."""
        params = {"select": columns}

        # Build filter params
        if filters:
            for key, value in filters.items():
                if isinstance(value, dict):
                    # Handle operators like {"gt": 10}
                    for op, val in value.items():
                        params[key] = f"{op}.{val}"
                else:
                    params[key] = f"eq.{value}"

        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        if offset:
            params["offset"] = str(offset)

        return await self._request("GET", table, params=params)

    async def insert(
            self,
            table: str,
            data: Any,
            return_data: bool = True
    ) -> Dict[str, Any]:
        """Inserts data into a table."""
        headers = {}
        if return_data:
            headers["Prefer"] = "return=representation"

        return await self._request("POST", table, data=data, headers=headers)

    async def update(
            self,
            table: str,
            data: Dict[str, Any],
            filters: Dict[str, Any],
            return_data: bool = True
    ) -> Dict[str, Any]:
        """Updates data in a table."""
        # Build filter params
        params = {}
        for key, value in filters.items():
            params[key] = f"eq.{value}"

        headers = {}
        if return_data:
            headers["Prefer"] = "return=representation"

        return await self._request("PATCH", table, data=data, params=params, headers=headers)

    async def upsert(
            self,
            table: str,
            data: Any,
            on_conflict: Optional[str] = None,
            return_data: bool = True
    ) -> Dict[str, Any]:
        """Upserts data into a table."""
        headers = {"Prefer": "resolution=merge-duplicates"}
        if return_data:
            headers["Prefer"] += ",return=representation"

        params = {}
        if on_conflict:
            params["on_conflict"] = on_conflict

        return await self._request("POST", table, data=data, params=params, headers=headers)

    async def delete(
            self,
            table: str,
            filters: Dict[str, Any],
            return_data: bool = False
    ) -> Dict[str, Any]:
        """Deletes data from a table."""
        # Build filter params
        params = {}
        for key, value in filters.items():
            params[key] = f"eq.{value}"

        headers = {}
        if return_data:
            headers["Prefer"] = "return=representation"

        return await self._request("DELETE", table, params=params, headers=headers)

    async def rpc(
            self,
            function_name: str,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Calls a Supabase RPC function."""
        url = f"{self.project_url}/rest/v1/rpc/{function_name}"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    url,
                    json=params or {},
                    headers=self.headers
                )

                if response.status_code in [200, 201]:
                    return {
                        "success": True,
                        "data": response.json() if response.content else None
                    }

                return {
                    "success": False,
                    "error": response.text,
                    "status_code": response.status_code
                }
        except Exception as e:
            return {"success": False, "error": str(e)}


# ============================================================
# SUPABASE NODE
# ============================================================

class SupabaseNode(BaseNode):
    """
    World-Class Supabase Integration Node.

    Features:
    - Multiple operations (select, insert, update, upsert, delete, rpc)
    - Connection-based or direct credentials
    - Retry with exponential backoff
    - Batch operations
    - Filter support

    Operations:
    - SELECT: Query data with filters
    - INSERT: Insert single or multiple rows
    - UPDATE: Update rows matching filters
    - UPSERT: Insert or update on conflict
    - DELETE: Delete rows matching filters
    - RPC: Call database functions
    """

    node_type = "supabaseNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Supabase",
            "icon": "Database",
            "category": "Data & Storage",
            "description": "Enterprise Supabase integration with full CRUD support.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "Supabase Connection",
                    "type": "connection_select",
                    "provider": "SUPABASE",
                    "helper": "Or provide credentials directly below"
                },
                {
                    "name": "project_url",
                    "label": "Project URL",
                    "type": "text",
                    "placeholder": "https://xyz.supabase.co",
                    "helper": "Required if not using connection"
                },
                {
                    "name": "service_role_key",
                    "label": "Service Role Key",
                    "type": "password",
                    "helper": "Required if not using connection"
                },
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": ["SELECT", "INSERT", "UPDATE", "UPSERT", "DELETE", "RPC"],
                    "default": "INSERT"
                },
                {
                    "name": "table_name",
                    "label": "Table Name",
                    "type": "text",
                    "required": True,
                    "conditional": {"operation": ["SELECT", "INSERT", "UPDATE", "UPSERT", "DELETE"]}
                },
                {
                    "name": "function_name",
                    "label": "Function Name",
                    "type": "text",
                    "conditional": {"operation": "RPC"}
                },
                {
                    "name": "columns",
                    "label": "Columns",
                    "type": "text",
                    "default": "*",
                    "conditional": {"operation": "SELECT"},
                    "helper": "Comma-separated column names"
                },
                {
                    "name": "data",
                    "label": "Data",
                    "type": "json_editor",
                    "placeholder": '{"column": "value"}',
                    "conditional": {"operation": ["INSERT", "UPDATE", "UPSERT", "RPC"]}
                },
                {
                    "name": "filters",
                    "label": "Filters",
                    "type": "json_editor",
                    "placeholder": '{"id": "123"}',
                    "conditional": {"operation": ["SELECT", "UPDATE", "DELETE"]},
                    "helper": "Key-value filters for WHERE clause"
                },
                {
                    "name": "order",
                    "label": "Order By",
                    "type": "text",
                    "placeholder": "created_at.desc",
                    "conditional": {"operation": "SELECT"}
                },
                {
                    "name": "limit",
                    "label": "Limit",
                    "type": "number",
                    "default": 100,
                    "conditional": {"operation": "SELECT"}
                },
                {
                    "name": "on_conflict",
                    "label": "On Conflict Column",
                    "type": "text",
                    "conditional": {"operation": "UPSERT"},
                    "helper": "Column for upsert conflict resolution"
                }
            ],
            "outputs": ["status", "data", "count", "error"]
        }

    def __init__(self):
        super().__init__()
        self.config = SupabaseConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes Supabase operation."""
        operation = input_data.get("operation", "INSERT").upper()

        # Get credentials
        project_url, api_key = await self._get_credentials(db, input_data)

        # Validate URL
        is_valid, error = SupabaseURLValidator.validate(project_url)
        if not is_valid:
            return {"status": "error", "error": error}

        # Create client
        client = SupabaseClient(project_url, api_key, self.config)

        # Execute operation
        if operation == "SELECT":
            return await self._execute_select(client, input_data)
        elif operation == "INSERT":
            return await self._execute_insert(client, input_data)
        elif operation == "UPDATE":
            return await self._execute_update(client, input_data)
        elif operation == "UPSERT":
            return await self._execute_upsert(client, input_data)
        elif operation == "DELETE":
            return await self._execute_delete(client, input_data)
        elif operation == "RPC":
            return await self._execute_rpc(client, input_data)
        else:
            return {"status": "error", "error": f"Unknown operation: {operation}"}

    async def _get_credentials(
            self,
            db: AsyncSession,
            input_data: Dict[str, Any]
    ) -> tuple[str, str]:
        """Gets credentials from connection or direct input."""
        connection_id = input_data.get("connection_id")

        if connection_id:
            result = await db.execute(
                select(Connection).where(Connection.id == connection_id)
            )
            conn = result.scalars().first()

            if not conn:
                raise ValueError(f"Connection {connection_id} not found")

            creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
            return creds.get("project_url"), creds.get("service_role_key") or creds.get("api_key")

        # Direct credentials
        project_url = input_data.get("project_url")
        api_key = input_data.get("service_role_key")

        if not project_url or not api_key:
            raise ValueError("Either connection_id or project_url and service_role_key are required")

        return project_url, api_key

    async def _execute_select(
            self,
            client: SupabaseClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes SELECT operation."""
        table = input_data.get("table_name")
        if not table:
            return {"status": "error", "error": "Table name is required"}

        columns = input_data.get("columns", "*")
        filters = self._parse_json_field(input_data.get("filters"))
        order = input_data.get("order")
        limit = input_data.get("limit", 100)

        result = await client.select(
            table=table,
            columns=columns,
            filters=filters,
            order=order,
            limit=limit
        )

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        data = result.get("data", [])
        return {
            "status": "success",
            "data": data,
            "count": len(data) if isinstance(data, list) else 1
        }

    async def _execute_insert(
            self,
            client: SupabaseClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes INSERT operation."""
        table = input_data.get("table_name")
        data = self._parse_json_field(input_data.get("data"))

        if not table:
            return {"status": "error", "error": "Table name is required"}
        if not data:
            return {"status": "error", "error": "Data is required for INSERT"}

        result = await client.insert(table=table, data=data)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "data": result.get("data"),
            "inserted": True
        }

    async def _execute_update(
            self,
            client: SupabaseClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes UPDATE operation."""
        table = input_data.get("table_name")
        data = self._parse_json_field(input_data.get("data"))
        filters = self._parse_json_field(input_data.get("filters"))

        if not table:
            return {"status": "error", "error": "Table name is required"}
        if not data:
            return {"status": "error", "error": "Data is required for UPDATE"}
        if not filters:
            return {"status": "error", "error": "Filters are required for UPDATE to prevent accidental mass updates"}

        result = await client.update(table=table, data=data, filters=filters)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "data": result.get("data"),
            "updated": True
        }

    async def _execute_upsert(
            self,
            client: SupabaseClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes UPSERT operation."""
        table = input_data.get("table_name")
        data = self._parse_json_field(input_data.get("data"))
        on_conflict = input_data.get("on_conflict")

        if not table:
            return {"status": "error", "error": "Table name is required"}
        if not data:
            return {"status": "error", "error": "Data is required for UPSERT"}

        result = await client.upsert(table=table, data=data, on_conflict=on_conflict)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "data": result.get("data"),
            "upserted": True
        }

    async def _execute_delete(
            self,
            client: SupabaseClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes DELETE operation."""
        table = input_data.get("table_name")
        filters = self._parse_json_field(input_data.get("filters"))

        if not table:
            return {"status": "error", "error": "Table name is required"}
        if not filters:
            return {"status": "error", "error": "Filters are required for DELETE to prevent accidental mass deletion"}

        result = await client.delete(table=table, filters=filters, return_data=True)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "data": result.get("data"),
            "deleted": True
        }

    async def _execute_rpc(
            self,
            client: SupabaseClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes RPC function call."""
        function_name = input_data.get("function_name")
        params = self._parse_json_field(input_data.get("data"))

        if not function_name:
            return {"status": "error", "error": "Function name is required for RPC"}

        result = await client.rpc(function_name=function_name, params=params)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "data": result.get("data")
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