# Vibe Code Mode: Python Backend Migration Architecture

## Overview

This document outlines a complete Python backend implementation for migrating the Vibe Code Mode feature from Rust/Electron Goose to a Python-based architecture with dynamic LLM configuration.

---

## 1. Core Architecture Principles

### The Vibe Code Mode Flow (Simplified for Python)

```
USER PROMPT
    ↓
LLM GENERATES TYPESCRIPT SCRIPT
    ↓
BACKEND: Transpile TS → JS
    ↓
BACKEND: Type-check against available tools
    ↓
BACKEND: Execute in sandbox (Node.js or Deno)
    ↓
TOOL INTERCEPTION: Route calls to Python services
    ↓
COLLECT OUTPUTS & TOOL GRAPH (DAG)
    ↓
FRONTEND: Display DAG + Code + Logs (side-by-side)
```

### Key Differences: Rust → Python

| Aspect | Rust (Original) | Python (New) |
|--------|-----------------|-------------|
| **Runtime** | pctx/Deno + V8 | Node.js/Deno (via subprocess) |
| **Code Gen** | LLM generates TypeScript | LLM generates TypeScript (same) |
| **Tool System** | Native Rust async callbacks | Python async handlers with IPC |
| **Sandboxing** | Embedded V8 | External Node.js process |
| **Type Checking** | V8 native + custom validators | tsc (TypeScript compiler) |
| **LLM** | Provider integrations | User-configurable via settings |

---

## 2. Proposed Python Project Structure

```
python-backend/
├── config/
│   ├── __init__.py
│   ├── settings.py              # Environment, LLM configs, paths
│   └── llm_config.py            # User LLM provider settings
├── core/
│   ├── __init__.py
│   ├── vibe_code_executor.py    # Main orchestrator for Vibe Code Mode
│   ├── llm_provider.py          # Dynamic LLM provider factory
│   ├── tool_registry.py         # Meta-tool handshake system
│   └── sandbox_manager.py       # Node.js/Deno process management
├── schemas/
│   ├── __init__.py
│   ├── tool_schemas.py          # Pydantic models for tool definitions
│   ├── code_execution.py        # Code execution request/response models
│   ├── tool_graph.py            # DAG/Tool Graph models
│   └── llm_request.py           # LLM request/response models
├── services/
│   ├── __init__.py
│   ├── code_generation.py       # LLM calls to generate TypeScript
│   ├── code_compilation.py      # TypeScript → JavaScript compilation
│   ├── code_sandbox.py          # Sandbox execution orchestration
│   ├── tool_execution.py        # Handler for individual tool calls
│   └── logging_service.py       # Real-time log aggregation
├── repositories/
│   ├── __init__.py
│   ├── execution_cache.py       # Cache execution results (optional)
│   ├── tool_registry_repo.py    # Store/retrieve available tools
│   └── session_repo.py          # Execution session state
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── code_execution.py    # POST /api/code/execute
│   │   ├── tools.py             # GET /api/tools, /api/tools/{id}
│   │   └── sessions.py          # GET /api/sessions/{id}
│   ├── middleware.py            # Request validation, auth
│   └── websocket_handler.py     # Real-time log streaming
├── models/
│   ├── __init__.py
│   ├── tool_model.py            # Tool definition & metadata
│   ├── execution_model.py       # Execution state & history
│   └── llm_config_model.py      # User LLM provider configuration
├── utils/
│   ├── __init__.py
│   ├── process_manager.py       # Manage Node.js subprocesses
│   ├── json_utils.py            # JSON serialization helpers
│   ├── validators.py            # Custom validation logic
│   └── errors.py                # Custom exception classes
├── sandbox/
│   ├── runtime/
│   │   ├── tool_bridge.js       # JavaScript-Python IPC bridge
│   │   └── sandbox_init.js      # Sandbox initialization code
│   └── declarations/
│       └── tools.d.ts           # TypeScript declarations for tools
├── main.py                       # FastAPI application entry point
├── requirements.txt              # Python dependencies
└── docker-compose.yml            # Optional: Node.js + Python services
```

