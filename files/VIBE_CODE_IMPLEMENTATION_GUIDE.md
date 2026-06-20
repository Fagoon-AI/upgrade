# Vibe Code Mode Python Backend: Quick Start Implementation Guide

---

## Quick Setup (30 minutes)

### Step 1: Project Initialization

```bash
# Create project directory
mkdir vibe-code-backend && cd vibe-code-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Initialize Git
git init
echo "venv/" > .gitignore
echo ".env" >> .gitignore
echo "__pycache__/" >> .gitignore
```

### Step 2: Install Dependencies

**`requirements.txt`**:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
httpx==0.25.1
python-dotenv==1.0.0
anthropic==0.7.0
openai==1.3.0
google-cloud-aiplatform==1.38.0
aiofiles==23.2.1
sqlalchemy==2.0.23
sqlmodel==0.0.14
pytest==7.4.3
pytest-asyncio==0.21.1
```

**Installation**:
```bash
pip install -r requirements.txt

# Also ensure Node.js and TypeScript compiler are available
npm install -g typescript
npm install -g esbuild
```

### Step 3: Create Directory Structure

```bash
mkdir -p config core schemas services repositories models api/routes utils sandbox/runtime
touch {config,core,schemas,services,repositories,models,api,api/routes,utils}/__init__.py
touch main.py requirements.txt .env.example docker-compose.yml
```

---

## Detailed Implementation Files

### 1. Configuration Files

**`config/settings.py`**:
```python
from pydantic_settings import BaseSettings
from pathlib import Path
import os

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Vibe Code Backend"
    DEBUG: bool = os.getenv("DEBUG", False)
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    SANDBOX_TEMP_DIR: Path = Path("/tmp/vibe-sandbox")
    
    # Node.js/TypeScript
    NODE_PATH: str = "node"
    TSC_PATH: str = "tsc"
    ESBUILD_PATH: str = "esbuild"
    
    # Code execution
    EXECUTION_TIMEOUT: int = 30
    MAX_CODE_LENGTH: int = 50000
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**`config/llm_config.py`**:
```python
from typing import Dict, Optional
from models.llm_config_model import UserLLMConfig, LLMProvider
import json
from pathlib import Path

# In production, load from database
USER_CONFIGS: Dict[str, UserLLMConfig] = {}

def get_user_llm_config(user_id: str) -> UserLLMConfig:
    """Fetch user's LLM configuration"""
    if user_id not in USER_CONFIGS:
        # Default to Anthropic
        USER_CONFIGS[user_id] = UserLLMConfig(
            user_id=user_id,
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-sonnet-20240229",
            api_key="YOUR_API_KEY",
        )
    return USER_CONFIGS[user_id]

def set_user_llm_config(config: UserLLMConfig):
    """Update user's LLM configuration"""
    USER_CONFIGS[config.user_id] = config
    # Persist to database here
```

**`.env.example`**:
```
DEBUG=True
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# LLM Providers (users can override in settings)
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
GOOGLE_API_KEY=your_key_here

# Execution
EXECUTION_TIMEOUT=30
```

### 2. Built-in Tools

**`tools/builtin_tools.py`**:
```python
import subprocess
import os
import asyncio
import json
from pathlib import Path
from models.tool_model import Tool

async def shell_handler(command: str, cwd: str = None) -> Dict:
    """Execute shell command"""
    try:
        result = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or os.getcwd(),
        )
        stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=15)
        
        return {
            "success": result.returncode == 0,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "returncode": result.returncode,
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": "Command timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def text_editor_handler(filepath: str, action: str, content: str = None) -> Dict:
    """File read/write operations"""
    try:
        path = Path(filepath)
        
        if action == "read":
            return {
                "success": True,
                "content": path.read_text(),
            }
        elif action == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return {"success": True, "message": f"Written {len(content)} bytes"}
        elif action == "append":
            with open(path, "a") as f:
                f.write(content)
            return {"success": True, "message": "Appended"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def json_processor_handler(data: str, operation: str) -> Dict:
    """JSON parsing and formatting"""
    try:
        parsed = json.loads(data)
        
        if operation == "format":
            return {
                "success": True,
                "result": json.dumps(parsed, indent=2),
            }
        elif operation == "minify":
            return {
                "success": True,
                "result": json.dumps(parsed, separators=(',', ':')),
            }
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {e}"}

def register_builtin_tools(repo):
    """Register all built-in tools"""
    
    tools = [
        Tool(
            id="developer.shell",
            name="shell",
            description="Execute shell commands",
            handler=shell_handler,
            parameters=[
                {"name": "command", "type": "string", "description": "Shell command", "required": True},
                {"name": "cwd", "type": "string", "description": "Working directory", "required": False},
            ],
            category="shell",
        ),
        Tool(
            id="developer.text_editor",
            name="text_editor",
            description="Read/write/append files",
            handler=text_editor_handler,
            parameters=[
                {"name": "filepath", "type": "string", "description": "File path", "required": True},
                {"name": "action", "type": "string", "description": "read|write|append", "required": True},
                {"name": "content", "type": "string", "description": "Content (for write/append)", "required": False},
            ],
            category="file",
        ),
        Tool(
            id="developer.json_processor",
            name="json_processor",
            description="Parse and format JSON",
            handler=json_processor_handler,
            parameters=[
                {"name": "data", "type": "string", "description": "JSON string", "required": True},
                {"name": "operation", "type": "string", "description": "format|minify", "required": True},
            ],
            category="utility",
        ),
    ]
    
    for tool in tools:
        repo.register_tool(tool)
```

