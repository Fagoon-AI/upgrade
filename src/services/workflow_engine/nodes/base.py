from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, ClassVar, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import copy
import re

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

if TYPE_CHECKING:
    from src.services.workflow_engine.context import ExecutionContext


# FIELD TYPE DEFINITIONS (For new manifest format)

class FieldType(str, Enum):
    """Supported field types for node configuration."""
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    BOOLEAN = "boolean"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    PASSWORD = "password"
    JSON_EDITOR = "json_editor"
    CODE_EDITOR = "code_editor"
    CONNECTION_SELECT = "connection_select"
    FILE_UPLOAD = "file_upload"
    SLIDER = "slider"
    DATE = "date"
    DATETIME = "datetime"
    LIST = "list"


class NodeCategory(str, Enum):
    """Standard categories for node organization."""
    TRIGGERS = "Triggers"
    LOGIC_FLOW = "Logic & Flow"
    AI_DATA = "AI & Data"
    COMMUNICATION = "Communication"
    INTELLIGENCE = "Intelligence Tools"
    DATA_STORAGE = "Data Storage"
    INTEGRATIONS = "Integrations"
    UTILITIES = "Utilities"


# DATACLASS DEFINITIONS FOR TYPE-SAFE MANIFESTS

@dataclass
class FieldDefinition:
    """Type-safe field definition for node manifests."""
    name: str
    label: str
    field_type: FieldType
    required: bool = False
    default: Any = None
    placeholder: Optional[str] = None
    description: Optional[str] = None
    options: Optional[List[Dict[str, Any]]] = None
    validation: Optional[Dict[str, Any]] = None
    depends_on: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "name": self.name,
            "label": self.label,
            "type": self.field_type.value if isinstance(self.field_type, FieldType) else self.field_type,
            "required": self.required
        }
        if self.default is not None:
            result["default"] = self.default
        if self.placeholder:
            result["placeholder"] = self.placeholder
        if self.description:
            result["description"] = self.description
        if self.options:
            result["options"] = self.options
        if self.validation:
            result["validation"] = self.validation
        if self.depends_on:
            result["depends_on"] = self.depends_on
        if self.min_value is not None:
            result["min"] = self.min_value
        if self.max_value is not None:
            result["max"] = self.max_value
        if self.step is not None:
            result["step"] = self.step
        return result


@dataclass
class NodeManifest:
    """Type-safe node manifest definition."""
    type: str
    display_name: str
    icon: str
    category: NodeCategory
    description: str
    fields: List[FieldDefinition] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    documentation_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "type": self.type,
            "display_name": self.display_name,
            "icon": self.icon,
            "category": self.category.value if isinstance(self.category, NodeCategory) else self.category,
            "description": self.description,
            "fields": [f.to_dict() for f in self.fields],
            "outputs": self.outputs,
            "version": self.version
        }
        if self.documentation_url:
            result["documentation_url"] = self.documentation_url
        if self.tags:
            result["tags"] = self.tags
        return result


def define_field(
        name: str,
        label: str,
        field_type: FieldType,
        required: bool = False,
        default: Any = None,
        **kwargs
) -> FieldDefinition:
    """
    Helper function for creating type-safe field definitions.

    Example:
        define_field("api_key", "API Key", FieldType.PASSWORD, required=True)
    """
    return FieldDefinition(
        name=name,
        label=label,
        field_type=field_type,
        required=required,
        default=default,
        placeholder=kwargs.get("placeholder"),
        description=kwargs.get("description"),
        options=kwargs.get("options"),
        validation=kwargs.get("validation"),
        depends_on=kwargs.get("depends_on"),
        min_value=kwargs.get("min_value") or kwargs.get("min"),
        max_value=kwargs.get("max_value") or kwargs.get("max"),
        step=kwargs.get("step")
    )


# EXCEPTION CLASSES

class NodeExecutionError(Exception):
    """Base exception for node execution failures."""

    def __init__(
            self,
            message: str,
            node_type: str = "unknown",
            node_id: Optional[str] = None,
            retryable: bool = True,
            details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.node_type = node_type
        self.node_id = node_id
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.message,
            "node_type": self.node_type,
            "node_id": self.node_id,
            "retryable": self.retryable,
            "details": self.details
        }


