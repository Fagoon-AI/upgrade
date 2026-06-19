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
    code: Optional[str] = None  # Generated TypeScript code, can be empty initially
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

class LLMMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class CodeGenerationRequest(BaseModel):
    user_prompt: str
    available_tools: List[str] = []  # Default to empty for Option B
    conversation_history: List[LLMMessage] = []
    user_preferences: Optional[Dict[str, Any]] = None
    llm_config_id: str

class CodeGenerationResponse(BaseModel):
    code: str  # Generated TypeScript
    tool_graph_plan: Optional[List[Dict[str, Any]]] = None
    explanation: Optional[str] = None
