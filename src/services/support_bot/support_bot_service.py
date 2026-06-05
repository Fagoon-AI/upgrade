import os
from loguru import logger

from pathlib import Path
from typing import List, Union, Any, IO, Dict

from src.embeddings.openai_embeddings import OpenAIEmbedding
from src.loaders.pdf_loader import PDFReader

from src.schemas.llm import BaseLLMConfig
from src.schemas.document import Document
from src.schemas.enums import EmbeddingModelType

from src.services.llm import LLMService
from src.storages.vectordb_storages.pgvector import PgVectorStorage
from src.storages.vectordb_storages.base import VectorDBQuery, VectorDBQueryResult
from src.core.database.postgres import PostgresManager
from src.core.settings import system_setting

class SupportBotService:
    def __init__(
        self,
        collection_name: str,
        postgres_manager: PostgresManager,
        embedding_model_type: EmbeddingModelType = EmbeddingModelType.TEXT_EMBEDDING_3_SMALL,
        vector_storage: PgVectorStorage = None,
    ):
        self.vector_storage = vector_storage or PgVectorStorage(
            postgres_manager=postgres_manager,
            vector_dim=embedding_model_type.output_dim
        )
        self.collection_name = collection_name
        self.embeddings = OpenAIEmbedding(model_type=embedding_model_type)
        self.llm_client = LLMService()

    async def get_similar_search_results(
        self, user_query: str, top_k: int = 3, filter_conditions: Dict[str, Any] = None
    ) -> List[VectorDBQueryResult]:
        query_vector = self.embeddings.create_embedding(user_query)
        vectordb_query = VectorDBQuery(query_vector=query_vector, top_k=top_k)

        return await self.vector_storage.query(
            query=vectordb_query, 
            collection_name=self.collection_name,
            filter_conditions=filter_conditions
        )

    async def get_answer_from_support_bot(
        self,
        user_query: str,
        system_prompt: str,
        fallback_handle_response: str,
        top_k: int = 3,
        filter_conditions: dict = None,
    ):
        try:
            search_results = await self.get_similar_search_results(
                user_query=user_query,
                top_k=top_k,
                filter_conditions=filter_conditions,
            )

            contents = [result.payload.get("content", "") for result in search_results]
            
            messages = [
                {
                    "role": "system",
                    "content": f"{system_prompt}\n\nKnowledge base:\n" + "\n".join(contents),
                },
                {"role": "user", "content": user_query},
            ]

            llm_config = BaseLLMConfig(model="gpt-4o-mini", provider="openai")
            response = await self.llm_client.chat_completion(
                messages, llm_config=llm_config
            )

            return response
        except Exception as e:
            logger.error(f"Error in support bot: {e}")
            return fallback_handle_response