---

## 3. Detailed Layer Implementation

### 3.1 Schemas Layer (Pydantic Models)

**`schemas/tool_schemas.py`**:
```python
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class ToolParameter(BaseModel):
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str
    required: bool = False
    default: Optional[Any] = None

class ToolDefinition(BaseModel):
    id: str  # e.g., "developer.shell"
    name: str
    description: str
    parameters: List[ToolParameter]
    returns: Dict[str, Any]  # Return type specification
    category: str  # "shell", "file", "editor", etc.

class ListFunctionsRequest(BaseModel):
    include_categories: Optional[List[str]] = None

class ListFunctionsResponse(BaseModel):
    functions: List[ToolDefinition]
    total_count: int

class GetFunctionDetailsRequest(BaseModel):
    tool_id: str

class GetFunctionDetailsResponse(BaseModel):
    tool: ToolDefinition
    examples: Optional[List[str]] = None
```

**`schemas/code_execution.py`**:
```python
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

class ToolGraphNode(BaseModel):
    id: str
    tool: str  # e.g., "developer.shell"
    description: str
    depends_on: List[str] = []  # List of node IDs this depends on
    status: str  # "pending", "running", "completed", "failed"
    output: Optional[Any] = None
    error: Optional[str] = None

class CodeExecutionRequest(BaseModel):
    user_prompt: str
    code: str  # Generated TypeScript code
    tool_graph: Optional[List[ToolGraphNode]] = None
    context: Optional[Dict[str, Any]] = None
    timeout_seconds: int = 30

class CodeExecutionResponse(BaseModel):
    success: bool
    execution_id: str
    tool_graph: List[ToolGraphNode]
    generated_code: str
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_logs: List[str]
    duration_ms: float
```

**`schemas/llm_request.py`**:
```python
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class LLMMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class CodeGenerationRequest(BaseModel):
    user_prompt: str
    available_tools: List[str]  # List of tool IDs
    conversation_history: List[LLMMessage] = []
    user_preferences: Optional[Dict[str, Any]] = None

class CodeGenerationResponse(BaseModel):
    code: str  # Generated TypeScript
    tool_graph_plan: Optional[List[Dict[str, Any]]] = None
    explanation: Optional[str] = None
```

### 3.2 Models Layer (Database/State Models)

**`models/tool_model.py`**:
```python
from datetime import datetime
from typing import Any, Dict, List, Optional

class Tool:
    """In-memory or DB-backed tool registry"""
    
    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        handler: callable,
        parameters: List[Dict[str, Any]],
        category: str = "general",
        enabled: bool = True,
        created_at: datetime = None
    ):
        self.id = id
        self.name = name
        self.description = description
        self.handler = handler  # Python async function
        self.parameters = parameters
        self.category = category
        self.enabled = enabled
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "enabled": self.enabled,
        }
```

**`models/execution_model.py`**:
```python
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

class CodeExecution:
    """Represents a single code execution session"""
    
    def __init__(
        self,
        id: str = None,
        user_id: str = None,
        code: str = "",
        tool_graph: List[Dict[str, Any]] = None,
        status: str = "pending",
        created_at: datetime = None,
    ):
        self.id = id or str(uuid.uuid4())
        self.user_id = user_id
        self.code = code
        self.tool_graph = tool_graph or []
        self.status = status  # pending, running, completed, failed
        self.created_at = created_at or datetime.utcnow()
        self.completed_at = None
        self.result = None
        self.error = None
        self.logs = []
    
    def add_log(self, message: str, level: str = "info"):
        self.logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message
        })
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "code": self.code,
            "tool_graph": self.tool_graph,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "logs": self.logs,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
```

**`models/llm_config_model.py`**:
```python
from typing import Dict, Any, Optional
from enum import Enum

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    CUSTOM = "custom"

class UserLLMConfig:
    """Per-user LLM provider configuration"""
    
    def __init__(
        self,
        user_id: str,
        provider: LLMProvider,
        model: str,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ):
        self.user_id = user_id
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.parameters = parameters or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "provider": self.provider.value,
            "model": self.model,
            "api_base": self.api_base,
            "parameters": self.parameters,
        }
```