### 3. Utility Classes

**`utils/errors.py`**:
```python
class VibeCodeException(Exception):
    """Base exception for Vibe Code Mode"""
    pass

class CompilationError(VibeCodeException):
    """TypeScript compilation error"""
    pass

class SandboxExecutionError(VibeCodeException):
    """Code execution in sandbox failed"""
    pass

class ToolNotFoundError(VibeCodeException):
    """Tool not registered"""
    pass

class LLMError(VibeCodeException):
    """LLM provider error"""
    pass
```

**`utils/process_manager.py`**:
```python
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ProcessManager:
    """Manages Node.js subprocess lifecycle"""
    
    def __init__(self, node_path: str = "node"):
        self.node_path = node_path
        self.active_processes = {}
    
    async def run_script(
        self,
        script_path: str,
        cwd: str,
        timeout: int = 30,
        env: dict = None,
    ) -> tuple:
        """
        Run Node.js script and return (stdout, stderr, returncode)
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self.node_path,
                script_path,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            
            return stdout.decode(), stderr.decode(), process.returncode
            
        except asyncio.TimeoutError:
            process.kill()
            raise TimeoutError(f"Script execution timeout after {timeout}s")
        except Exception as e:
            logger.error(f"Process error: {e}")
            raise
```

**`utils/validators.py`**:
```python
import re
from utils.errors import VibeCodeException

def validate_typescript_code(code: str, max_length: int = 50000) -> None:
    """Validate TypeScript code before execution"""
    
    if not code or not code.strip():
        raise VibeCodeException("Code cannot be empty")
    
    if len(code) > max_length:
        raise VibeCodeException(f"Code exceeds maximum length of {max_length}")
    
    # Check for dangerous patterns (basic validation)
    dangerous_patterns = [
        r'process\.exit',
        r'eval\(',
        r'__dirname',
        r'require.*fs',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            raise VibeCodeException(f"Code contains dangerous pattern: {pattern}")

def validate_tool_id(tool_id: str) -> None:
    """Validate tool ID format"""
    if not re.match(r'^[a-z]+\.[a-z_]+$', tool_id):
        raise VibeCodeException(f"Invalid tool ID format: {tool_id}")
```

### 4. Sandbox JavaScript Runtime

**`sandbox/runtime/tool_bridge.js`**:
```javascript
// Tool bridge: IPC between TypeScript/JavaScript and Python backend

import { EventEmitter } from 'events';

class ToolBridge extends EventEmitter {
  constructor() {
    super();
    this.toolHandlers = new Map();
    this.initialized = false;
  }

  async initialize(toolDefinitions) {
    // Create proxy objects for each tool
    this.tools = {};
    
    for (const toolDef of toolDefinitions) {
      const [namespace, toolName] = toolDef.id.split('.');
      
      if (!this.tools[namespace]) {
        this.tools[namespace] = {};
      }
      
      this.tools[namespace][toolName] = async (...args) => {
        return await this.callTool(toolDef.id, args);
      };
    }
    
    this.initialized = true;
  }

  async callTool(toolId, args) {
    // In real implementation, this communicates via IPC/HTTP
    // For now, return mock data
    console.log(`Calling tool: ${toolId} with args:`, args);
    
    return {
      success: true,
      data: `Executed ${toolId}`,
      timestamp: new Date().toISOString(),
    };
  }
}

export default new ToolBridge();
```

