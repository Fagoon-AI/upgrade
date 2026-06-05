import httpx
from pydantic import BaseModel, Field
from typing import List, Optional

from src.schemas.chat import ChatCompletionInputRequest
from src.schemas.users import Preference
from src.models.auth_models.user_model import UserInDB
from src.services.nosql.postgres_services import PostgresServices
from src.services.crawl4ai_service import Crawl4AIService
from src.core.database.postgres import PostgresManager

class ChatContext(BaseModel):
    """
    Encapsulates all contextual information for a single chat stream request.
    This makes passing request-specific state between services clean and simple.
    """
    request: ChatCompletionInputRequest
    user: UserInDB
    user_preferences: Preference
    db_services: "PostgresServices"
    postgres_manager: "PostgresManager"
    user_id: str = Field(..., description="The ID of the user initiating the request.")
    http_client: httpx.AsyncClient
    crawl_service: Crawl4AIService

    class Config:
        arbitrary_types_allowed = True

ChatContext.model_rebuild()