class InputValidationError(NodeExecutionError):
    """Raised when node inputs fail validation."""

    def __init__(self, message: str, node_type: str, invalid_fields: List[str]):
        super().__init__(
            message=message,
            node_type=node_type,
            retryable=False,
            details={"invalid_fields": invalid_fields}
        )
        self.invalid_fields = invalid_fields


class ConnectionError(NodeExecutionError):
    """Raised when external service connection fails."""

    def __init__(self, message: str, node_type: str, provider: str):
        super().__init__(
            message=message,
            node_type=node_type,
            retryable=True,
            details={"provider": provider}
        )
        self.provider = provider


# BASE NODE CLASS

class BaseNode(ABC):
    """
    Base Node Interface.

    BACKWARD COMPATIBILITY:
    - Existing nodes only need to implement execute() - this is unchanged
    - get_manifest() is optional (returns empty dict by default)
    - All new features are opt-in via method overrides

    Required Implementation:
    - node_type: Class variable identifying the node
    - execute(): The core execution logic

    Optional Implementations:
    - get_manifest(): Returns node specification for discovery
    - validate_inputs(): Custom validation logic
    - on_before_execute(): Pre-execution hook
    - on_after_execute(): Post-execution hook
    - on_error(): Error handling hook

    Usage (Existing - Still Works):
        class MyNode(BaseNode):
            node_type = "myNode"

            async def execute(self, db, context, input_data):
                return {"result": "data"}

    Usage (Enhanced):
        class MyNode(BaseNode):
            node_type = "myNode"

            @classmethod
            def get_manifest(cls):
                return {
                    "type": cls.node_type,
                    "display_name": "My Node",
                    "fields": [...],
                    "outputs": [...]
                }

            async def execute(self, db, context, input_data):
                return {"result": "data"}
    """

    # Class-level configuration (MUST be overridden)
    node_type: ClassVar[str] = "base"

    def __init__(self):
        """Initialize node instance."""
        self._execution_start: Optional[datetime] = None
        self._current_node_id: Optional[str] = None

    # REQUIRED METHOD (Signature unchanged for compatibility)

    @abstractmethod
    async def execute(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Core execution logic for the node.

        MUST be implemented by all node subclasses.
        SIGNATURE UNCHANGED for backward compatibility.

        Args:
            db: Database session for persistence operations
            context: Execution context with shared state
            input_data: Resolved inputs from UI configuration

        Returns:
            Dictionary containing node outputs
        """
        pass

    # OPTIONAL MANIFEST (Returns dict for compatibility)

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        """
        Returns the node specification for discovery.

        OPTIONAL: Override this to provide node metadata.
        Default implementation returns minimal manifest.

        Returns:
            Dictionary with node metadata (compatible with existing format)
        """
        return {
            "type": cls.node_type,
            "display_name": cls.node_type,
            "icon": "Box",
            "category": "Utilities",
            "description": f"{cls.node_type} node",
            "fields": [],
            "outputs": []
        }

    # OPTIONAL LIFECYCLE HOOKS (New - Opt-in)

    async def validate_inputs(
            self,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validates inputs against the node manifest.

        OPTIONAL: Override for custom validation.
        Default implementation passes through inputs unchanged.

        Args:
            input_data: Raw input data from resolver

        Returns:
            Validated input data (may be modified)

        Raises:
            InputValidationError: If validation fails
        """
        # Default: No validation, pass through
        return input_data

    async def on_before_execute(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            input_data: Dict[str, Any]
    ) -> None:
        """
        Hook called before execute().

        OPTIONAL: Override for setup, metrics, logging.
        """
        self._execution_start = datetime.now(timezone.utc)
        logger.debug(f"Node execution starting: {self.node_type}")

    async def on_after_execute(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            input_data: Dict[str, Any],
            output_data: Dict[str, Any]
    ) -> None:
        """
        Hook called after successful execute().

        OPTIONAL: Override for metrics, cleanup, audit.
        """
        if self._execution_start:
            duration = (datetime.now(timezone.utc) - self._execution_start).total_seconds()
            logger.debug(f"Node execution completed: {self.node_type} ({duration:.2f}s)")

    async def on_error(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            error: Exception
    ) -> None:
        """
        Hook called when execute() raises an exception.

        OPTIONAL: Override for error handling, alerting.
        """
        logger.error(f"Node execution failed: {self.node_type} - {error}")

    async def cleanup(self) -> None:
        """
        Hook for releasing resources.

        OPTIONAL: Override for cleanup logic.
        """
        self._execution_start = None
        self._current_node_id = None

    # ENHANCED EXECUTION (New - Use for new nodes)

    async def run(
            self,
            db: AsyncSession,
            context: 'ExecutionContext',
            input_data: Dict[str, Any],
            node_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete execution lifecycle with all hooks.

        NEW METHOD: Use this for enhanced execution with:
        - Input validation
        - Lifecycle hooks
        - Error wrapping

        For backward compatibility, the executor can still call
        execute() directly for existing nodes.

        Args:
            db: Database session
            context: Execution context
            input_data: Raw input data (will be validated)
            node_id: Optional node ID for error context

        Returns:
            Node output dictionary
        """
        self._current_node_id = node_id

        try:
            # Phase 1: Validation (optional)
            validated_input = await self.validate_inputs(input_data)

            # Phase 2: Pre-execution hook
            await self.on_before_execute(db, context, validated_input)

            # Phase 3: Core execution
            output = await self.execute(db, context, validated_input)

            # Phase 4: Post-execution hook
            await self.on_after_execute(db, context, validated_input, output)

            return output

        except NodeExecutionError:
            # Re-raise typed errors
            raise
        except Exception as e:
            # Wrap unexpected errors
            await self.on_error(db, context, e)
            raise NodeExecutionError(
                message=str(e),
                node_type=self.node_type,
                node_id=node_id,
                retryable=True,
                details={"original_error": type(e).__name__}
            )
        finally:
            await self.cleanup()

    # HELPER METHODS FOR SUBCLASSES

    def _validate_required_fields(
            self,
            input_data: Dict[str, Any],
            required_fields: List[str]
    ) -> List[str]:
        """
        Helper to check required fields.

        Returns list of missing field names.
        """
        missing = []
        for field in required_fields:
            value = input_data.get(field)
            if value is None or value == "":
                missing.append(field)
        return missing

    def _coerce_number(self, value: Any, default: float = 0) -> float:
        """Helper to safely convert to number."""
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _coerce_boolean(self, value: Any, default: bool = False) -> bool:
        """Helper to safely convert to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return default

    def _coerce_list(self, value: Any) -> List[Any]:
        """Helper to ensure value is a list."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [v.strip() for v in value.split(',') if v.strip()]
        if value is None:
            return []
        return [value]


# HELPER FUNCTIONS FOR NEW NODE DEVELOPMENT

def create_field(
        name: str,
        label: str,
        field_type: str,
        required: bool = False,
        default: Any = None,
        **kwargs
) -> Dict[str, Any]:
    """
    Helper function for creating field definitions in manifests.

    Example:
        create_field("api_key", "API Key", "password", required=True)
    """
    field = {
        "name": name,
        "label": label,
        "type": field_type,
        "required": required
    }

    if default is not None:
        field["default"] = default

    field.update(kwargs)
    return field


def create_manifest(
        node_type: str,
        display_name: str,
        icon: str,
        category: str,
        description: str,
        fields: List[Dict[str, Any]],
        outputs: List[str],
        **kwargs
) -> Dict[str, Any]:
    """
    Helper function for creating node manifests.

    Example:
        create_manifest(
            node_type="myNode",
            display_name="My Node",
            icon="Star",
            category="Utilities",
            description="Does something",
            fields=[create_field("input", "Input", "text")],
            outputs=["result"]
        )
    """
    manifest = {
        "type": node_type,
        "display_name": display_name,
        "icon": icon,
        "category": category,
        "description": description,
        "fields": fields,
        "outputs": outputs
    }

    manifest.update(kwargs)
    return manifest