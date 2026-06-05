from loguru import logger
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field



class BaseVideoGeneratorConfig(BaseModel):
    model: str = Field(..., description="The specific model ID to use for video generation (e.g., 'veo-2.0-generate-001').")

    class Config:
        extra = "allow"


class BaseVideoGenerator(ABC):
    def __init__(self, config: BaseVideoGeneratorConfig):
        self.config = config
        self.logger = logger.bind(class_name=self.__class__.__name__)

    @abstractmethod
    def generate_video(
        self,
        job_id: str,
        prompt: str,
        **kwargs: Any,
    ) -> str:

        pass

    @abstractmethod
    def _download_and_save_video(self, job_id: str, video_source: Any) -> str:
        pass