from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional
from enum import Enum
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Integer, Boolean
from sqlalchemy.orm import relationship

# Make sure to import Base from the main models module when setting up Alembic
from src.models.sql.base import Base

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    CUSTOM = "custom"

class ToolModel:
    """In-memory or DB-backed tool registry. 
    Not necessarily a SQLAlchemy model if we register them in memory."""
    
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

class VibeCodeExecution(Base):
    """Represents a single code execution session"""
    __tablename__ = "vibe_code_executions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True, nullable=True) # Could be a foreign key to users table
    code = Column(String, nullable=True)
    tool_graph = Column(JSON, default=list)
    status = Column(String, default="pending")  # pending, running, completed, failed
    result = Column(JSON, nullable=True)
    error = Column(String, nullable=True)
    logs = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    def add_log(self, message: str, level: str = "info"):
        current_logs = self.logs or []
        current_logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message
        })
        self.logs = current_logs
    
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

class UserLLMConfigDB(Base):
    """Per-user LLM provider configuration"""
    __tablename__ = "user_llm_configs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False, unique=True)
    provider = Column(String, nullable=False) # e.g., "anthropic"
    model = Column(String, nullable=False)
    api_key = Column(String, nullable=True) # Encrypted
    api_base = Column(String, nullable=True)
    parameters = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "provider": self.provider,
            "model": self.model,
            "api_base": self.api_base,
            "parameters": self.parameters,
        }
