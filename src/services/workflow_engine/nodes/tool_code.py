import ast
import asyncio
import json
import os
import sys
import tempfile
import signal
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from loguru import logger

try:
    import resource
except ImportError:
    resource = None  # Windows compatibility

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.workflow_engine.nodes.base import (
    BaseNode, NodeManifest, NodeCategory, NodeExecutionError,
    FieldDefinition, FieldType, create_manifest, define_field
)
from src.core.sandbox import (
    SandboxManager, SandboxResult, DockerSandboxConfig, SandboxMode,
    get_sandbox_manager
)


class SandboxViolation(Enum):
    """Categories of sandbox security violations."""
    FORBIDDEN_IMPORT = auto()
    FORBIDDEN_BUILTIN = auto()
    FORBIDDEN_ATTRIBUTE = auto()
    FORBIDDEN_SYNTAX = auto()
    RESOURCE_LIMIT = auto()
    TIMEOUT = auto()
    OUTPUT_SIZE = auto()


@dataclass
class SandboxConfig:
    """
    Configuration for sandbox execution limits.
    All limits are conservative defaults that can be overridden.
    """
    timeout_seconds: float = 5.0
    max_memory_mb: int = 128
    max_output_bytes: int = 1_000_000  # 1MB
    max_cpu_seconds: int = 5
    allowed_modules: Set[str] = field(default_factory=lambda: {
        # Safe standard library modules
        'json', 'math', 'random', 'string', 'datetime', 'collections',
        'itertools', 'functools', 'operator', 're', 'typing',
        'decimal', 'fractions', 'statistics', 'copy', 'enum',
        'dataclasses', 'abc', 'numbers', 'uuid', 'hashlib',
        'base64', 'urllib.parse', 'html', 'textwrap'
    })
    forbidden_builtins: Set[str] = field(default_factory=lambda: {
        'eval', 'exec', 'compile', 'open', 'input', '__import__',
        'globals', 'locals', 'vars', 'dir', 'getattr', 'setattr',
        'delattr', 'hasattr', 'type', 'isinstance', 'issubclass',
        'callable', 'classmethod', 'staticmethod', 'property',
        'super', 'object', 'memoryview', 'bytearray', 'breakpoint'
    })
    forbidden_attributes: Set[str] = field(default_factory=lambda: {
        '__class__', '__bases__', '__subclasses__', '__mro__',
        '__code__', '__globals__', '__builtins__', '__dict__',
        '__closure__', '__func__', '__self__', '__module__',
        '__qualname__', '__annotations__', '__wrapped__'
    })


