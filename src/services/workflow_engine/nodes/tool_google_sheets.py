import asyncio
import json
import re
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

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
class SheetsConfig:
    """Configuration for Sheets operations."""
    max_retries: int = 3
    retry_delay: float = 1.0
    max_cells_per_request: int = 10_000_000  # 10 million cells limit
    default_range: str = "Sheet1!A:Z"


# Operation to scope mapping
OPERATION_SCOPES = {
    "READ_DATA": {"https://www.googleapis.com/auth/spreadsheets.readonly"},
    "APPEND_DATA": {"https://www.googleapis.com/auth/spreadsheets"},
    "UPDATE_DATA": {"https://www.googleapis.com/auth/spreadsheets"},
    "CLEAR_DATA": {"https://www.googleapis.com/auth/spreadsheets"},
    "GET_METADATA": {"https://www.googleapis.com/auth/spreadsheets.readonly"},
    "CREATE_SHEET": {"https://www.googleapis.com/auth/spreadsheets"},
}

# Full access scope (covers all operations)
FULL_ACCESS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


# ============================================================
# RANGE VALIDATOR
# ============================================================

class RangeValidator:
    """Validates and parses Google Sheets range notation."""

    # A1 notation pattern: Sheet1!A1:B10 or A1:B10 or Sheet1!A:Z
    RANGE_PATTERN = re.compile(
        r"^(?:(?P<sheet>[^!]+)!)?"  # Optional sheet name
        r"(?P<start>[A-Z]+)(?P<start_row>\d+)?"  # Start column and optional row
        r"(?::(?P<end>[A-Z]+)(?P<end_row>\d+)?)?$",  # Optional end
        re.IGNORECASE
    )

    @classmethod
    def validate(cls, range_str: str) -> Tuple[bool, Optional[str]]:
        """Validates a range string."""
        if not range_str:
            return False, "Range is required"

        range_str = range_str.strip()

        # Check for basic format
        if not cls.RANGE_PATTERN.match(range_str):
            return False, f"Invalid range format: {range_str}"

        return True, None

    @classmethod
    def parse(cls, range_str: str) -> Dict[str, Any]:
        """Parses a range string into components."""
        match = cls.RANGE_PATTERN.match(range_str.strip())
        if not match:
            return {}

        return {
            "sheet": match.group("sheet") or "Sheet1",
            "start_col": match.group("start"),
            "start_row": match.group("start_row"),
            "end_col": match.group("end"),
            "end_row": match.group("end_row"),
        }

    @classmethod
    def normalize(cls, range_str: str, default_sheet: str = "Sheet1") -> str:
        """Normalizes a range string."""
        parsed = cls.parse(range_str)
        if not parsed:
            return range_str

        sheet = parsed.get("sheet") or default_sheet
        start = parsed.get("start_col", "A")
        start_row = parsed.get("start_row") or ""
        end = parsed.get("end_col")
        end_row = parsed.get("end_row") or ""

        if end:
            return f"{sheet}!{start}{start_row}:{end}{end_row}"
        return f"{sheet}!{start}{start_row}"


# ============================================================
# SHEETS CLIENT
# ============================================================

