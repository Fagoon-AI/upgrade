"""
Docker-based Code Execution Sandbox.

Provides secure, isolated code execution using Docker containers with:
- Complete process isolation (namespaces, cgroups)
- Network isolation (no network access by default)
- Filesystem isolation (read-only root, tmpfs for writes)
- Resource limits (CPU, memory, PIDs)
- Automatic cleanup and timeout enforcement
- Non-root execution

Security Layers:
1. Static code analysis (before container)
2. Container isolation (Docker)
3. Resource limits (cgroups)
4. Network isolation (no network)
5. Filesystem isolation (read-only + tmpfs)
6. User isolation (non-root)
7. Seccomp profiles (syscall filtering)
8. Capability dropping (no privileged ops)
"""

import asyncio
import json
import os
import tempfile
import hashlib
import shutil
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import uuid

from loguru import logger

try:
    import docker
    from docker.errors import ContainerError, ImageNotFound, APIError
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None


# ============================================================
# CONFIGURATION
# ============================================================

class SandboxMode(str, Enum):
    """Sandbox execution modes."""
    DOCKER = "docker"           # Full Docker isolation (production)
    SUBPROCESS = "subprocess"   # Subprocess with resource limits (fallback)
    DISABLED = "disabled"       # No sandbox (development only, dangerous)


@dataclass
class DockerSandboxConfig:
    """
    Configuration for Docker sandbox execution.

    All limits are conservative defaults suitable for untrusted code.
    """
    # Execution limits
    timeout_seconds: float = 10.0
    max_memory_mb: int = 128
    max_cpu_percent: int = 50  # 50% of one CPU
    max_pids: int = 50         # Maximum processes
    max_output_bytes: int = 1_000_000  # 1MB

    # Container configuration
    image_name: str = "workflow-sandbox-python"
    image_tag: str = "latest"
    network_mode: str = "none"  # No network access
    read_only: bool = True      # Read-only root filesystem
    tmpfs_size_mb: int = 64     # Size of writable tmpfs

    # Security options
    drop_capabilities: bool = True
    no_new_privileges: bool = True
    seccomp_profile: str = "default"  # Or path to custom profile
    user: str = "sandbox"       # Non-root user in container

    # Python-specific
    allowed_modules: List[str] = field(default_factory=lambda: [
        'json', 'math', 'random', 'string', 'datetime', 'collections',
        'itertools', 'functools', 'operator', 're', 'typing',
        'decimal', 'fractions', 'statistics', 'copy', 'enum',
        'dataclasses', 'abc', 'numbers', 'uuid', 'hashlib',
        'base64', 'urllib.parse', 'html', 'textwrap', 'time'
    ])

    # Cleanup
    remove_container: bool = True
    container_prefix: str = "sandbox-"

    @property
    def full_image_name(self) -> str:
        return f"{self.image_name}:{self.image_tag}"

    @property
    def memory_limit(self) -> str:
        return f"{self.max_memory_mb}m"

    @property
    def cpu_period(self) -> int:
        return 100000  # 100ms

    @property
    def cpu_quota(self) -> int:
        return int(self.cpu_period * self.max_cpu_percent / 100)