**`sandbox/runtime/sandbox_init.js`**:
```javascript
// Initialize sandbox with available tools

import toolBridge from './tool_bridge.js';

async function initializeSandbox(toolDefinitions) {
  console.log(`[SANDBOX] Initializing with ${toolDefinitions.length} tools`);
  
  await toolBridge.initialize(toolDefinitions);
  
  // Create global developer module
  globalThis.developer = toolBridge.tools;
  
  // Setup global utilities
  globalThis.log = console.log;
  globalThis.logError = console.error;
  
  console.log('[SANDBOX] Ready for code execution');
}

export { initializeSandbox };
```

**`sandbox/declarations/tools.d.ts`**:
```typescript
// TypeScript type definitions for available tools

declare module 'developer' {
  export async function shell(command: string, cwd?: string): Promise<{
    success: boolean;
    stdout: string;
    stderr: string;
    returncode: number;
  }>;

  export async function text_editor(
    filepath: string,
    action: 'read' | 'write' | 'append',
    content?: string
  ): Promise<{
    success: boolean;
    content?: string;
    message?: string;
    error?: string;
  }>;

  export async function json_processor(
    data: string,
    operation: 'format' | 'minify'
  ): Promise<{
    success: boolean;
    result?: string;
    error?: string;
  }>;
}
```

### 5. Tool Execution Service

**`services/tool_execution.py`**:
```python
import asyncio
import logging
from typing import Any, Dict, Optional
from models.tool_model import Tool

logger = logging.getLogger(__name__)

class ToolExecutionService:
    """Executes individual tools"""
    
    def __init__(self):
        self.execution_cache = {}
    
    async def execute_tool(
        self,
        tool: Tool,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute a tool with given arguments"""
        
        if not tool.enabled:
            return {"error": f"Tool {tool.id} is disabled"}
        
        try:
            # Call the tool handler
            result = await tool.handler(**kwargs)
            
            logger.info(f"Executed {tool.id}: {result}")
            return result
            
        except TypeError as e:
            return {"error": f"Invalid arguments for {tool.id}: {e}"}
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"error": str(e)}
    
    async def execute_tools_parallel(
        self,
        tools: list,
        *,
        raise_on_error: bool = False,
    ) -> Dict[str, Any]:
        """Execute multiple tools in parallel"""
        
        tasks = [
            self.execute_tool(tool)
            for tool in tools
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        if raise_on_error:
            for result in results:
                if isinstance(result, Exception):
                    raise result
        
        return {"results": results}
```

### 6. Complete API Routes Example

**`api/routes/code_execution.py`**:
```python
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
import logging
from typing import Optional
from schemas.code_execution import CodeExecutionRequest, CodeExecutionResponse
from core.vibe_code_executor import VibeCodeExecutor
from models.llm_config_model import UserLLMConfig
from config.llm_config import get_user_llm_config
from repositories.session_repo import SessionRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/code", tags=["code-execution"])

# Global instances (in production, use dependency injection)
executor = None
session_repo = SessionRepository()

def set_executor(exec_instance):
    global executor
    executor = exec_instance

def get_current_user_id() -> str:
    """Extract user ID (implement your auth here)"""
    return "user_default"

@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Execute Vibe Code Mode"""
    
    if not executor:
        raise HTTPException(status_code=500, detail="Executor not initialized")
    
    try:
        user_llm_config = get_user_llm_config(user_id)
        response = await executor.execute(request, user_id, user_llm_config)
        return response
    
    except Exception as e:
        logger.error(f"Execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/execution/{execution_id}")
async def get_execution(execution_id: str):
    """Get execution details"""
    execution = session_repo.get_session(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution.to_dict()

@router.get("/execution/{execution_id}/logs")
async def get_execution_logs(execution_id: str):
    """Get execution logs as server-sent events"""
    execution = session_repo.get_session(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    async def event_generator():
        for log_entry in execution.logs:
            yield f"data: {log_entry}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 7. Complete Main Application

**`main.py`**:
```python
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from config.settings import settings
from config.llm_config import get_user_llm_config
from repositories.tool_registry_repo import ToolRegistryRepository
from repositories.session_repo import SessionRepository
from core.tool_registry import ToolRegistry
from core.llm_provider import LLMProviderFactory
from core.vibe_code_executor import VibeCodeExecutor
from services.code_generation import CodeGenerationService
from services.code_compilation import CodeCompilationService
from services.code_sandbox import CodeSandboxService
from services.tool_execution import ToolExecutionService
from api.routes import code_execution, tools
from tools.builtin_tools import register_builtin_tools

