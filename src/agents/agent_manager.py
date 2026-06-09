from datetime import datetime, timezone
from typing import List, Optional, Any, Dict
import asyncio
import uuid
from loguru import logger
from src.storages.file_storage import FileStorageService
from src.schemas.agents import AgentDefaultModel, AgentUpdateModel
from src.core.database.postgres import PostgresManager
from src.services.nosql.postgres_services import PostgresServices
from sqlalchemy import select, update, delete

class AgentManager:
    def __init__(self, postgres_manager: PostgresManager, file_storage: FileStorageService):
        self.postgres_manager = postgres_manager
        self.file_storage = file_storage
        logger.info("AgentManager initialized with PostgreSQL.")

    async def create_agent(self, user_id: str, agent_data: AgentDefaultModel) -> Dict[str, Any]:
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid user_id provided to create_agent: {user_id}")
            raise ValueError("Invalid user ID format. UUID expected.")

        async with self.postgres_manager.get_session() as session:
            pg_services = PostgresServices(session)
            
            agent_dict = {
                "id": uuid.uuid4(),
                "user_id": user_uuid,
                "name": agent_data.name,
                "instructions": agent_data.instructions,
                "config": agent_data.model_dump(exclude={"name", "instructions"}),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            
            sql_agent = await pg_services.create_agent(agent_dict)
            return {
                "id": str(sql_agent.id),
                "name": sql_agent.name,
                "instructions": sql_agent.instructions,
                **sql_agent.config
            }

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        try:
            agent_uuid = uuid.UUID(agent_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid agent_id provided to get_agent: {agent_id}")
            return None

        async with self.postgres_manager.get_session() as session:
            pg_services = PostgresServices(session)
            sql_agent = await pg_services.get_agent_by_id(agent_uuid)
            if sql_agent and not sql_agent.is_deleted:
                return {
                    "id": str(sql_agent.id),
                    "name": sql_agent.name,
                    "instructions": sql_agent.instructions,
                    **sql_agent.config
                }
        return None

    async def list_agents(self, user_id: str) -> List[Dict[str, Any]]:
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid user_id provided to list_agents: {user_id}")
            return []

        async with self.postgres_manager.get_session() as session:
            pg_services = PostgresServices(session)
            sql_agents = await pg_services.get_all_agents_by_user_id(user_uuid)
            return [
                {
                    "id": str(agent.id),
                    "name": agent.name,
                    "instructions": agent.instructions,
                    **agent.config
                } for agent in sql_agents
            ]

    async def update_agent(self, agent_id: str, update_data: AgentUpdateModel) -> bool:
        try:
            agent_uuid = uuid.UUID(agent_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid agent_id provided to update_agent: {agent_id}")
            return False

        async with self.postgres_manager.get_session() as session:
            pg_services = PostgresServices(session)
            data = update_data.model_dump(exclude_unset=True)
            if not data:
                return False
            
            # Split standard fields from config
            std_fields = {"name", "instructions"}
            update_dict = {k: v for k, v in data.items() if k in std_fields}
            config_updates = {k: v for k, v in data.items() if k not in std_fields}
            
            if config_updates:
                # In a real app, you'd merge JSONB. For simplicity here:
                sql_agent = await pg_services.get_agent_by_id(agent_uuid)
                if sql_agent:
                    new_config = {**sql_agent.config, **config_updates}
                    update_dict["config"] = new_config

            update_dict["updated_at"] = datetime.now(timezone.utc)
            return await pg_services.update_agent(agent_uuid, update_dict)

    async def delete_agent(self, agent_id: str) -> bool:
        try:
            agent_uuid = uuid.UUID(agent_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid agent_id provided to delete_agent: {agent_id}")
            return False

        async with self.postgres_manager.get_session() as session:
            pg_services = PostgresServices(session)
            return await pg_services.delete_agent(agent_uuid)