@dataclass
class SandboxResult:
    """Result from sandbox execution."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_time_ms: int = 0
    memory_used_mb: float = 0
    container_id: Optional[str] = None
    stdout: str = ""
    stderr: str = ""


# ============================================================
# DOCKER SANDBOX EXECUTOR
# ============================================================

class DockerSandboxExecutor:
    """
    Executes code in isolated Docker containers.

    Security Features:
    - No network access
    - Read-only filesystem with tmpfs for /tmp
    - Memory and CPU limits via cgroups
    - PID limits to prevent fork bombs
    - Dropped capabilities
    - Non-root user
    - Automatic cleanup

    Usage:
        executor = DockerSandboxExecutor()
        result = await executor.execute(code, inputs, timeout=5.0)
    """

    def __init__(self, config: Optional[DockerSandboxConfig] = None):
        self.config = config or DockerSandboxConfig()
        self._client: Optional[docker.DockerClient] = None
        self._initialized = False
        self._image_exists = False

    async def initialize(self) -> bool:
        """Initialize Docker client and verify image exists."""
        if self._initialized:
            return self._image_exists

        if not DOCKER_AVAILABLE:
            logger.warning("Docker package not installed, sandbox unavailable")
            self._initialized = True
            return False

        try:
            # Create Docker client
            self._client = docker.from_env()

            # Verify Docker is accessible
            self._client.ping()
            logger.info("Docker client connected")

            # Check if sandbox image exists
            try:
                self._client.images.get(self.config.full_image_name)
                self._image_exists = True
                logger.info(f"Sandbox image found: {self.config.full_image_name}")
            except ImageNotFound:
                logger.warning(
                    f"Sandbox image not found: {self.config.full_image_name}. "
                    "Run 'docker build -t workflow-sandbox-python:latest -f docker/Dockerfile.sandbox .' "
                    "to build it."
                )
                self._image_exists = False

            self._initialized = True
            return self._image_exists

        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self._initialized = True
            self._image_exists = False
            return False

    def _create_execution_script(
        self,
        user_code: str,
        inputs: Dict[str, Any]
    ) -> str:
        """Creates the Python script to execute inside the container."""
        inputs_json = json.dumps(inputs)
        allowed_modules = json.dumps(self.config.allowed_modules)

        return f'''#!/usr/bin/env python3
"""Sandbox execution wrapper - auto-generated, do not edit."""

import json
import sys
import traceback

# Allowed modules whitelist
ALLOWED_MODULES = set({allowed_modules})

# Safe import function
_original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Restricted import that only allows whitelisted modules."""
    base_module = name.split('.')[0]
    if base_module not in ALLOWED_MODULES:
        raise ImportError(f"Module '{{name}}' is not allowed in sandbox")
    return _original_import(name, globals, locals, fromlist, level)

# Safe builtins
SAFE_BUILTINS = {{
    # Types
    'bool': bool, 'int': int, 'float': float, 'str': str,
    'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
    'frozenset': frozenset, 'bytes': bytes, 'complex': complex,

    # Functions
    'abs': abs, 'all': all, 'any': any, 'ascii': ascii,
    'bin': bin, 'chr': chr, 'divmod': divmod, 'enumerate': enumerate,
    'filter': filter, 'format': format, 'hex': hex, 'id': id,
    'iter': iter, 'len': len, 'map': map, 'max': max, 'min': min,
    'next': next, 'oct': oct, 'ord': ord, 'pow': pow, 'print': print,
    'range': range, 'repr': repr, 'reversed': reversed, 'round': round,
    'slice': slice, 'sorted': sorted, 'sum': sum, 'zip': zip,
    'isinstance': isinstance, 'type': type, 'hash': hash,

    # Constants
    'True': True, 'False': False, 'None': None,

    # Exceptions
    'Exception': Exception, 'ValueError': ValueError,
    'TypeError': TypeError, 'KeyError': KeyError,
    'IndexError': IndexError, 'AttributeError': AttributeError,
    'RuntimeError': RuntimeError, 'StopIteration': StopIteration,
    'ZeroDivisionError': ZeroDivisionError, 'OverflowError': OverflowError,
    'AssertionError': AssertionError, 'ImportError': ImportError,

    # Safe import
    '__import__': _safe_import,
}}

