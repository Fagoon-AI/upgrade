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
from src.services.agents.llm_tasks import generate_general_chat_response, generate_general_response

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

    async def _build_llm_service_for_agent(self, agent_id: str, agent: Any, user_id: str) -> tuple[LLMService, str]:
        """
        Safely builds an LLMService instance by resolving model settings 
        nested deep inside an agent's 'config' field layer.
        """
        model = system_setting.SMART_MODEL_ID
        provider = None
        temperature = 0.1
        top_p = 0.1
        max_tokens = None
        api_key = None

        config_data = {}
        if isinstance(agent, dict):
            config_data = agent.get("config") or agent.get("model_settings") or agent
        else:
            config_data = getattr(agent, "config", None) or getattr(agent, "model_settings", None) or agent

        model_settings = {}
        if isinstance(config_data, dict):
            model_settings = config_data.get("model_settings") or config_data
        elif config_data is not None:
            model_settings = getattr(config_data, "model_settings", config_data)

        if model_settings and hasattr(model_settings, "model_dump"):
            model_settings = model_settings.model_dump()
        elif not isinstance(model_settings, dict):
            model_settings = {}

        model = model_settings.get("llm_model") or model_settings.get("model") or model
        provider = model_settings.get("provider")

        # Guardrail: Handle generic model IDs to map to proper working model IDs
        if provider:
            provider_lower = provider.lower()
            if provider_lower == "gemini" and model in ("gemini", None, ""):
                model = "gemini-1.5-flash"
            elif provider_lower == "openai" and model in ("openai", None, ""):
                model = "gpt-4o-mini"
            elif provider_lower == "groq" and model in ("groq", None, ""):
                model = "llama-3.3-70b-versatile"

        temperature = model_settings.get("temperature", temperature)
        top_p = model_settings.get("top_p", top_p)
        max_tokens = model_settings.get("max_tokens", max_tokens)
        api_key = model_settings.get("api_key")

        if not provider and model:
            try:
                provider = get_model_provider(model)
            except ValueError:
                provider = system_setting.SMART_MODEL_PROVIDER

        # Resolve user's API key for agents
        from src.services.api_key_resolver import resolve_api_key
        try:
            resolved_api_key = await resolve_api_key(
                user_id=uuid.UUID(str(user_id)),
                provider=provider,
                feature="agents",
                specific_id=agent_id
            )
            if resolved_api_key:
                api_key = resolved_api_key
        except Exception as e:
            logger.error(f"Failed to resolve custom API key: {e}")

        logger.info(
            f"[Key Resolution] Agent: {agent_id}. "
            f"Model: {model} | Provider: {provider} | "
            f"Using Custom Database Key: {bool(api_key)}"
        )

        llm_config = BaseLLMConfig(
            model=model,
            provider=provider,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            api_key=api_key,
        )
        return LLMService(llm_config), model

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

        # 2. Build Text Generation Service
        llm_service, model_name = await self._build_llm_service_for_agent(agent_id, agent, user_id)
        collection_name = f"agent_{agent_id}"
        
        # 3. Clean RAG Retrieval Layer (Zero external fallbacks to error out on)
        context = ""
        try:
            query_vector = await llm_service.get_embeddings(message)
            vector_query = VectorDBQuery(query_vector=query_vector, top_k=5)
            search_results = await self.vector_store.query(vector_query, collection_name)
            context = "\n".join([res.payload.get("content", "") for res in search_results])
        except Exception:
            # Silently catch the missing embedding implementation and proceed cleanly
            logger.info("Skipping knowledge retrieval layer for this model turn. Proceeding directly to chat.")
            context = ""

        # 4. Construct Prompt
       # 4. Construct Prompt with Strict RAG Guardrails
        base_instructions = agent.instructions if hasattr(agent, "instructions") else agent.get("instructions", "You are a helpful assistant.")

        if context:
            # When documents ARE found in the database
            guardrail_rules = (
                "\n\n--- KNOWLEDGE BASE GUARDRAILS ---\n"
                "1. You may naturally answer greetings and questions about your identity, role, or company services as defined in your base instructions.\n"
                "2. For specific user queries, you MUST base your answers primarily on the 'Knowledge Base Context' provided below.\n"
                "3. If the user asks a factual question that is NOT covered by your base instructions or the context below, DO NOT hallucinate or use outside knowledge. Reply with: 'I apologize, but I can only answer questions related to my specific expertise, and I do not have information about that.'\n"
                "-----------------------------------\n"
                f"\nKnowledge Base Context:\n{context}"
            )
        else:
            # When NO documents are found (or RAG is skipped)
            guardrail_rules = (
                "\n\n--- OPERATING RULES ---\n"
                "1. You may naturally answer basic greetings, pleasantries, and questions about your identity, role, company, and services based STRICTLY on your base instructions.\n"
                "2. If the user asks a specific factual question that goes beyond your base instructions, DO NOT guess or use general internet knowledge. You must reply with: 'I apologize, but I can only answer questions related to my specific expertise, and I do not have information about that.'\n"
                "-----------------------------------\n"
            )

        system_prompt = f"{base_instructions}{guardrail_rules}"

        # 5. Save User Message
        await self.chat_service.add_message(history_id, "user", message)

        # 6. Fetch Conversational History
        db_history = await self.chat_service.get_history(history_id)
        
        messages = [{"role": "system", "content": system_prompt}]
        for msg in db_history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

        # 7. Stream from LLM Task Layer
        full_response = ""
        try:
            async for token in generate_general_response(
                messages=messages, llm_config=llm_service.config
            ):
                full_response += token
                yield token
        except Exception as stream_err:
            logger.error(f"Streaming failed: {stream_err}")
            yield f"Error during streaming generation: {str(stream_err)}"
            return

        # 8. Save AI Response
        await self.chat_service.add_message(history_id, "assistant", full_response)