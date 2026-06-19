from pydantic import BaseModel, Field
from typing import List, Optional
from fastapi import UploadFile, Form, File


class UpgradeChatFile(BaseModel):
    filename: str
    content: str
    mime_type: str


class ChatCompletionInputRequest(BaseModel):
    # user_id: str = Field(..., description="The ID of the user making the request")
    conversation_id: str = Field(..., description="The ID of the conversation")
    message: str = Field(..., description="User latest query for chat completion")
    internet_search: Optional[bool] = Field(default=False, description="Enable internet search")
    selected_model: Optional[str] = Field(default=None, description="The selected model for the chat")
    is_reasoning: Optional[bool] = Field(default=False, description="Indicates if reasoning is enabled")
    web_search_enabled: bool = False
    generate_audio: bool = Field(False, description="Flag to generate audio for the assistant's response.")
    file_ids: Optional[List[str]] = Field(default=None, description="List of file IDs to be used as context.")
    file_data: Optional[str] = Field(default=None, description="Base64 encoded file content")
    file_name: Optional[str] = Field(default=None, description="Name of the uploaded file")

