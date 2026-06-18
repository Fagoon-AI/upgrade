import re
import json
import operator
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
from functools import wraps

from sqlalchemy.ext.asyncio import AsyncSession
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import BaseLoader, TemplateError, UndefinedError
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext


# ============================================================
# CONFIGURATION
# ============================================================

# Maximum regex execution time (simplified - pattern complexity limit)
MAX_REGEX_LENGTH = 500

# Truthy string values
TRUTHY_VALUES = frozenset([
    "true", "1", "yes", "y", "on", "enabled", "success", "ok", "t"
])

# Falsy string values
FALSY_VALUES = frozenset([
    "false", "0", "no", "n", "off", "disabled", "failure", "fail", "f", ""
])


# ============================================================
# SECURE JINJA2 ENVIRONMENT
# ============================================================

class SecureJinjaEnvironment:
    """
    Creates a sandboxed Jinja2 environment with custom filters and tests.

    Security features:
    - SandboxedEnvironment prevents dangerous operations
    - Limited regex execution
    - No file system access
    - No arbitrary code execution
    """

    def __init__(self):
        self.env = SandboxedEnvironment(
            loader=BaseLoader(),
            autoescape=False,  # We're not outputting HTML
            keep_trailing_newline=False
        )

        # Register custom filters
        self._register_filters()

        # Register custom tests
        self._register_tests()

    def _register_filters(self):
        """Registers custom Jinja2 filters."""

        # Type conversion filters
        self.env.filters['to_int'] = self._safe_int
        self.env.filters['to_float'] = self._safe_float
        self.env.filters['to_str'] = str
        self.env.filters['to_bool'] = self._to_bool
        self.env.filters['to_list'] = self._to_list

        # String filters
        self.env.filters['strip'] = lambda x: str(x).strip() if x else ""
        self.env.filters['normalize'] = self._normalize_string

        # JSON filters
        self.env.filters['json_path'] = self._json_path
        self.env.filters['from_json'] = self._safe_json_loads

        # Collection filters
        self.env.filters['first_or'] = lambda lst, default=None: lst[0] if lst else default
        self.env.filters['last_or'] = lambda lst, default=None: lst[-1] if lst else default
        self.env.filters['get'] = lambda d, key, default=None: d.get(key, default) if isinstance(d, dict) else default

        # Comparison helpers
        self.env.filters['is_empty'] = lambda x: not x or (isinstance(x, (list, dict, str)) and len(x) == 0)
        self.env.filters['is_not_empty'] = lambda x: bool(x) and (not isinstance(x, (list, dict, str)) or len(x) > 0)

    def _register_tests(self):
        """Registers custom Jinja2 tests."""

        # Regex test with safety limits
        self.env.tests['search'] = self._safe_regex_search
        self.env.tests['match'] = self._safe_regex_match

        # Type tests
        self.env.tests['list'] = lambda x: isinstance(x, list)
        self.env.tests['dict'] = lambda x: isinstance(x, dict)
        self.env.tests['string'] = lambda x: isinstance(x, str)
        self.env.tests['number'] = lambda x: isinstance(x, (int, float))
        self.env.tests['truthy'] = self._is_truthy
        self.env.tests['falsy'] = self._is_falsy

        # Comparison tests
        self.env.tests['gt'] = lambda x, y: self._safe_compare(x, y, operator.gt)
        self.env.tests['gte'] = lambda x, y: self._safe_compare(x, y, operator.ge)
        self.env.tests['lt'] = lambda x, y: self._safe_compare(x, y, operator.lt)
        self.env.tests['lte'] = lambda x, y: self._safe_compare(x, y, operator.le)
        self.env.tests['between'] = self._is_between

        # String tests
        self.env.tests['contains'] = lambda x, y: str(y).lower() in str(x).lower() if x and y else False
        self.env.tests['startswith'] = lambda x, y: str(x).lower().startswith(str(y).lower()) if x and y else False
        self.env.tests['endswith'] = lambda x, y: str(x).lower().endswith(str(y).lower()) if x and y else False

    # Filter implementations
    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Safely converts value to int."""
        try:
            if isinstance(value, bool):
                return 1 if value else 0
            return int(float(value))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Safely converts value to float."""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _to_bool(value: Any) -> bool:
        """Converts value to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower().strip() in TRUTHY_VALUES
        return bool(value)

    @staticmethod
    def _to_list(value: Any) -> List:
        """Converts value to list."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, (tuple, set)):
            return list(value)
        if isinstance(value, str):
            # Try JSON array
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except:
                pass
        return [value]

    @staticmethod
    def _normalize_string(value: Any) -> str:
        """Normalizes string (lowercase, strip, single spaces)."""
        if value is None:
            return ""
        s = str(value).lower().strip()
        return re.sub(r'\s+', ' ', s)

    @staticmethod
    def _json_path(data: Any, path: str, default: Any = None) -> Any:
        """Accesses nested JSON data using dot notation."""
        if data is None:
            return default

        try:
            parts = path.split('.')
            result = data

            for part in parts:
                # Handle array index
                if '[' in part and ']' in part:
                    key, idx = part.split('[')
                    idx = int(idx.rstrip(']'))

                    if key:
                        result = result.get(key, []) if isinstance(result, dict) else []

                    if isinstance(result, list) and 0 <= idx < len(result):
                        result = result[idx]
                    else:
                        return default
                else:
                    if isinstance(result, dict):
                        result = result.get(part, default)
                    else:
                        return default

            return result
        except Exception:
            return default

    @staticmethod
    def _safe_json_loads(value: str, default: Any = None) -> Any:
        """Safely parses JSON string."""
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except:
            return default

    # Test implementations
    @staticmethod
    def _safe_regex_search(value: Any, pattern: str) -> bool:
        """Safely performs regex search with limits."""
        if value is None:
            return False

        # Limit pattern length
        if len(pattern) > MAX_REGEX_LENGTH:
            logger.warning(f"Regex pattern too long: {len(pattern)} chars")
            return False

        try:
            return re.search(pattern, str(value), re.IGNORECASE) is not None
        except re.error as e:
            logger.warning(f"Invalid regex pattern: {e}")
            return False

    @staticmethod
    def _safe_regex_match(value: Any, pattern: str) -> bool:
        """Safely performs regex match with limits."""
        if value is None:
            return False

        if len(pattern) > MAX_REGEX_LENGTH:
            return False

        try:
            return re.match(pattern, str(value), re.IGNORECASE) is not None
        except re.error:
            return False

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        """Checks if value is truthy."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower().strip() in TRUTHY_VALUES
        if isinstance(value, (int, float)):
            return value != 0
        return bool(value)

    @staticmethod
    def _is_falsy(value: Any) -> bool:
        """Checks if value is falsy."""
        if value is None:
            return True
        if isinstance(value, bool):
            return not value
        if isinstance(value, str):
            return value.lower().strip() in FALSY_VALUES
        if isinstance(value, (int, float)):
            return value == 0
        return not bool(value)

    @staticmethod
    def _safe_compare(x: Any, y: Any, op) -> bool:
        """Safely compares two values."""
        try:
            # Try numeric comparison first
            x_num = float(x) if not isinstance(x, bool) else (1 if x else 0)
            y_num = float(y) if not isinstance(y, bool) else (1 if y else 0)
            return op(x_num, y_num)
        except (ValueError, TypeError):
            # Fall back to string comparison
            return op(str(x), str(y))

    @staticmethod
    def _is_between(value: Any, low: Any, high: Any) -> bool:
        """Checks if value is between low and high (inclusive)."""
        try:
            v = float(value)
            return float(low) <= v <= float(high)
        except (ValueError, TypeError):
            return False

    def render(self, template_str: str, context: Dict[str, Any]) -> str:
        """Renders template with context."""
        template = self.env.from_string(template_str)
        return template.render(**context)


# ============================================================
# FILTER NODE
# ============================================================

class FilterNode(BaseNode):
    """
    Condition/Filter Node.

    Features:
    - Sandboxed Jinja2 evaluation
    - Custom comparison operators
    - Safe regex with limits
    - JSON path access
    - Comprehensive truthiness evaluation
    - Error recovery

    Operators:
    - Comparisons: gt, gte, lt, lte, between
    - String: contains, startswith, endswith, search, match
    - Type: is list, is dict, is string, is number
    - Logic: is truthy, is falsy, is empty

    Examples:
    - {{ steps['api'].status_code }} is gt(200)
    - {{ steps['input'].email }} is search('@company\\.com$')
    - {{ steps['data'].items | length }} is between(1, 100)
    - {{ steps['result'].value | json_path('data.users[0].name') }}
    """

    node_type = "filterNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "Condition",
            "icon": "GitBranch",
            "category": "Logic & Flow",
            "description": "Evaluate conditions to route workflow through True or False branches.",
            "fields": [
                {
                    "name": "condition",
                    "label": "Condition Expression",
                    "type": "textarea",
                    "required": True,
                    "placeholder": "{{ steps['api'].status == 'success' }}",
                    "helper": "Jinja2 expression that evaluates to true/false"
                },
                {
                    "name": "else_condition",
                    "label": "Else-If Condition",
                    "type": "textarea",
                    "placeholder": "{{ steps['api'].retry_count < 3 }}",
                    "helper": "Optional: evaluated if main condition is false"
                },
                {
                    "name": "error_branch",
                    "label": "Error Handling",
                    "type": "select",
                    "options": ["false_branch", "error_branch", "raise"],
                    "default": "false_branch",
                    "helper": "What to do if evaluation fails"
                }
            ],
            "outputs": ["status", "evaluated", "result", "selected_branch"],
            "outputs_schema": {
                "status": {"type": "string", "description": "Execution status ('success' or 'error')"},
                "evaluated": {"type": "string", "description": "The evaluated expression result"},
                "result": {"type": "boolean", "description": "Whether condition was true or false"},
                "selected_branch": {"type": "string", "description": "Branch taken: 'true', 'false', 'else', or 'error'"}
            },
            "output_handles": [
                {"id": "true", "label": "True", "type": "any", "description": "Taken when condition is true"},
                {"id": "false", "label": "False", "type": "any", "description": "Taken when condition is false"},
                {"id": "else", "label": "Else", "type": "any", "description": "Taken when else-if condition is true"},
                {"id": "error", "label": "Error", "type": "any", "description": "Taken when evaluation fails"}
            ]
        }

    def __init__(self):
        super().__init__()
        self.jinja = SecureJinjaEnvironment()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes condition evaluation."""
        condition = input_data.get("condition", "").strip()
        else_condition = input_data.get("else_condition", "").strip()
        error_handling = input_data.get("error_branch", "false_branch")

        if not condition:
            return self._error_response(
                "Condition expression is required",
                error_handling
            )

        # Build template context
        template_context = {
            "steps": context.node_outputs,
            "item": input_data.get("loop_item"),
            "env": input_data.get("env", {}),
            "now": datetime.now(timezone.utc),
            "true": True,
            "false": False,
            "null": None
        }

        # Evaluate main condition
        main_result = self._evaluate_condition(condition, template_context)

        if main_result["error"]:
            return self._error_response(
                main_result["error"],
                error_handling,
                condition=condition
            )

        # Main condition is true
        if main_result["value"]:
            return {
                "status": "success",
                "evaluated": str(main_result["raw"]),
                "result": True,
                "selected_branch": "true"
            }

        # Check else-if condition
        if else_condition:
            else_result = self._evaluate_condition(else_condition, template_context)

            if else_result["error"]:
                return self._error_response(
                    else_result["error"],
                    error_handling,
                    condition=else_condition
                )

            if else_result["value"]:
                return {
                    "status": "success",
                    "evaluated": str(else_result["raw"]),
                    "result": True,
                    "selected_branch": "else"
                }

        # All conditions false
        return {
            "status": "success",
            "evaluated": str(main_result["raw"]),
            "result": False,
            "selected_branch": "false"
        }

    def _evaluate_condition(
            self,
            condition: str,
            context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluates a single condition."""
        try:
            # Render template
            result_str = self.jinja.render(condition, context)
            result_str = result_str.strip().lower()

            # Evaluate truthiness
            is_true = self._is_truthy(result_str)

            return {
                "value": is_true,
                "raw": result_str,
                "error": None
            }

        except UndefinedError as e:
            return {
                "value": False,
                "raw": None,
                "error": f"Undefined variable: {e}"
            }
        except TemplateError as e:
            return {
                "value": False,
                "raw": None,
                "error": f"Template error: {e}"
            }
        except Exception as e:
            return {
                "value": False,
                "raw": None,
                "error": f"Evaluation error: {e}"
            }

    def _is_truthy(self, value: str) -> bool:
        """Determines if a rendered value is truthy."""
        if not value:
            return False

        value = value.lower().strip()

        # Check explicit truthy values
        if value in TRUTHY_VALUES:
            return True

        # Check explicit falsy values
        if value in FALSY_VALUES:
            return False

        # Try numeric
        try:
            return float(value) != 0
        except ValueError:
            pass

        # Non-empty string is truthy
        return bool(value)

    def _error_response(
            self,
            error: str,
            handling: str,
            condition: str = None
    ) -> Dict[str, Any]:
        """Creates error response based on handling strategy."""
        logger.warning(
            f"Filter condition error: {error}",
            extra={"condition": condition}
        )

        if handling == "raise":
            raise ValueError(f"Condition evaluation failed: {error}")

        if handling == "error_branch":
            return {
                "status": "error",
                "error": error,
                "condition": condition,
                "selected_branch": "error"
            }

        # Default: false_branch
        return {
            "status": "error",
            "error": error,
            "condition": condition,
            "selected_branch": "false"
        }