class CodeAnalyzer(ast.NodeVisitor):
    """
    Static code analyzer that detects security violations before execution.

    Uses AST walking to identify:
    - Forbidden imports
    - Dangerous attribute access
    - Eval/exec calls
    - Dunder method access
    """

    def __init__(self, config: SandboxConfig):
        self.config = config
        self.violations: List[Tuple[SandboxViolation, str, int]] = []

    def analyze(self, code: str) -> List[Tuple[SandboxViolation, str, int]]:
        """
        Analyzes code and returns list of violations.

        Returns:
            List of (violation_type, message, line_number) tuples
        """
        self.violations = []

        try:
            tree = ast.parse(code)
            self.visit(tree)
        except SyntaxError as e:
            self.violations.append((
                SandboxViolation.FORBIDDEN_SYNTAX,
                f"Syntax error: {e.msg}",
                e.lineno or 0
            ))

        return self.violations

    def visit_Import(self, node: ast.Import):
        """Check regular imports."""
        for alias in node.names:
            module = alias.name.split('.')[0]
            if module not in self.config.allowed_modules:
                self.violations.append((
                    SandboxViolation.FORBIDDEN_IMPORT,
                    f"Import of '{alias.name}' is not allowed",
                    node.lineno
                ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Check from-imports."""
        if node.module:
            module = node.module.split('.')[0]
            if module not in self.config.allowed_modules:
                self.violations.append((
                    SandboxViolation.FORBIDDEN_IMPORT,
                    f"Import from '{node.module}' is not allowed",
                    node.lineno
                ))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        """Check attribute access for dunder methods."""
        if node.attr in self.config.forbidden_attributes:
            self.violations.append((
                SandboxViolation.FORBIDDEN_ATTRIBUTE,
                f"Access to '{node.attr}' is forbidden",
                node.lineno
            ))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Check function calls for forbidden builtins."""
        if isinstance(node.func, ast.Name):
            if node.func.id in self.config.forbidden_builtins:
                self.violations.append((
                    SandboxViolation.FORBIDDEN_BUILTIN,
                    f"Call to '{node.func.id}' is forbidden",
                    node.lineno
                ))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        """Check for forbidden name access."""
        if node.id.startswith('__') and node.id.endswith('__'):
            self.violations.append((
                SandboxViolation.FORBIDDEN_ATTRIBUTE,
                f"Access to dunder '{node.id}' is forbidden",
                node.lineno
            ))
        self.generic_visit(node)


def create_safe_builtins() -> Dict[str, Any]:
    """
    Creates a restricted builtins dictionary.
    Only includes safe functions that can't escape the sandbox.
    """
    import builtins

    # Whitelist of safe builtins
    safe_names = {
        # Types
        'bool', 'int', 'float', 'str', 'list', 'dict', 'set', 'tuple',
        'frozenset', 'bytes', 'complex',

        # Functions
        'abs', 'all', 'any', 'ascii', 'bin', 'chr', 'divmod',
        'enumerate', 'filter', 'format', 'hex', 'id', 'iter',
        'len', 'map', 'max', 'min', 'next', 'oct', 'ord', 'pow',
        'print', 'range', 'repr', 'reversed', 'round', 'slice',
        'sorted', 'sum', 'zip',

        # Constants
        'True', 'False', 'None',

        # Exceptions (for error handling)
        'Exception', 'ValueError', 'TypeError', 'KeyError',
        'IndexError', 'AttributeError', 'RuntimeError', 'StopIteration',
        'ZeroDivisionError', 'OverflowError', 'AssertionError'
    }

    return {
        name: getattr(builtins, name)
        for name in safe_names
        if hasattr(builtins, name)
    }


def create_wrapper_script(
        user_code: str,
        inputs: Dict[str, Any],
        config: SandboxConfig
) -> str:
    """
    Creates the isolated execution wrapper script.

    The wrapper:
    1. Sets resource limits
    2. Creates restricted execution environment
    3. Captures output safely
    4. Handles errors gracefully
    """
    inputs_json = json.dumps(inputs)
    allowed_modules = json.dumps(list(config.allowed_modules))

    return f'''
import json
import sys
import resource

# PHASE 1: Resource Limits (Defense Layer)

# Memory limit
mem_limit = {config.max_memory_mb} * 1024 * 1024
try:
    resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
except (ValueError, resource.error):
    pass  # May not be available on all systems

# CPU time limit
try:
    resource.setrlimit(resource.RLIMIT_CPU, ({config.max_cpu_seconds}, {config.max_cpu_seconds}))
except (ValueError, resource.error):
    pass

# PHASE 2: Safe Import System

ALLOWED_MODULES = set({allowed_modules})
_original_import = __builtins__.__dict__.get('__import__', __import__)

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Restricted import that only allows whitelisted modules."""
    base_module = name.split('.')[0]
    if base_module not in ALLOWED_MODULES:
        raise ImportError(f"Module '{{name}}' is not allowed in sandbox")
    return _original_import(name, globals, locals, fromlist, level)

# PHASE 3: Execution Environment

def execute_user_code():
    """Executes user code in a restricted namespace."""

    # Safe builtins only
    safe_builtins = {{
        'bool': bool, 'int': int, 'float': float, 'str': str,
        'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
        'frozenset': frozenset, 'bytes': bytes, 'complex': complex,
        'abs': abs, 'all': all, 'any': any, 'ascii': ascii,
        'bin': bin, 'chr': chr, 'divmod': divmod, 'enumerate': enumerate,
        'filter': filter, 'format': format, 'hex': hex, 'id': id,
        'iter': iter, 'len': len, 'map': map, 'max': max, 'min': min,
        'next': next, 'oct': oct, 'ord': ord, 'pow': pow, 'print': print,
        'range': range, 'repr': repr, 'reversed': reversed, 'round': round,
        'slice': slice, 'sorted': sorted, 'sum': sum, 'zip': zip,
        'True': True, 'False': False, 'None': None,
        'Exception': Exception, 'ValueError': ValueError,
        'TypeError': TypeError, 'KeyError': KeyError,
        'IndexError': IndexError, 'RuntimeError': RuntimeError,
        'ZeroDivisionError': ZeroDivisionError,
        '__import__': _safe_import
    }}

    # Create isolated namespace
    inputs = {inputs_json}
    namespace = {{
        '__builtins__': safe_builtins,
        'inputs': inputs,
        'result': None
    }}

    # User code to execute
    user_code = {repr(user_code)}

    try:
        exec(user_code, namespace, namespace)
        return namespace.get('result')
    except Exception as e:
        return {{"__error__": str(e), "__type__": type(e).__name__}}

# PHASE 4: Main Execution

if __name__ == "__main__":
    try:
        result = execute_user_code()
        output = {{"success": True, "result": result}}
    except Exception as e:
        output = {{"success": False, "error": str(e), "error_type": type(e).__name__}}

    # Output as JSON (truncated if too large)
    output_json = json.dumps(output)
    if len(output_json) > {config.max_output_bytes}:
        output_json = json.dumps({{
            "success": False,
            "error": "Output exceeded maximum size limit",
            "error_type": "OutputSizeError"
        }})

    print(output_json)
'''


class CodeExecutionNode(BaseNode):
    """
    Secure Python Sandbox Node.

    Executes user-provided Python code in a completely isolated
    Docker container (production) or subprocess (fallback).

    Security Layers:
    1. Static code analysis (AST-based detection of dangerous patterns)
    2. Docker container isolation (namespaces, cgroups, seccomp)
    3. No network access (network=none)
    4. Read-only filesystem with tmpfs for writes
    5. Memory and CPU limits
    6. Non-root user execution
    7. Capability dropping
    8. Output size limits

    Execution Modes:
    - Docker (production): Full container isolation
    - Subprocess (fallback): Resource-limited subprocess
    - Disabled: No execution (returns error)

    Usage:
        The code has access to:
        - `inputs`: Dictionary of input variables
        - `result`: Set this to return data

        Example user code:
            data = inputs.get('numbers', [])
            result = sum(data) / len(data) if data else 0
    """

    node_type = "codeNode"

    def __init__(self):
        super().__init__()
        self.config = SandboxConfig()
        self.analyzer = CodeAnalyzer(self.config)
        self._sandbox_manager: Optional[SandboxManager] = None

    @classmethod
    def get_manifest(cls) -> NodeManifest:
        return create_manifest(
            node_type=cls.node_type,
            display_name="Python Sandbox",
            icon="Code2",
            category=NodeCategory.INTELLIGENCE,
            description="Execute secure, isolated Python code for data transformation.",
            fields=[
                define_field(
                    name="code",
                    label="Python Script",
                    field_type=FieldType.CODE_EDITOR,
                    required=True,
                    language="python",
                    placeholder="# Access inputs via 'inputs' dict\n# Set 'result' variable to return data\nresult = inputs.get('value', 0) * 2",
                    helper="Available: inputs (dict), result (set to output)"
                ),
                define_field(
                    name="inputs",
                    label="Input Variables",
                    field_type=FieldType.JSON_EDITOR,
                    default={},
                    placeholder='{"numbers": [1, 2, 3]}',
                    helper="JSON object passed as 'inputs' to your code"
                ),
                define_field(
                    name="timeout",
                    label="Timeout (seconds)",
                    field_type=FieldType.NUMBER,
                    default=5,
                    min_value=1,
                    max_value=30
                )
            ],
            outputs=["result", "execution_time_ms", "status"],
            timeout_seconds=30,
            max_retries=1  # Code errors usually aren't transient
        )

    async def execute(
            self,
            db: AsyncSession,
            context: Any,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes user code in a secure Docker sandbox.

        Execution Pipeline:
        1. Extract and validate inputs
        2. Static code analysis (detect dangerous patterns)
        3. Execute in Docker container (or subprocess fallback)
        4. Parse and validate output

        Security is enforced at multiple layers:
        - Pre-execution: AST analysis blocks dangerous patterns
        - Execution: Docker isolation prevents system access
        - Post-execution: Output validation and size limits
        """
        user_code = input_data.get("code", "")
        code_inputs = input_data.get("inputs", {})
        timeout = float(input_data.get("timeout", self.config.timeout_seconds))

        if not user_code or not user_code.strip():
            raise NodeExecutionError(
                message="Code input is required",
                node_type=self.node_type,
                retryable=False
            )

        # Ensure inputs is a dictionary
        if isinstance(code_inputs, str):
            try:
                code_inputs = json.loads(code_inputs)
            except json.JSONDecodeError:
                code_inputs = {}

        # PHASE 1: Static Analysis (Defense Layer 1)
        # Catches obvious dangerous patterns before any execution

        violations = self.analyzer.analyze(user_code)
        if violations:
            error_messages = [
                f"Line {line}: {msg}"
                for vtype, msg, line in violations
            ]
            raise NodeExecutionError(
                message=f"Code security violations detected:\n" + "\n".join(error_messages),
                node_type=self.node_type,
                retryable=False,
                details={"violations": [v[1] for v in violations]}
            )

        # PHASE 2: Docker Sandbox Execution (Defense Layer 2)
        # Full container isolation with resource limits

        try:
            sandbox = await get_sandbox_manager()
            sandbox_result: SandboxResult = await sandbox.execute(
                code=user_code,
                inputs=code_inputs,
                timeout=timeout
            )

            logger.debug(
                f"Sandbox execution completed: "
                f"success={sandbox_result.success}, "
                f"time={sandbox_result.execution_time_ms}ms, "
                f"memory={sandbox_result.memory_used_mb:.1f}MB"
            )

        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            raise NodeExecutionError(
                message=f"Sandbox execution failed: {str(e)}",
                node_type=self.node_type,
                retryable=False,
                details={"error_type": type(e).__name__}
            )

        # PHASE 3: Handle Result

        if not sandbox_result.success:
            error_msg = sandbox_result.error or "Unknown execution error"
            error_type = sandbox_result.error_type or "RuntimeError"

            # Provide helpful error messages
            if error_type == "TimeoutError":
                raise NodeExecutionError(
                    message=f"Execution timed out after {timeout} seconds. "
                            f"Consider optimizing your code or increasing the timeout.",
                    node_type=self.node_type,
                    retryable=False,
                    details={"timeout_seconds": timeout}
                )
            elif error_type == "ImportError":
                raise NodeExecutionError(
                    message=f"Import error: {error_msg}. "
                            f"Only standard library modules are allowed.",
                    node_type=self.node_type,
                    retryable=False,
                    details={"allowed_modules": list(self.config.allowed_modules)}
                )
            elif error_type == "SandboxUnavailable":
                raise NodeExecutionError(
                    message="Code execution sandbox is not available. "
                            "Please contact support.",
                    node_type=self.node_type,
                    retryable=True  # Might be transient
                )
            else:
                raise NodeExecutionError(
                    message=f"{error_type}: {error_msg}",
                    node_type=self.node_type,
                    retryable=False,
                    details={
                        "error_type": error_type,
                        "stderr": sandbox_result.stderr[:500] if sandbox_result.stderr else None
                    }
                )

        # PHASE 4: Validate Result

        result = sandbox_result.result

        # Check for internal error marker (shouldn't happen with Docker sandbox)
        if isinstance(result, dict) and "__error__" in result:
            raise NodeExecutionError(
                message=f"{result.get('__type__', 'Error')}: {result['__error__']}",
                node_type=self.node_type,
                retryable=False
            )

        return {
            "status": "success",
            "result": result,
            "execution_time_ms": sandbox_result.execution_time_ms,
            "memory_used_mb": round(sandbox_result.memory_used_mb, 2),
            "sandbox_mode": "docker" if sandbox_result.container_id else "subprocess"
        }

    async def validate_inputs(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extended validation for code inputs."""
        validated = await super().validate_inputs(input_data)

        # Additional validation: code must be a string
        code = validated.get("code", "")
        if not isinstance(code, str):
            from nodes.base import InputValidationError
            raise InputValidationError(
                message="Code must be a string",
                node_type=self.node_type,
                invalid_fields=["code"]
            )

        return validated