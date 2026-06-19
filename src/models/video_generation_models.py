import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PromptSubmit(BaseModel):
    text: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="User prompt for video generation",
    )
    enhance_prompt: bool = Field(
        default=False, description="Whether to enhance the prompt using AI"
    )


class JobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ENHANCING = "ENHANCING_PROMPT"
    

class VideoJobBase(BaseModel):
    original_prompt: str
    user_id: Optional[str] = None
    enhanced_prompt: Optional[str] = None
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    error_message: Optional[str] = None
    video_url: Optional[str] = None
    file_path: Optional[str] = None


class VideoJobCreate(VideoJobBase):
    pass


class VideoJob(VideoJobBase):
    id: str = Field(alias="_id", default_factory=lambda: str(uuid.uuid4()))

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                "original_prompt": "A futuristic city at sunset with flying cars.",
                "enhanced_prompt": "A cyberpunk metropolis at twilight, neon signs reflecting on wet asphalt, sleek flying vehicles zipping between towering skyscrapers, cinematic wide shot.",
                "status": "PROCESSING",
                "progress": 50,
                "error_message": None,
                "video_url": None,
                "file_path": None,
            }
        }


class JobSubmissionResponse(BaseModel):
    job_id: str
    video_path: str
    message: str
    status_endpoint: str
    websocket_endpoint: Optional[str] = None