### 3.3 Services Layer (Business Logic)

**`services/code_generation.py`**:
```python
import logging
from typing import List, Dict, Any, Optional
from schemas.llm_request import CodeGenerationRequest, CodeGenerationResponse
from core.llm_provider import LLMProvider
from models.llm_config_model import UserLLMConfig

logger = logging.getLogger(__name__)

class CodeGenerationService:
    """Orchestrates LLM calls to generate TypeScript code"""
    
    def __init__(self, llm_provider_factory):
        self.llm_provider_factory = llm_provider_factory
    
    async def generate_code(
        self,
        request: CodeGenerationRequest,
        user_llm_config: UserLLMConfig,
    ) -> CodeGenerationResponse:
        """
        Call the user's configured LLM to generate TypeScript code
        """
        # Get the LLM provider based on user config
        llm = self.llm_provider_factory.get_provider(user_llm_config)
        
        # Build system prompt for code generation
        system_prompt = self._build_system_prompt(request.available_tools)
        
        # Build messages
        messages = [
            {"role": "user", "content": request.user_prompt}
        ]
        if request.conversation_history:
            messages = [
                {"role": m.role, "content": m.content}
                for m in request.conversation_history
            ] + messages
        
        # Call LLM
        response = await llm.generate(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )
        
        logger.info(f"Generated code for user {user_llm_config.user_id}")
        
        # Parse response (extract code block)
        code = self._extract_code_from_response(response.text)
        
        return CodeGenerationResponse(
            code=code,
            explanation=response.text,
        )
    
    def _build_system_prompt(self, available_tools: List[str]) -> str:
        tools_list = ", ".join(available_tools)
        return f"""You are a code generation expert. Generate TypeScript code that uses available tools to accomplish the user's goal.

Available tools: {tools_list}

Guidelines:
1. Generate pure TypeScript code that can be executed in a sandbox
2. Import tools from the "developer" module: import {{ shell, text_editor, ... }} from "developer"
3. Use async/await patterns for tool calls
4. Always wrap in an async main() function and export default main
5. Handle errors gracefully
6. Return meaningful results as JSON
"""
    
    def _extract_code_from_response(self, response_text: str) -> str:
        """Extract TypeScript code from LLM response (markdown code block)"""
        import re
        match = re.search(r'```(?:typescript|ts)?\n(.*?)\n```', response_text, re.DOTALL)
        return match.group(1) if match else response_text
```

**`services/code_compilation.py`**:
```python
import asyncio
import logging
import json
import tempfile
import os
from typing import Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class CodeCompilationService:
    """Compiles TypeScript to JavaScript and validates types"""
    
    def __init__(self, node_path: str = "node", tsc_path: str = "tsc"):
        self.node_path = node_path
        self.tsc_path = tsc_path
    
    async def compile_typescript(
        self,
        code: str,
        tool_declarations: str,
    ) -> Tuple[str, Optional[str]]:
        """
        Compile TypeScript code to JavaScript.
        Returns (js_code, error_message)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write source files
            ts_file = Path(tmpdir) / "main.ts"
            decl_file = Path(tmpdir) / "tools.d.ts"
            tsconfig_file = Path(tmpdir) / "tsconfig.json"
            
            ts_file.write_text(code)
            decl_file.write_text(tool_declarations)
            
            # Write tsconfig.json
            tsconfig = {
                "compilerOptions": {
                    "target": "ES2020",
                    "module": "esnext",
                    "lib": ["ES2020"],
                    "strict": True,
                    "esModuleInterop": True,
                    "skipLibCheck": True,
                    "forceConsistentCasingInFileNames": True,
                },
                "include": ["*.ts"],
            }
            tsconfig_file.write_text(json.dumps(tsconfig, indent=2))
            
            # Run tsc
            try:
                result = await asyncio.create_subprocess_exec(
                    self.tsc_path,
                    "--noEmit",
                    cwd=tmpdir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                stdout, stderr = await asyncio.wait_for(
                    result.communicate(),
                    timeout=10.0,
                )
                
                if result.returncode != 0:
                    error_msg = stderr.decode() or stdout.decode()
                    logger.error(f"TypeScript compilation error: {error_msg}")
                    return "", error_msg
                
                # Now compile with babel or swc for actual JS output
                js_code = await self._transpile_to_js(code, tmpdir)
                return js_code, None
                
            except asyncio.TimeoutError:
                return "", "TypeScript compilation timeout"
            except Exception as e:
                logger.error(f"Compilation error: {e}")
                return "", str(e)
    
    async def _transpile_to_js(self, code: str, tmpdir: str) -> str:
        """Transpile TypeScript to JavaScript using esbuild or similar"""
        # For simplicity, using a basic regex-based transpilation
        # In production, use esbuild or swc for accurate transpilation
        js_code = code
        # Remove type annotations (simplified)
        import re
        js_code = re.sub(r':\s*\w+(\[\])?', '', js_code)  # Remove `: Type`
        js_code = re.sub(r'as\s+\w+', '', js_code)  # Remove `as Type`
        return js_code
```

