from openai import OpenAI
from openai._types import NOT_GIVEN, NotGiven
from src.embeddings.base import BaseEmbedding
from src.schemas.enums import EmbeddingModelType
import os
from typing import Any


class OpenAIEmbedding(BaseEmbedding[str]):
    provider_name = "openai"

    def __init__(
        self,
        model_type: EmbeddingModelType,
        url: str | None = None,
        api_key: str | None = None,
        dimensions: int | NotGiven = NOT_GIVEN,
    ):
        if not model_type.is_openai:
            raise ValueError(f"{model_type=} is not an OpenAI model.")
        self.model_type = model_type
        self.output_dim = (
            model_type.output_dim if dimensions == NOT_GIVEN else dimensions
        )

        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._url = url or os.getenv("OPENAI_API_BASE_URL")

        self.client = OpenAI(
            api_key=self._api_key, base_url=self._url, timeout=180, max_retries=3
        )

    def embed_list(self, objs: list[str], **kwargs: Any) -> list[list[float]]:
        if self.model_type == EmbeddingModelType.TEXT_EMBEDDING_ADA_2:
            response = self.client.embeddings.create(
                input=objs, model=self.model_type.value, **kwargs
            )
        else:
            response = self.client.embeddings.create(
                input=objs,
                model=self.model_type.value,
                dimensions=self.output_dim,
                **kwargs,
            )
        return [data.embedding for data in response.data]

    def get_output_dim(self) -> int:
        return self.output_dim

    def create_embedding(self, text: str, **kwargs: Any) -> list[float]:
        embedding = self.embed_list([text], **kwargs)
        return embedding[0]
