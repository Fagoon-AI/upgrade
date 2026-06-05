from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional

class FileReference(BaseModel):
    file_id: str = Field(..., description="Unique identifier for the file reference.")
    conversation_id: str = Field(..., description="The conversation this file belongs to.")
    user_id: str = Field(..., description="The user who uploaded the file.")
    gcs_path: str = Field(..., description="The full path to the file in Google Cloud Storage.")
    filename: str = Field(..., description="The original name of the uploaded file.")
    mime_type: str = Field(..., description="The MIME type of the file.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))