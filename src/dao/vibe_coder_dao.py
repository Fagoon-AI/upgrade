from typing import Dict, List, Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.models.sql.vibe_coder_models import ToolModel, VibeCodeExecution, UserLLMConfigDB

logger = logging.getLogger(__name__)

class ToolRegistryDAO:
    """In-memory tool registry (acts as a DAO for tools)"""
    
    def __init__(self):
        self._tools: Dict[str, ToolModel] = {}
    
    def register_tool(self, tool: ToolModel):
        """Register a new tool"""
        self._tools[tool.id] = tool
        logger.info(f"Registered tool: {tool.id}")
    
    def get_tool(self, tool_id: str) -> Optional[ToolModel]:
        """Retrieve a tool by ID"""
        return self._tools.get(tool_id)
    
    def list_tools(self, category: Optional[str] = None) -> List[ToolModel]:
        """List all tools, optionally filtered by category"""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools
    
    def list_enabled_tools(self) -> List[ToolModel]:
        """List only enabled tools"""
        return [t for t in self._tools.values() if t.enabled]


class VibeCodeExecutionDAO:
    """Data Access Object for Vibe Code Executions and LLM Configs"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_execution(self, execution: VibeCodeExecution) -> VibeCodeExecution:
        """Create or update an execution session"""
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)
        return execution

    async def get_execution(self, execution_id: str) -> Optional[VibeCodeExecution]:
        """Retrieve an execution by ID"""
        result = await self.db.execute(
            select(VibeCodeExecution).where(VibeCodeExecution.id == execution_id)
        )
        return result.scalars().first()

    async def get_user_llm_config(self, user_id: str) -> Optional[UserLLMConfigDB]:
        """Fetch user's custom LLM configuration"""
        result = await self.db.execute(
            select(UserLLMConfigDB).where(UserLLMConfigDB.user_id == user_id)
        )
        return result.scalars().first()
        
    async def save_user_llm_config(self, config: UserLLMConfigDB) -> UserLLMConfigDB:
        """Create or update user LLM config"""
        existing = await self.get_user_llm_config(config.user_id)
        if existing:
            existing.provider = config.provider
            existing.model = config.model
            existing.api_key = config.api_key
            existing.api_base = config.api_base
            existing.parameters = config.parameters
            self.db.add(existing)
        else:
            self.db.add(config)
            
        await self.db.commit()
        return config
