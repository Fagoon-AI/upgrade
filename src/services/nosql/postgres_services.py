from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type
import uuid
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.models.sql.models import (
    User,
    Agent,
    AgentChatHistory,
    AgentChat,
    UpgradeChatHistory,
    UpgradeChat,
    VideoJob,
    FileReference,
    DocumentChunk,
    GoogleToken,
    RefreshToken,
    LLMModelConfig,
)

class PostgresServices:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def create_user(self, user_data: Dict[str, Any]) -> User:
        user = User(**user_data)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_agent_by_id(self, agent_id: uuid.UUID) -> Optional[Agent]:
        return await self.session.get(Agent, agent_id)

    async def get_all_agents_by_user_id(self, user_id: uuid.UUID) -> List[Agent]:
        stmt = select(Agent).where(Agent.user_id == user_id, Agent.is_deleted == False)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_llm_model_config(self, model_config_data: Dict[str, Any]) -> LLMModelConfig:
        model_config = LLMModelConfig(**model_config_data)
        self.session.add(model_config)
        await self.session.commit()
        await self.session.refresh(model_config)
        return model_config

    async def get_llm_model_config_by_id(
        self,
        config_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[LLMModelConfig]:
        stmt = select(LLMModelConfig).where(
            LLMModelConfig.id == config_id,
            LLMModelConfig.user_id == user_id,
            LLMModelConfig.is_deleted == False,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_llm_model_configs_by_user_id(self, user_id: uuid.UUID) -> List[LLMModelConfig]:
        stmt = select(LLMModelConfig).where(
            LLMModelConfig.user_id == user_id,
            LLMModelConfig.is_deleted == False,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_llm_model_config(
        self,
        config_id: uuid.UUID,
        user_id: uuid.UUID,
        update_data: Dict[str, Any],
    ) -> Optional[LLMModelConfig]:
        stmt = update(LLMModelConfig).where(
            LLMModelConfig.id == config_id,
            LLMModelConfig.user_id == user_id,
            LLMModelConfig.is_deleted == False,
        ).values(**update_data)
        result = await self.session.execute(stmt)
        await self.session.commit()
        if result.rowcount == 0:
            return None
        return await self.get_llm_model_config_by_id(config_id, user_id)

    async def soft_delete_llm_model_config(
        self,
        config_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        stmt = update(LLMModelConfig).where(
            LLMModelConfig.id == config_id,
            LLMModelConfig.user_id == user_id,
            LLMModelConfig.is_deleted == False,
        ).values(is_deleted=True, updated_at=datetime.now(timezone.utc))
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def create_agent(self, agent_data: Dict[str, Any]) -> Agent:
        agent = Agent(**agent_data)
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def update_agent(self, agent_id: uuid.UUID, update_data: Dict[str, Any]) -> bool:
        stmt = update(Agent).where(Agent.id == agent_id).values(**update_data)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def delete_agent(self, agent_id: uuid.UUID) -> bool:
        return await self.update_agent(agent_id, {"is_deleted": True, "updated_at": datetime.now(timezone.utc)})

    async def create_agent_chat_history(self, history_data: Dict[str, Any]) -> AgentChatHistory:
        history = AgentChatHistory(**history_data)
        self.session.add(history)
        await self.session.commit()
        await self.session.refresh(history)
        return history

    async def insert_agent_message(self, chat_data: Dict[str, Any]) -> AgentChat:
        chat = AgentChat(**chat_data)
        self.session.add(chat)
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def get_agent_conversation_history(self, history_id: uuid.UUID) -> List[AgentChat]:
        stmt = select(AgentChat).where(AgentChat.history_id == history_id).order_by(AgentChat.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_video_job(self, job_data: Dict[str, Any]) -> VideoJob:
        job = VideoJob(**job_data)
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_video_job(self, job_id: uuid.UUID) -> Optional[VideoJob]:
        return await self.session.get(VideoJob, job_id)

    async def update_video_job(self, job_id: uuid.UUID, update_data: Dict[str, Any]) -> Optional[VideoJob]:
        stmt = update(VideoJob).where(VideoJob.id == job_id).values(**update_data)
        await self.session.execute(stmt)
        await self.session.commit()
        return await self.get_video_job(job_id)

    async def insert_file_reference(self, file_ref_data: Dict[str, Any]) -> FileReference:
        file_ref = FileReference(**file_ref_data)
        self.session.add(file_ref)
        await self.session.commit()
        await self.session.refresh(file_ref)
        return file_ref

    async def get_file_references_by_ids(self, file_ids: List[str]) -> List[FileReference]:
        stmt = select(FileReference).where(FileReference.file_id.in_(file_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