**`services/code_sandbox.py`**:
```python
import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from models.execution_model import CodeExecution
from schemas.tool_schemas import ToolGraphNode

logger = logging.getLogger(__name__)

class CodeSandboxService:
    """Executes code in an isolated Node.js environment"""
    
    def __init__(
        self,
        node_path: str = "node",
        tool_registry=None,
        deno_path: Optional[str] = None,
    ):
        self.node_path = node_path
        self.deno_path = deno_path
        self.tool_registry = tool_registry
        self.tool_bridge_template = self._load_bridge_template()
    
    async def execute(
        self,
        execution: CodeExecution,
        code: str,
        timeout_seconds: int = 30,
    ) -> CodeExecution:
        """Execute TypeScript code in sandbox"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Write main code
            main_file = tmpdir_path / "main.js"
            main_file.write_text(code)
            
            # Write IPC bridge
            bridge_file = tmpdir_path / "bridge.js"
            bridge_file.write_text(self.tool_bridge_template)
            
            # Start Node.js subprocess
            execution.add_log("Starting Node.js sandbox...", "info")
            
            try:
                process = await asyncio.create_subprocess_exec(
                    self.node_path,
                    str(main_file),
                    cwd=tmpdir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,
                )
                
                # Execute with timeout
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds,
                )
                
                output = stdout.decode()
                error = stderr.decode()
                
                execution.add_log(output, "debug")
                if error:
                    execution.add_log(error, "error")
                    execution.error = error
                    execution.status = "failed"
                else:
                    execution.result = json.loads(output) if output else None
                    execution.status = "completed"
                
            except asyncio.TimeoutError:
                execution.error = f"Execution timeout after {timeout_seconds} seconds"
                execution.status = "failed"
                execution.add_log(execution.error, "error")
            except Exception as e:
                execution.error = str(e)
                execution.status = "failed"
                execution.add_log(str(e), "error")
        
        return execution
    
    def _load_bridge_template(self) -> str:
        """IPC bridge for tool calls from JavaScript to Python"""
        return '''
// Tool bridge: routes tool calls from TS to Python backend
const tools = {};

['developer.shell', 'developer.text_editor', 'developer.read_file'].forEach(toolId => {
    tools[toolId] = async (args) => {
        // In production, send to Python via IPC/HTTP
        console.log(JSON.stringify({ type: 'tool_call', tool: toolId, args }));
        // Wait for response via stdin or HTTP
        return { success: true, data: "mocked" };
    };
});

export { tools };
'''
```

### 3.4 Repositories Layer