def execute():
    """Execute user code in isolated namespace."""
    inputs = {inputs_json}

    namespace = {{
        '__builtins__': SAFE_BUILTINS,
        '__name__': '__sandbox__',
        'inputs': inputs,
        'result': None,
    }}

    user_code = {repr(user_code)}

    try:
        exec(user_code, namespace, namespace)
        return {{"success": True, "result": namespace.get('result')}}
    except Exception as e:
        return {{
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}

if __name__ == "__main__":
    try:
        output = execute()
    except Exception as e:
        output = {{
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }}

    # Output as JSON
    output_json = json.dumps(output, default=str)

    # Truncate if too large
    max_size = {self.config.max_output_bytes}
    if len(output_json) > max_size:
        output_json = json.dumps({{
            "success": False,
            "error": f"Output exceeded maximum size ({{max_size}} bytes)",
            "error_type": "OutputSizeError"
        }})

    print(output_json)
'''

    async def execute(
        self,
        code: str,
        inputs: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> SandboxResult:
        """
        Execute code in a Docker container.

        Args:
            code: Python code to execute
            inputs: Input variables available as 'inputs' dict
            timeout: Execution timeout in seconds

        Returns:
            SandboxResult with execution outcome
        """
        timeout = timeout or self.config.timeout_seconds
        start_time = datetime.now(timezone.utc)

        # Ensure initialized
        if not await self.initialize():
            return SandboxResult(
                success=False,
                error="Docker sandbox not available",
                error_type="SandboxUnavailable"
            )

        container = None
        temp_dir = None

        try:
            # Create temporary directory for script
            temp_dir = tempfile.mkdtemp(prefix="sandbox-")
            script_path = Path(temp_dir) / "script.py"

            # Write execution script
            script_content = self._create_execution_script(code, inputs)
            script_path.write_text(script_content, encoding='utf-8')
            os.chmod(script_path, 0o444)  # Read-only

            # Generate unique container name
            container_name = f"{self.config.container_prefix}{uuid.uuid4().hex[:12]}"

            # Build container configuration
            container_config = {
                'image': self.config.full_image_name,
                'name': container_name,
                'command': ['python3', '/sandbox/script.py'],
                'volumes': {
                    temp_dir: {
                        'bind': '/sandbox',
                        'mode': 'ro'  # Read-only mount
                    }
                },
                'working_dir': '/tmp',
                'user': self.config.user,
                'network_mode': self.config.network_mode,
                'read_only': self.config.read_only,
                'mem_limit': self.config.memory_limit,
                'memswap_limit': self.config.memory_limit,  # No swap
                'cpu_period': self.config.cpu_period,
                'cpu_quota': self.config.cpu_quota,
                'pids_limit': self.config.max_pids,
                'detach': True,
                'auto_remove': False,  # We'll remove after getting logs
                'environment': {
                    'PYTHONDONTWRITEBYTECODE': '1',
                    'PYTHONUNBUFFERED': '1',
                },
            }

            # Add tmpfs for writable /tmp
            container_config['tmpfs'] = {
                '/tmp': f'size={self.config.tmpfs_size_mb}m,mode=1777'
            }

            # Security options
            if self.config.drop_capabilities:
                container_config['cap_drop'] = ['ALL']

            if self.config.no_new_privileges:
                container_config['security_opt'] = ['no-new-privileges:true']

            # Create and start container
            container = self._client.containers.create(**container_config)
            container.start()

            logger.debug(f"Started sandbox container: {container_name}")

            # Wait for completion with timeout
            try:
                exit_code = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: container.wait(timeout=timeout)
                    ),
                    timeout=timeout + 2  # Small buffer for container overhead
                )
                exit_code = exit_code.get('StatusCode', -1)

            except asyncio.TimeoutError:
                # Kill container
                try:
                    container.kill()
                except Exception:
                    pass

                return SandboxResult(
                    success=False,
                    error=f"Execution timed out after {timeout} seconds",
                    error_type="TimeoutError",
                    execution_time_ms=int(timeout * 1000),
                    container_id=container.id
                )

            # Get output
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace')

            execution_time_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            # Get memory stats if available
            memory_used_mb = 0.0
            try:
                stats = container.stats(stream=False)
                memory_used = stats.get('memory_stats', {}).get('usage', 0)
                memory_used_mb = memory_used / (1024 * 1024)
            except Exception:
                pass

            # Parse output
            if exit_code != 0:
                return SandboxResult(
                    success=False,
                    error=f"Container exited with code {exit_code}: {stderr.strip() or stdout.strip()}",
                    error_type="ContainerError",
                    execution_time_ms=execution_time_ms,
                    memory_used_mb=memory_used_mb,
                    container_id=container.id,
                    stdout=stdout,
                    stderr=stderr
                )

            # Parse JSON output
            try:
                output_data = json.loads(stdout.strip())
            except json.JSONDecodeError as e:
                return SandboxResult(
                    success=False,
                    error=f"Failed to parse output: {e}",
                    error_type="OutputParseError",
                    execution_time_ms=execution_time_ms,
                    stdout=stdout[:1000],
                    stderr=stderr
                )

            # Check execution result
            if not output_data.get('success', False):
                return SandboxResult(
                    success=False,
                    error=output_data.get('error', 'Unknown error'),
                    error_type=output_data.get('error_type', 'RuntimeError'),
                    execution_time_ms=execution_time_ms,
                    memory_used_mb=memory_used_mb,
                    container_id=container.id,
                    stdout=stdout,
                    stderr=stderr
                )

            return SandboxResult(
                success=True,
                result=output_data.get('result'),
                execution_time_ms=execution_time_ms,
                memory_used_mb=memory_used_mb,
                container_id=container.id,
                stdout=stdout,
                stderr=stderr
            )

        except docker.errors.ImageNotFound:
            return SandboxResult(
                success=False,
                error=f"Sandbox image not found: {self.config.full_image_name}",
                error_type="ImageNotFound"
            )

        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {e}")
            return SandboxResult(
                success=False,
                error=f"Docker error: {str(e)}",
                error_type="DockerAPIError"
            )

        except Exception as e:
            logger.error(f"Sandbox execution error: {e}")
            return SandboxResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__
            )

        finally:
            # Cleanup container
            if container and self.config.remove_container:
                try:
                    container.remove(force=True)
                except Exception as e:
                    logger.warning(f"Failed to remove container: {e}")

            # Cleanup temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to remove temp dir: {e}")

    async def cleanup_stale_containers(self) -> int:
        """Remove any stale sandbox containers."""
        if not self._client:
            return 0

        removed = 0
        try:
            containers = self._client.containers.list(
                all=True,
                filters={'name': self.config.container_prefix}
            )

            for container in containers:
                try:
                    container.remove(force=True)
                    removed += 1
                except Exception as e:
                    logger.warning(f"Failed to remove stale container {container.id}: {e}")

            if removed:
                logger.info(f"Cleaned up {removed} stale sandbox containers")

        except Exception as e:
            logger.error(f"Failed to cleanup containers: {e}")

        return removed

    async def health_check(self) -> Dict[str, Any]:
        """Check sandbox health status."""
        result = {
            'available': False,
            'docker_connected': False,
            'image_exists': False,
            'image_name': self.config.full_image_name,
        }

        if not DOCKER_AVAILABLE:
            result['error'] = 'Docker package not installed'
            return result

        try:
            if not self._client:
                self._client = docker.from_env()

            # Check Docker connection
            self._client.ping()
            result['docker_connected'] = True

            # Check image
            try:
                image = self._client.images.get(self.config.full_image_name)
                result['image_exists'] = True
                result['image_id'] = image.id[:12]
                result['image_size_mb'] = round(image.attrs.get('Size', 0) / (1024 * 1024), 1)
            except ImageNotFound:
                result['image_exists'] = False

            result['available'] = result['docker_connected'] and result['image_exists']

        except Exception as e:
            result['error'] = str(e)

        return result


# ============================================================
# SUBPROCESS FALLBACK EXECUTOR
# ============================================================

class SubprocessSandboxExecutor:
    """
    Fallback sandbox using subprocess with resource limits.

    Less secure than Docker but provides some isolation:
    - Separate process
    - Resource limits (where supported)
    - Restricted environment

    WARNING: Not suitable for truly untrusted code!
    """

    def __init__(self, config: Optional[DockerSandboxConfig] = None):
        self.config = config or DockerSandboxConfig()

    async def execute(
        self,
        code: str,
        inputs: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> SandboxResult:
        """Execute code in a subprocess with resource limits."""
        import sys
        import resource

        timeout = timeout or self.config.timeout_seconds
        start_time = datetime.now(timezone.utc)

        # Create execution script
        script = self._create_script(code, inputs)

        # Write to temp file
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(script)
                temp_file = f.name

            # Execute in subprocess
            process = await asyncio.create_subprocess_exec(
                sys.executable, temp_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    'PATH': os.environ.get('PATH', ''),
                    'PYTHONPATH': '',
                    'HOME': '/tmp',
                    'PYTHONDONTWRITEBYTECODE': '1',
                },
                preexec_fn=self._set_limits if hasattr(resource, 'setrlimit') else None
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass

                return SandboxResult(
                    success=False,
                    error=f"Execution timed out after {timeout} seconds",
                    error_type="TimeoutError",
                    execution_time_ms=int(timeout * 1000)
                )

            execution_time_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            stdout_text = stdout.decode('utf-8', errors='replace').strip()
            stderr_text = stderr.decode('utf-8', errors='replace').strip()

            if process.returncode != 0:
                return SandboxResult(
                    success=False,
                    error=stderr_text or f"Process exited with code {process.returncode}",
                    error_type="ProcessError",
                    execution_time_ms=execution_time_ms,
                    stdout=stdout_text,
                    stderr=stderr_text
                )

            # Parse output
            try:
                output_data = json.loads(stdout_text)
            except json.JSONDecodeError as e:
                return SandboxResult(
                    success=False,
                    error=f"Failed to parse output: {e}",
                    error_type="OutputParseError",
                    execution_time_ms=execution_time_ms,
                    stdout=stdout_text[:1000],
                    stderr=stderr_text
                )

            if not output_data.get('success', False):
                return SandboxResult(
                    success=False,
                    error=output_data.get('error', 'Unknown error'),
                    error_type=output_data.get('error_type', 'RuntimeError'),
                    execution_time_ms=execution_time_ms,
                    stdout=stdout_text,
                    stderr=stderr_text
                )

            return SandboxResult(
                success=True,
                result=output_data.get('result'),
                execution_time_ms=execution_time_ms,
                stdout=stdout_text,
                stderr=stderr_text
            )

        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def _set_limits(self):
        """Set resource limits for subprocess (Unix only)."""
        import resource

        # Memory limit
        mem_bytes = self.config.max_memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, resource.error):
            pass

        # CPU time limit
        try:
            cpu_seconds = int(self.config.timeout_seconds) + 1
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        except (ValueError, resource.error):
            pass

        # Prevent core dumps
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, resource.error):
            pass

    def _create_script(self, code: str, inputs: Dict[str, Any]) -> str:
        """Create execution script for subprocess."""
        inputs_json = json.dumps(inputs)
        allowed_modules = json.dumps(self.config.allowed_modules)

        return f'''
import json
import sys

ALLOWED_MODULES = set({allowed_modules})
_original_import = __import__

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    base_module = name.split('.')[0]
    if base_module not in ALLOWED_MODULES:
        raise ImportError(f"Module '{{name}}' is not allowed")
    return _original_import(name, globals, locals, fromlist, level)

SAFE_BUILTINS = {{
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
    '__import__': _safe_import,
}}

def execute():
    inputs = {inputs_json}
    namespace = {{
        '__builtins__': SAFE_BUILTINS,
        'inputs': inputs,
        'result': None,
    }}

    user_code = {repr(code)}

    try:
        exec(user_code, namespace, namespace)
        return {{"success": True, "result": namespace.get('result')}}
    except Exception as e:
        return {{"success": False, "error": str(e), "error_type": type(e).__name__}}

if __name__ == "__main__":
    try:
        output = execute()
    except Exception as e:
        output = {{"success": False, "error": str(e), "error_type": type(e).__name__}}

    output_json = json.dumps(output, default=str)
    if len(output_json) > {self.config.max_output_bytes}:
        output_json = json.dumps({{"success": False, "error": "Output too large", "error_type": "OutputSizeError"}})
    print(output_json)
'''


# ============================================================
# UNIFIED SANDBOX MANAGER
# ============================================================

class SandboxManager:
    """
    Unified sandbox manager that selects the best available executor.

    Priority:
    1. Docker (most secure)
    2. Subprocess (fallback)
    3. Disabled (development only)
    """

    def __init__(
        self,
        mode: Optional[SandboxMode] = None,
        config: Optional[DockerSandboxConfig] = None
    ):
        self.config = config or DockerSandboxConfig()
        self._mode = mode
        self._docker_executor: Optional[DockerSandboxExecutor] = None
        self._subprocess_executor: Optional[SubprocessSandboxExecutor] = None
        self._initialized = False
        self._active_mode: Optional[SandboxMode] = None

    async def initialize(self) -> SandboxMode:
        """Initialize sandbox and determine available mode."""
        if self._initialized:
            return self._active_mode

        # If mode explicitly set, use it
        if self._mode == SandboxMode.DISABLED:
            logger.warning("Sandbox DISABLED - code execution is NOT secure!")
            self._active_mode = SandboxMode.DISABLED
            self._initialized = True
            return self._active_mode

        # Try Docker first
        if self._mode in (None, SandboxMode.DOCKER):
            self._docker_executor = DockerSandboxExecutor(self.config)
            if await self._docker_executor.initialize():
                self._active_mode = SandboxMode.DOCKER
                logger.info("Sandbox mode: Docker (full isolation)")
                self._initialized = True
                return self._active_mode

        # Fall back to subprocess
        if self._mode in (None, SandboxMode.SUBPROCESS):
            self._subprocess_executor = SubprocessSandboxExecutor(self.config)
            self._active_mode = SandboxMode.SUBPROCESS
            logger.warning(
                "Sandbox mode: Subprocess (limited isolation). "
                "Build Docker image for production security!"
            )
            self._initialized = True
            return self._active_mode

        # No sandbox available
        logger.error("No sandbox available!")
        self._active_mode = SandboxMode.DISABLED
        self._initialized = True
        return self._active_mode

    async def execute(
        self,
        code: str,
        inputs: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> SandboxResult:
        """Execute code using the best available sandbox."""
        await self.initialize()

        if self._active_mode == SandboxMode.DOCKER:
            return await self._docker_executor.execute(code, inputs, timeout)

        elif self._active_mode == SandboxMode.SUBPROCESS:
            return await self._subprocess_executor.execute(code, inputs, timeout)

        else:
            return SandboxResult(
                success=False,
                error="Sandbox is disabled, code execution not allowed",
                error_type="SandboxDisabled"
            )

    async def health_check(self) -> Dict[str, Any]:
        """Get sandbox health status."""
        await self.initialize()

        result = {
            'mode': self._active_mode.value if self._active_mode else 'unknown',
            'config': {
                'timeout_seconds': self.config.timeout_seconds,
                'max_memory_mb': self.config.max_memory_mb,
                'max_cpu_percent': self.config.max_cpu_percent,
                'network_mode': self.config.network_mode,
            }
        }

        if self._docker_executor:
            result['docker'] = await self._docker_executor.health_check()

        return result

    async def cleanup(self) -> None:
        """Cleanup any stale resources."""
        if self._docker_executor:
            await self._docker_executor.cleanup_stale_containers()


# ============================================================
# GLOBAL INSTANCE
# ============================================================

_sandbox_manager: Optional[SandboxManager] = None


async def get_sandbox_manager() -> SandboxManager:
    """Get or create the global sandbox manager."""
    global _sandbox_manager

    if _sandbox_manager is None:
        # Load configuration from settings
        try:
            from src.core.config import settings

            # Map settings mode string to SandboxMode enum
            mode_map = {
                "docker": SandboxMode.DOCKER,
                "subprocess": SandboxMode.SUBPROCESS,
                "disabled": SandboxMode.DISABLED,
            }
            mode = mode_map.get(settings.SANDBOX_MODE.lower(), SandboxMode.DOCKER)

            # Build config from settings
            config = DockerSandboxConfig(
                timeout_seconds=float(settings.SANDBOX_TIMEOUT_SECONDS),
                max_memory_mb=settings.SANDBOX_MAX_MEMORY_MB,
                max_cpu_percent=settings.SANDBOX_MAX_CPU_PERCENT,
                max_output_bytes=settings.SANDBOX_MAX_OUTPUT_BYTES,
                network_mode="bridge" if settings.SANDBOX_NETWORK_ENABLED else "none",
            )

            # Parse image name and tag
            if ":" in settings.SANDBOX_DOCKER_IMAGE:
                config.image_name, config.image_tag = settings.SANDBOX_DOCKER_IMAGE.rsplit(":", 1)
            else:
                config.image_name = settings.SANDBOX_DOCKER_IMAGE

            _sandbox_manager = SandboxManager(mode=mode, config=config)

        except ImportError:
            # Settings not available, use defaults
            _sandbox_manager = SandboxManager()

        await _sandbox_manager.initialize()

    return _sandbox_manager


def reset_sandbox_manager() -> None:
    """Reset the sandbox manager (for testing)."""
    global _sandbox_manager
    _sandbox_manager = None