# Setup logging
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Global state
tool_registry_repo = None
session_repo = None
tool_registry = None
executor = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global tool_registry_repo, session_repo, tool_registry, executor
    
    logger.info("🚀 Initializing Vibe Code Mode Backend...")
    
    # Initialize repositories
    tool_registry_repo = ToolRegistryRepository()
    session_repo = SessionRepository()
    tool_registry = ToolRegistry(tool_registry_repo)
    
    # Register built-in tools
    logger.info("📦 Registering built-in tools...")
    register_builtin_tools(tool_registry_repo)
    
    # Initialize services
    code_gen_service = CodeGenerationService(
        llm_provider_factory=LLMProviderFactory()
    )
    code_compile_service = CodeCompilationService(
        node_path=settings.NODE_PATH,
        tsc_path=settings.TSC_PATH,
    )
    code_sandbox_service = CodeSandboxService(
        node_path=settings.NODE_PATH,
        tool_registry=tool_registry,
    )
    tool_exec_service = ToolExecutionService()
    
    # Initialize executor
    executor = VibeCodeExecutor(
        code_gen_service=code_gen_service,
        code_compile_service=code_compile_service,
        code_sandbox_service=code_sandbox_service,
        tool_exec_service=tool_exec_service,
        session_repo=session_repo,
        tool_registry=tool_registry,
    )
    
    # Set executor in routes
    code_execution.set_executor(executor)
    
    logger.info("✅ Backend initialized successfully")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down...")

# Create FastAPI app
app = FastAPI(
    title="Vibe Code Mode API",
    description="Python backend for Vibe Code Mode - Dynamic LLM, Local Code Execution",
    version="1.0.0",
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

# Health check
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "vibe-code-backend",
        "initialized": executor is not None,
    }

@app.get("/config/llm")
async def get_llm_config():
    """Get current user's LLM config (for debugging)"""
    config = get_user_llm_config("user_default")
    return {
        "provider": config.provider.value,
        "model": config.model,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
```

---

## Running the Backend

### Development Mode

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python main.py

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Docker Deployment

**`Dockerfile`**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Node.js and TypeScript
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g typescript esbuild && \
    rm -rf /var/lib/apt/lists/*

# Copy Python files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose port
EXPOSE 8000

# Run server
CMD ["python", "main.py"]
```

**`docker-compose.yml`**:
```yaml
version: '3.8'

services:
  vibe-backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEBUG=False
      - LOG_LEVEL=INFO
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./:/app
```

Run with:
```bash
docker-compose up
```

---

## Testing

**`tests/test_code_execution.py`**:
```python
import pytest
import asyncio
from schemas.code_execution import CodeExecutionRequest
from models.llm_config_model import UserLLMConfig, LLMProvider

@pytest.mark.asyncio
async def test_simple_code_execution(executor):
    """Test basic code execution"""
    
    code = '''
    import { shell } from "developer";
    
    export default async function main() {
        const result = await shell("echo 'hello world'");
        return result;
    }
    '''
    
    request = CodeExecutionRequest(
        user_prompt="Execute echo command",
        code=code,
    )
    
    config = UserLLMConfig(
        user_id="test_user",
        provider=LLMProvider.ANTHROPIC,
        model="claude-3-sonnet",
    )
    
    response = await executor.execute(request, "test_user", config)
    assert response.success

@pytest.fixture
def executor():
    # Setup executor for tests
    from core.vibe_code_executor import VibeCodeExecutor
    # ... initialize with test dependencies
    return executor
```

Run tests:
```bash
pytest tests/ -v
```

---

## Performance Optimization Tips

1. **Caching**: Cache tool definitions and compilation results
   ```python
   from functools import lru_cache
   
   @lru_cache(maxsize=128)
   def get_tool_declarations(tool_count):
       # ...generate once per unique set
   ```

2. **Async Tool Execution**: Execute independent tools in parallel
   ```python
   results = await asyncio.gather(*[
       execute_tool(t) for t in tools
   ])
   ```

3. **Connection Pooling**: Reuse HTTP connections for LLM APIs
   ```python
   client = httpx.AsyncClient(
       limits=httpx.Limits(max_connections=100)
   )
   ```

4. **Database Indexing**: Add indexes on frequently queried fields
   ```python
   class Execution(Base):
       user_id: str = Column(String, index=True)
       created_at: datetime = Column(DateTime, index=True)
   ```

---

## Monitoring & Observability

Add structured logging:
```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
)

logger = structlog.get_logger()
```

---

## Next Steps

1. ✅ Set up the project structure
2. ✅ Implement core services
3. ✅ Add database persistence (SQLAlchemy)
4. ✅ Implement real LLM integration testing
5. ✅ Add authentication & authorization
6. ✅ Deploy to production (AWS/GCP/Azure)
7. ✅ Add monitoring (Prometheus, Datadog)
8. ✅ Implement rate limiting & quotas