**`repositories/tool_registry_repo.py`**:
```python
from typing import Dict, List, Optional
from models.tool_model import Tool
import logging

logger = logging.getLogger(__name__)

class ToolRegistryRepository:
    """In-memory or database-backed tool registry"""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register_tool(self, tool: Tool):
        """Register a new tool"""
        self._tools[tool.id] = tool
        logger.info(f"Registered tool: {tool.id}")
    
    def get_tool(self, tool_id: str) -> Optional[Tool]:
        """Retrieve a tool by ID"""
        return self._tools.get(tool_id)
    
    def list_tools(self, category: Optional[str] = None) -> List[Tool]:
        """List all tools, optionally filtered by category"""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools
    
    def list_enabled_tools(self) -> List[Tool]:
        """List only enabled tools"""
        return [t for t in self._tools.values() if t.enabled]
```

**`repositories/session_repo.py`**:
```python
from typing import Dict, Optional
from models.execution_model import CodeExecution

class SessionRepository:
    """Store execution sessions (in-memory or database)"""
    
    def __init__(self):
        self._sessions: Dict[str, CodeExecution] = {}
    
    def save_session(self, execution: CodeExecution):
        """Save or update an execution session"""
        self._sessions[execution.id] = execution
    
    def get_session(self, execution_id: str) -> Optional[CodeExecution]:
        """Retrieve a session by ID"""
        return self._sessions.get(execution_id)
    
    def list_sessions(self, user_id: str) -> list:
        """List all sessions for a user"""
        return [
            e for e in self._sessions.values()
            if e.user_id == user_id
        ]
```

### 3.5 Core Layer (Orchestration)

**`core/tool_registry.py`**:
```python
from typing import List, Dict, Any
from models.tool_model import Tool
from schemas.tool_schemas import ToolDefinition, ToolParameter
import inspect

class ToolRegistry:
    """Meta-tool handshake system"""
    
    def __init__(self, repository):
        self.repo = repository
    
    async def list_functions(self, include_categories: List[str] = None) -> List[ToolDefinition]:
        """List available functions (meta-tool #1)"""
        tools = self.repo.list_enabled_tools()
        
        if include_categories:
            tools = [t for t in tools if t.category in include_categories]
        
        return [
            ToolDefinition(
                id=t.id,
                name=t.name,
                description=t.description,
                parameters=t.parameters,
                returns={"type": "object"},
                category=t.category,
            )
            for t in tools
        ]
    
    async def get_function_details(self, tool_id: str) -> ToolDefinition:
        """Get detailed info about a function (meta-tool #2)"""
        tool = self.repo.get_tool(tool_id)
        if not tool:
            raise ValueError(f"Tool {tool_id} not found")
        
        return ToolDefinition(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
            returns={"type": "object"},
            category=tool.category,
        )
    
    def generate_tool_declarations(self) -> str:
        """Generate TypeScript declarations for all tools"""
        tools = self.repo.list_enabled_tools()
        
        declarations = "declare module 'developer' {\n"
        for tool in tools:
            declarations += self._tool_to_typescript(tool)
        declarations += "}\n"
        
        return declarations
    
    def _tool_to_typescript(self, tool: Tool) -> str:
        """Convert a Tool to TypeScript declaration"""
        params = ", ".join([
            f"{p['name']}{'?' if not p.get('required', False) else ''}: {p['type']}"
            for p in tool.parameters
        ])
        
        return f"""
  export async function {tool.name}({params}): Promise<any>;
"""
```

