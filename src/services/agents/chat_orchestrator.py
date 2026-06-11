from typing import Any, AsyncGenerator, Dict, List, Optional
import uuid
import asyncio
from loguru import logger

from src.agents.agent_manager import AgentManager
from src.services.agents.chat import AgentChatService
from src.storages.vectordb_storages.pgvector import PgVectorStorage
from src.services.llm import LLMService
from src.schemas.llm import BaseLLMConfig
from src.services.map_model_provider import get_model_provider
from src.storages.vectordb_storages.base import VectorDBQuery
from src.core.settings import system_setting

class ChatOrchestrator:
    def __init__(
        self,
        agent_manager: AgentManager,
        vector_store: PgVectorStorage,
        chat_service: AgentChatService
    ):
        self.agent_manager = agent_manager
        self.vector_store = vector_store
        self.chat_service = chat_service

    def _build_llm_service_for_agent(self, agent: dict) -> LLMService:
        model_settings = agent.get("model_settings") or {}
        model = model_settings.get("llm_model") or system_setting.SMART_MODEL_ID
        provider = model_settings.get("provider")

        if not provider:
            try:
                provider = get_model_provider(model)
            except ValueError:
                provider = system_setting.SMART_MODEL_PROVIDER

        llm_config = BaseLLMConfig(
            model=model,
            provider=provider,
            temperature=model_settings.get("temperature", 0.1),
            top_p=model_settings.get("top_p", 0.1),
            max_tokens=model_settings.get("max_tokens"),
            api_key=model_settings.get("api_key"),
        )
        return LLMService(llm_config)

    async def stream_chat(
        self,
        user_id: str,
        agent_id: str,
        history_id: str,
        message: str,
        llm_config: Optional[BaseLLMConfig] = None
    ) -> AsyncGenerator[str, None]:
        # 1. Get Agent
        agent = await self.agent_manager.get_agent(agent_id)
        if not agent:
            yield "Agent not found."
            return

        # 2. RAG Retrieval
        llm_service = self._build_llm_service_for_agent(agent)
        collection_name = f"agent_{agent_id}"
        query_vector = await llm_service.get_embeddings(message)

        vector_query = VectorDBQuery(query_vector=query_vector, top_k=5)
        search_results = await self.vector_store.query(vector_query, collection_name)

        context = "\n".join([res.payload.get("content", "") for res in search_results])

        # 3. Construct Prompt
        system_prompt = agent.get("instructions", "You are a helpful assistant.")
        full_prompt = f"Context:\n{context}\n\nUser Message: {message}"

        # 4. Save User Message
        await self.chat_service.add_message(history_id, "user", message)

        # 5. Stream from LLM
        full_response = ""
        async for token in llm_service.stream_response(system_prompt, full_prompt, llm_config):
            full_response += token
            yield token

        # 6. Save AI Message
        await self.chat_service.add_message(history_id, "assistant", full_response)