class SheetsClient:
    """
    Robust Google Sheets API client.
    """

    def __init__(self, credentials_data: Dict[str, Any], config: Optional[SheetsConfig] = None):
        self.creds_data = credentials_data
        self.config = config or SheetsConfig()
        self._service = None
        self._credentials = None

    async def _get_service(self):
        """Gets Sheets service with fresh credentials."""
        if self._service:
            return self._service

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from google.auth.transport.requests import Request
        except ImportError:
            raise NodeExecutionError(
                message="Google API libraries not installed",
                node_type="googleSheetsNode",
                retryable=False
            )

        # Get scopes from credentials
        scopes = self.creds_data.get("scopes", [])
        if isinstance(scopes, str):
            scopes = [scopes]

        # Build credentials
        self._credentials = Credentials(
            token=self.creds_data.get("token"),
            refresh_token=self.creds_data.get("refresh_token"),
            token_uri=self.creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=self.creds_data.get("client_id"),
            client_secret=self.creds_data.get("client_secret"),
            scopes=scopes
        )

        # Refresh if expired
        if self._credentials.expired and self._credentials.refresh_token:
            try:
                request = Request()
                await asyncio.to_thread(self._credentials.refresh, request)
                logger.info("Sheets token refreshed successfully")
            except Exception as e:
                raise ConnectionError(
                    message=f"Token refresh failed: {e}",
                    node_type="googleSheetsNode",
                    provider="google"
                )

        # Build service
        self._service = build(
            'sheets', 'v4',
            credentials=self._credentials,
            cache_discovery=False
        )

        return self._service

    def check_scopes(self, operation: str) -> Tuple[bool, List[str]]:
        """Checks if current scopes are sufficient for operation."""
        granted_scopes = set(self.creds_data.get("scopes", []))
        required_scopes = OPERATION_SCOPES.get(operation, set())

        # Full access scope covers everything
        if FULL_ACCESS_SCOPE in granted_scopes:
            return True, []

        missing = required_scopes - granted_scopes
        return len(missing) == 0, list(missing)

    async def read_data(
            self,
            spreadsheet_id: str,
            range_name: str,
            value_render_option: str = "FORMATTED_VALUE"
    ) -> Dict[str, Any]:
        """Reads data from a range."""
        service = await self._get_service()

        try:
            result = await asyncio.to_thread(
                service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueRenderOption=value_render_option
                ).execute
            )

            values = result.get('values', [])

            return {
                "success": True,
                "rows": values,
                "count": len(values),
                "range": result.get('range')
            }

        except Exception as e:
            return self._handle_error(e)

    async def append_data(
            self,
            spreadsheet_id: str,
            range_name: str,
            values: List[List[Any]],
            value_input_option: str = "USER_ENTERED"
    ) -> Dict[str, Any]:
        """Appends rows to a sheet."""
        service = await self._get_service()

        # Ensure values is a list of lists
        if values and not isinstance(values[0], list):
            values = [values]

        try:
            result = await asyncio.to_thread(
                service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    insertDataOption="INSERT_ROWS",
                    body={'values': values}
                ).execute
            )

            updates = result.get('updates', {})

            return {
                "success": True,
                "updated_range": updates.get('updatedRange'),
                "updated_rows": updates.get('updatedRows', 0),
                "updated_cells": updates.get('updatedCells', 0)
            }

        except Exception as e:
            return self._handle_error(e)

    async def update_data(
            self,
            spreadsheet_id: str,
            range_name: str,
            values: List[List[Any]],
            value_input_option: str = "USER_ENTERED"
    ) -> Dict[str, Any]:
        """Updates data in a specific range."""
        service = await self._get_service()

        # Ensure values is a list of lists
        if values and not isinstance(values[0], list):
            values = [values]

        try:
            result = await asyncio.to_thread(
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    body={'values': values}
                ).execute
            )

            return {
                "success": True,
                "updated_range": result.get('updatedRange'),
                "updated_rows": result.get('updatedRows', 0),
                "updated_cells": result.get('updatedCells', 0)
            }

        except Exception as e:
            return self._handle_error(e)

    async def clear_data(
            self,
            spreadsheet_id: str,
            range_name: str
    ) -> Dict[str, Any]:
        """Clears data from a range."""
        service = await self._get_service()

        try:
            result = await asyncio.to_thread(
                service.spreadsheets().values().clear(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    body={}
                ).execute
            )

            return {
                "success": True,
                "cleared_range": result.get('clearedRange')
            }

        except Exception as e:
            return self._handle_error(e)

    async def get_metadata(
            self,
            spreadsheet_id: str
    ) -> Dict[str, Any]:
        """Gets spreadsheet metadata."""
        service = await self._get_service()

        try:
            result = await asyncio.to_thread(
                service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id,
                    fields="properties,sheets.properties"
                ).execute
            )

            sheets = []
            for sheet in result.get('sheets', []):
                props = sheet.get('properties', {})
                sheets.append({
                    "sheet_id": props.get('sheetId'),
                    "title": props.get('title'),
                    "index": props.get('index'),
                    "row_count": props.get('gridProperties', {}).get('rowCount'),
                    "column_count": props.get('gridProperties', {}).get('columnCount')
                })

            return {
                "success": True,
                "title": result.get('properties', {}).get('title'),
                "locale": result.get('properties', {}).get('locale'),
                "sheets": sheets,
                "sheet_count": len(sheets)
            }

        except Exception as e:
            return self._handle_error(e)

    async def create_sheet(
            self,
            spreadsheet_id: str,
            sheet_title: str
    ) -> Dict[str, Any]:
        """Creates a new sheet in the spreadsheet."""
        service = await self._get_service()

        try:
            result = await asyncio.to_thread(
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        'requests': [{
                            'addSheet': {
                                'properties': {'title': sheet_title}
                            }
                        }]
                    }
                ).execute
            )

            replies = result.get('replies', [])
            if replies:
                sheet_props = replies[0].get('addSheet', {}).get('properties', {})
                return {
                    "success": True,
                    "sheet_id": sheet_props.get('sheetId'),
                    "title": sheet_props.get('title')
                }

            return {"success": True, "title": sheet_title}

        except Exception as e:
            return self._handle_error(e)

    def _handle_error(self, error: Exception) -> Dict[str, Any]:
        """Handles API errors."""
        error_str = str(error).lower()

        if "invalid_grant" in error_str or "token" in error_str:
            return {
                "success": False,
                "error": "Authentication expired. Please re-authenticate.",
                "auth_error": True
            }

        if "not found" in error_str:
            return {
                "success": False,
                "error": "Spreadsheet not found. Check the spreadsheet ID."
            }

        if "permission" in error_str or "forbidden" in error_str:
            return {
                "success": False,
                "error": "Permission denied. Check sharing settings."
            }

        if "quota" in error_str or "rate" in error_str:
            return {
                "success": False,
                "error": "Rate limit exceeded. Please try again later.",
                "retryable": True
            }

        return {"success": False, "error": str(error)}