**`core/vibe_code_executor.py`**:
```python
import logging
import asyncio
from datetime import datetime
from typing import Optional
from schemas.code_execution import CodeExecutionRequest, CodeExecutionResponse
from models.execution_model import CodeExecution
from models.llm_config_model import UserLLMConfig
from services.code_generation import CodeGenerationService
from services.code_compilation import CodeCompilationService
from services.code_sandbox import CodeSandboxService
from services.tool_execution import ToolExecutionService
from repositories.session_repo import SessionRepository

logger = logging.getLogger(__name__)

class VibeCodeExecutor:
    """Main orchestrator for Vibe Code Mode"""
    
    def __init__(
        self,
        code_gen_service: CodeGenerationService,
        code_compile_service: CodeCompilationService,
        code_sandbox_service: CodeSandboxService,
        tool_exec_service: ToolExecutionService,
        session_repo: SessionRepository,
        tool_registry,
    ):
        self.code_gen = code_gen_service
        self.code_compile = code_compile_service
        self.code_sandbox = code_sandbox_service
        self.tool_exec = tool_exec_service
        self.session_repo = session_repo
        self.tool_registry = tool_registry
    
    async def execute(
        self,
        request: CodeExecutionRequest,
        user_id: str,
        user_llm_config: UserLLMConfig,
    ) -> CodeExecutionResponse:
        """Execute Vibe Code Mode workflow"""
        
        # Create execution session
        execution = CodeExecution(user_id=user_id)
        self.session_repo.save_session(execution)
        
        try:
            # Step 1: If code not provided, generate it
            if not request.code:
                execution.add_log("Generating TypeScript code from prompt...", "info")
                available_tools = [t.id for t in self.tool_registry.repo.list_enabled_tools()]
                
                code_gen_response = await self.code_gen.generate_code(
                    CodeGenerationRequest(
                        user_prompt=request.user_prompt,
                        available_tools=available_tools,
                    ),
                    user_llm_config,
                )
                code = code_gen_response.code
            else:
                code = request.code
            
            execution.code = code
            
            # Step 2: Compile TypeScript to JavaScript
            execution.add_log("Compiling TypeScript to JavaScript...", "info")
            tool_declarations = self.tool_registry.generate_tool_declarations()
            
            js_code, compile_error = await self.code_compile.compile_typescript(
                code, tool_declarations
            )
            
            if compile_error:
                execution.error = compile_error
                execution.status = "failed"
                execution.add_log(f"Compilation error: {compile_error}", "error")
                self.session_repo.save_session(execution)
                return self._to_response(execution)
            
            # Step 3: Execute in sandbox
            execution.add_log("Executing code in sandbox...", "info")
            execution.status = "running"
            
            execution = await self.code_sandbox.execute(
                execution,
                js_code,
                timeout_seconds=request.timeout_seconds,
            )
            
            # Step 4: Build tool graph (DAG) from execution
            execution.tool_graph = request.tool_graph or []
            
            execution.completed_at = datetime.utcnow()
            self.session_repo.save_session(execution)
            
            execution.add_log("Code execution completed.", "info")
            
        except Exception as e:
            logger.error(f"Execution error: {e}", exc_info=True)
            execution.error = str(e)
            execution.status = "failed"
            execution.add_log(str(e), "error")
            self.session_repo.save_session(execution)
        
        return self._to_response(execution)
    
    def _to_response(self, execution: CodeExecution) -> CodeExecutionResponse:
        """Convert CodeExecution model to API response"""
        return CodeExecutionResponse(
            success=execution.status == "completed",
            execution_id=execution.id,
            tool_graph=execution.tool_graph,
            generated_code=execution.code,
            result=execution.result,
            error=execution.error,
            execution_logs=["  ".join([l['timestamp'], l['level'], l['message']]) for l in execution.logs],
            duration_ms=0,  # Calculate from timestamps if needed
        )
```

**`core/llm_provider.py`**:
```python
import logging
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod
from models.llm_config_model import UserLLMConfig, LLMProvider

logger = logging.getLogger(__name__)

class BaseLLMProvider(ABC):
    """Abstract base for LLM providers"""
    
    def __init__(self, config: UserLLMConfig):
        self.config = config
    
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> 'GenerationResponse':
        pass

class AnthropicProvider(BaseLLMProvider):
    async def generate(self, system_prompt, messages, temperature=0.7, max_tokens=2048):
        import anthropic
        
        client = anthropic.Anthropic(api_key=self.config.api_key)
        
        response = await client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
        )
        
        return GenerationResponse(
            text=response.content[0].text,
            stop_reason=response.stop_reason,
        )

class OpenAIProvider(BaseLLMProvider):
    async def generate(self, system_prompt, messages, temperature=0.7, max_tokens=2048):
        import openai
        
        client = openai.AsyncOpenAI(api_key=self.config.api_key)
        
        all_messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]
        
        response = await client.chat.completions.create(
            model=self.config.model,
            messages=all_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return GenerationResponse(
            text=response.choices[0].message.content,
            stop_reason=response.choices[0].finish_reason,
        )

class LLMProviderFactory:
    """Factory for creating provider instances based on user config"""
    
    _providers = {
        LLMProvider.ANTHROPIC: AnthropicProvider,
        LLMProvider.OPENAI: OpenAIProvider,
        # Add more as needed
    }
    
    @classmethod
    def get_provider(cls, config: UserLLMConfig) -> BaseLLMProvider:
        """Get appropriate provider instance"""
        provider_class = cls._providers.get(config.provider)
        if not provider_class:
            raise ValueError(f"Unknown provider: {config.provider}")
        return provider_class(config)

class GenerationResponse:
    def __init__(self, text: str, stop_reason: str):
        self.text = text
        self.stop_reason = stop_reason
```

### 3.6 API Routes Layer

**`api/routes/code_execution.py`**:
```python
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from schemas.code_execution import CodeExecutionRequest, CodeExecutionResponse
from core.vibe_code_executor import VibeCodeExecutor
from models.llm_config_model import UserLLMConfig

router = APIRouter(prefix="/api/code", tags=["code-execution"])

async def get_current_user_id() -> str:
    """Dependency: extract user ID from request"""
    # Implement auth logic here
    return "user_123"

async def get_user_llm_config(user_id: str) -> UserLLMConfig:
    """Dependency: fetch user's LLM configuration"""
    # Load from database/cache
    from config.llm_config import get_user_llm_config as db_get
    return db_get(user_id)

@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    executor: VibeCodeExecutor = Depends(),
    user_id: str = Depends(get_current_user_id),
    user_llm_config: UserLLMConfig = Depends(get_user_llm_config),
):
    """Execute Vibe Code Mode"""
    try:
        response = await executor.execute(request, user_id, user_llm_config)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/execution/{execution_id}")
async def get_execution(
    execution_id: str,
    session_repo = Depends(),
):
    """Retrieve execution details"""
    execution = session_repo.get_session(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution.to_dict()
```