# ============================================================
# GOOGLE SHEETS NODE
# ============================================================

class GoogleSheetsNode(BaseNode):
    """
    Google Sheets Integration Node.

    Features:
    - OAuth2 with token refresh
    - Scope validation
    - Range validation
    - Batch operations
    - Multiple sheet support

    Operations:
    - READ_DATA: Read from range
    - APPEND_DATA: Add rows
    - UPDATE_DATA: Update specific range
    - CLEAR_DATA: Clear range
    - GET_METADATA: Get spreadsheet info
    - CREATE_SHEET: Add new sheet
    """

    node_type = "googleSheetsNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Google Sheets",
            "icon": "Grid",
            "category": "Data & Storage",
            "description": "spreadsheet automation with batch operations.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "Google Connection",
                    "type": "connection_select",
                    "provider": "GOOGLE",
                    "required": True
                },
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": ["READ_DATA", "APPEND_DATA", "UPDATE_DATA", "CLEAR_DATA", "GET_METADATA", "CREATE_SHEET"],
                    "default": "READ_DATA"
                },
                {
                    "name": "spreadsheet_id",
                    "label": "Spreadsheet ID",
                    "type": "text",
                    "required": True,
                    "helper": "Found in the spreadsheet URL"
                },
                {
                    "name": "range",
                    "label": "Range",
                    "type": "text",
                    "default": "Sheet1!A:Z",
                    "placeholder": "Sheet1!A1:D10",
                    "conditional": {"operation": ["READ_DATA", "APPEND_DATA", "UPDATE_DATA", "CLEAR_DATA"]}
                },
                {
                    "name": "values",
                    "label": "Values",
                    "type": "json_editor",
                    "placeholder": '[[\"Name\", \"Value\"], [\"Row 2\", \"Data\"]]',
                    "conditional": {"operation": ["APPEND_DATA", "UPDATE_DATA"]},
                    "helper": "2D array of values"
                },
                {
                    "name": "sheet_title",
                    "label": "New Sheet Name",
                    "type": "text",
                    "conditional": {"operation": "CREATE_SHEET"}
                },
                {
                    "name": "value_render_option",
                    "label": "Value Format",
                    "type": "select",
                    "options": ["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"],
                    "default": "FORMATTED_VALUE",
                    "conditional": {"operation": "READ_DATA"}
                }
            ],
            "outputs": ["status", "rows", "count", "updated_range", "sheets", "sheet_id"]
        }

    def __init__(self):
        super().__init__()
        self.config = SheetsConfig()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes Google Sheets operation."""
        connection_id = input_data.get("connection_id")
        operation = input_data.get("operation", "READ_DATA").upper()
        spreadsheet_id = input_data.get("spreadsheet_id", "").strip()

        if not connection_id:
            raise NodeExecutionError(
                message="Connection ID is required",
                node_type=self.node_type,
                retryable=False
            )

        if not spreadsheet_id:
            raise NodeExecutionError(
                message="Spreadsheet ID is required",
                node_type=self.node_type,
                retryable=False
            )

        # Get credentials
        creds_data = await self._get_credentials(db, connection_id)
        client = SheetsClient(creds_data, self.config)

        # Check scopes
        has_scopes, missing = client.check_scopes(operation)
        if not has_scopes:
            return {
                "status": "requires_auth",
                "selected_branch": "paused",
                "error_code": "INSUFFICIENT_SCOPES",
                "missing_scopes": missing,
                "message": f"Operation '{operation}' requires additional permissions"
            }

        # Execute operation
        if operation == "READ_DATA":
            return await self._read_data(client, input_data)
        elif operation == "APPEND_DATA":
            return await self._append_data(client, input_data)
        elif operation == "UPDATE_DATA":
            return await self._update_data(client, input_data)
        elif operation == "CLEAR_DATA":
            return await self._clear_data(client, input_data)
        elif operation == "GET_METADATA":
            return await self._get_metadata(client, input_data)
        elif operation == "CREATE_SHEET":
            return await self._create_sheet(client, input_data)
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

        try:
            return json.loads(crypto.decrypt(connection.encrypted_credentials))
        except Exception as e:
            raise ConnectionError(
                message="Failed to decrypt credentials",
                node_type=self.node_type,
                provider="google"
            )

    async def _read_data(
            self,
            client: SheetsClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reads data from spreadsheet."""
        spreadsheet_id = input_data.get("spreadsheet_id")
        range_name = input_data.get("range", self.config.default_range)
        value_render = input_data.get("value_render_option", "FORMATTED_VALUE")

        # Validate range
        is_valid, error = RangeValidator.validate(range_name)
        if not is_valid:
            raise NodeExecutionError(message=error, node_type=self.node_type, retryable=False)

        result = await client.read_data(
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
            value_render_option=value_render
        )

        if not result.get("success"):
            if result.get("auth_error"):
                return {"status": "requires_auth", "error": result.get("error"), "selected_branch": "paused"}
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "rows": result.get("rows", []),
            "count": result.get("count", 0),
            "range": result.get("range")
        }

    async def _append_data(
            self,
            client: SheetsClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Appends data to spreadsheet."""
        spreadsheet_id = input_data.get("spreadsheet_id")
        range_name = input_data.get("range", self.config.default_range)
        values = input_data.get("values", [])

        if not values:
            raise NodeExecutionError(
                message="Values are required for append operation",
                node_type=self.node_type,
                retryable=False
            )

        # Parse JSON if string
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except json.JSONDecodeError:
                raise NodeExecutionError(
                    message="Invalid JSON format for values",
                    node_type=self.node_type,
                    retryable=False
                )

        result = await client.append_data(
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
            values=values
        )

        if not result.get("success"):
            if result.get("auth_error"):
                return {"status": "requires_auth", "error": result.get("error"), "selected_branch": "paused"}
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "appended": True,
            "updated_range": result.get("updated_range"),
            "updated_rows": result.get("updated_rows"),
            "updated_cells": result.get("updated_cells")
        }

    async def _update_data(
            self,
            client: SheetsClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Updates data in spreadsheet."""
        spreadsheet_id = input_data.get("spreadsheet_id")
        range_name = input_data.get("range")
        values = input_data.get("values", [])

        if not range_name:
            raise NodeExecutionError(
                message="Range is required for update operation",
                node_type=self.node_type,
                retryable=False
            )

        if not values:
            raise NodeExecutionError(
                message="Values are required for update operation",
                node_type=self.node_type,
                retryable=False
            )

        # Parse JSON if string
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except json.JSONDecodeError:
                raise NodeExecutionError(
                    message="Invalid JSON format for values",
                    node_type=self.node_type,
                    retryable=False
                )

        result = await client.update_data(
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
            values=values
        )

        if not result.get("success"):
            if result.get("auth_error"):
                return {"status": "requires_auth", "error": result.get("error"), "selected_branch": "paused"}
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "updated": True,
            "updated_range": result.get("updated_range"),
            "updated_rows": result.get("updated_rows"),
            "updated_cells": result.get("updated_cells")
        }

    async def _clear_data(
            self,
            client: SheetsClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Clears data from spreadsheet."""
        spreadsheet_id = input_data.get("spreadsheet_id")
        range_name = input_data.get("range")

        if not range_name:
            raise NodeExecutionError(
                message="Range is required for clear operation",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.clear_data(
            spreadsheet_id=spreadsheet_id,
            range_name=range_name
        )

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "cleared": True,
            "cleared_range": result.get("cleared_range")
        }

    async def _get_metadata(
            self,
            client: SheetsClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Gets spreadsheet metadata."""
        spreadsheet_id = input_data.get("spreadsheet_id")

        result = await client.get_metadata(spreadsheet_id=spreadsheet_id)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "title": result.get("title"),
            "sheets": result.get("sheets", []),
            "sheet_count": result.get("sheet_count", 0)
        }

    async def _create_sheet(
            self,
            client: SheetsClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Creates a new sheet."""
        spreadsheet_id = input_data.get("spreadsheet_id")
        sheet_title = input_data.get("sheet_title", "").strip()

        if not sheet_title:
            raise NodeExecutionError(
                message="Sheet title is required",
                node_type=self.node_type,
                retryable=False
            )

        result = await client.create_sheet(
            spreadsheet_id=spreadsheet_id,
            sheet_title=sheet_title
        )

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "created": True,
            "sheet_id": result.get("sheet_id"),
            "title": result.get("title")
        }