**`api/routes/tools.py`**:
```python
from fastapi import APIRouter, HTTPException, Depends
from schemas.tool_schemas import ListFunctionsResponse, GetFunctionDetailsResponse
from core.tool_registry import ToolRegistry

router = APIRouter(prefix="/api/tools", tags=["tools"])

@router.get("/", response_model=ListFunctionsResponse)
async def list_tools(
    category: Optional[str] = None,
    tool_registry: ToolRegistry = Depends(),
):
    """List available tools (meta-tool #1)"""
    tools = await tool_registry.list_functions(
        include_categories=[category] if category else None
    )
    return ListFunctionsResponse(
        functions=tools,
        total_count=len(tools),
    )

@router.get("/{tool_id}", response_model=GetFunctionDetailsResponse)
async def get_tool_details(
    tool_id: str,
    tool_registry: ToolRegistry = Depends(),
):
    """Get tool details (meta-tool #2)"""
    try:
        tool = await tool_registry.get_function_details(tool_id)
        return GetFunctionDetailsResponse(tool=tool)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

---

## 4. FastAPI Application Setup

**`main.py`**:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config.settings import Settings
from repositories.tool_registry_repo import ToolRegistryRepository
from repositories.session_repo import SessionRepository
from core.tool_registry import ToolRegistry
from core.vibe_code_executor import VibeCodeExecutor
from services.code_generation import CodeGenerationService
from services.code_compilation import CodeCompilationService
from services.code_sandbox import CodeSandboxService
from services.tool_execution import ToolExecutionService
from api.routes import code_execution, tools

settings = Settings()

# Initialize repositories and services
tool_registry_repo = ToolRegistryRepository()
session_repo = SessionRepository()
tool_registry = ToolRegistry(tool_registry_repo)

code_gen_service = CodeGenerationService(llm_provider_factory=None)  # Injected per request
code_compile_service = CodeCompilationService()
code_sandbox_service = CodeSandboxService(tool_registry=tool_registry)
tool_exec_service = ToolExecutionService()

executor = VibeCodeExecutor(
    code_gen_service=code_gen_service,
    code_compile_service=code_compile_service,
    code_sandbox_service=code_sandbox_service,
    tool_exec_service=tool_exec_service,
    session_repo=session_repo,
    tool_registry=tool_registry,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Initializing Vibe Code Mode Backend...")
    # Register default tools
    from tools.builtin_tools import register_builtin_tools
    register_builtin_tools(tool_registry_repo)
    
    yield
    
    # Shutdown
    print("Shutting down...")

app = FastAPI(
    title="Vibe Code Mode API",
    description="Python backend for Vibe Code Mode",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(code_execution.router)
app.include_router(tools.router)

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 5. Migration Strategy & Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Set up Python project structure with FastAPI
- [ ] Implement Pydantic schemas for all models
- [ ] Create database models (SQLAlchemy if using DB)
- [ ] Implement repositories layer (in-memory first)

### Phase 2: Core Services (Week 2-3)
- [ ] Implement LLM provider factory with user config support
- [ ] Implement code generation service (calls LLM)
- [ ] Implement code compilation service (TypeScript → JavaScript)
- [ ] Implement code sandbox service (Node.js execution)

### Phase 3: Integration (Week 3-4)
- [ ] Wire up VibeCodeExecutor orchestrator
- [ ] Implement API routes (code execution, tools)
- [ ] Add WebSocket support for real-time logs
- [ ] Implement tool registry system

### Phase 4: Polish & Optimization (Week 4+)
- [ ] Add database persistence (SQLAlchemy)
- [ ] Implement caching layer
- [ ] Add comprehensive error handling
- [ ] Performance optimization & load testing

---

## 6. Key Features Comparison: Rust vs Python

| Feature | Rust (Original) | Python (Proposed) |
|---------|-----------------|------------------|
| **Speed** | ⚡ Very fast | 🟡 Good (async/await) |
| **Type Safety** | ✅ Compile-time | 🟡 Runtime (Pydantic) |
| **Deployment** | Binary | Docker container |
| **Development** | Slower (compilation) | ⚡ Fast (iteration) |
| **LLM Integration** | Hard-coded providers | ✅ Dynamic/user-configurable |
| **Maintenance** | Complex | More accessible |
| **Community** | Smaller | Larger (Python) |

---

## 7. Integration with Frontend

The frontend remains similar to the Electron GUI but connects to Python backend:

```
FRONTEND (React/Electron)
    ↓ HTTP/WebSocket
FASTAPI Backend (Python)
    ↓ Subprocess/IPC
Node.js Sandbox (Code Execution)
    ↓ IPC Callbacks
BACKEND SERVICES (Tool Registry, File I/O, etc.)
```

### WebSocket for Real-Time Logs

```python
@app.websocket("/ws/execution/{execution_id}")
async def websocket_logs(websocket: WebSocket, execution_id: str):
    await websocket.accept()
    execution = session_repo.get_session(execution_id)
    
    if not execution:
        await websocket.close(code=4004, reason="Execution not found")
        return
    
    # Stream logs as they arrive
    for log_entry in execution.logs:
        await websocket.send_json(log_entry)
```

---

## 8. Conclusion

This Python architecture provides:
1. **Clean separation of concerns** (models, services, routes)
2. **Dynamic LLM configuration** per user
3. **Scalable design** (easy to add caching, DB, async job queues)
4. **Type safety** via Pydantic schemas
5. **Easy deployment** via Docker
6. **Maintainability** for Python developers

The system maintains the core "Vibe Coding" paradigm while adapting to Python's ecosystem.
