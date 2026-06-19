import os
import time
import uuid
from typing import Any, Optional
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from src.core.settings import system_setting
from src.video_generation.base import BaseVideoGenerator, BaseVideoGeneratorConfig


class VideoGenerationError(Exception):
    pass


class VeoVideoGeneratorConfig(BaseVideoGeneratorConfig):
    user_id: Optional[uuid.UUID] = None
    api_key: Optional[str] = None


class VeoVideoGenerator(BaseVideoGenerator):
    def __init__(self, config: VeoVideoGeneratorConfig):
        super().__init__(config)
        self._client = None


    def _initialize_gemini_client(self):
        if self._client is None:
            api_key = getattr(self.config, "api_key", None) or system_setting.GEMINI_API_KEY
            if not api_key or api_key == "YOUR_GEMINI_API_KEY":
                self.logger.error("GEMINI_API_KEY is not configured or is placeholder. Cannot initialize Veo client for live generation.")
                raise VideoGenerationError("Gemini API key is not configured for Veo generation.")
            try:
                self._client = genai.Client(api_key=api_key)
                self.logger.info("Successfully initialized Gemini client for Veo model.")
            except Exception as e:
                self.logger.error("Failed to initialize Gemini client for live Veo generation: {}", e)
                raise VideoGenerationError(f"Failed to initialize Gemini client for Veo: {e}")
        return self._client


    def generate_video(
            self,
            video_path: str,
            job_id: str,
            prompt: str,
            **kwargs: Any,
    ) -> str:
        """
        Generates a video using the Veo API and saves it locally.
        Returns the local file path upon successful download.
        """
        self.logger.info(
            "Veo Integration: Starting video generation for job {} with prompt: '{}'.",
            job_id, prompt
        )

        if not system_setting.ENABLE_VEO_GENERATION:
            if system_setting.MOCK_VEO_API_IF_DISABLED:
                self.logger.warning(
                    "Veo generation is disabled (ENABLE_VEO_GENERATION=False). "
                    "Generating mock video locally for job {} instead of live API call.",
                    job_id
                )
                mock_video_bytes = b"This is a mock video content for " + prompt.encode('utf-8')
                os.makedirs("outputs", exist_ok=True)
                local_path = f"outputs/{job_id}.mp4"
                with open(local_path, "wb") as f:
                    f.write(mock_video_bytes)
                self.logger.info("Mock video saved locally at: {}", local_path)
                return local_path
            else:
                self.logger.error(
                    "Veo generation is disabled and not mocked. "
                    "Failing job {} as per configuration.",
                    job_id
                )
                raise VideoGenerationError("Live Veo generation is disabled by configuration.")


        try:
            client = self._initialize_gemini_client()
            duration_to_request = min(system_setting.MAX_VEO_VIDEO_DURATION_SECONDS, 5)
            num_videos_to_request = min(system_setting.MAX_VEO_GENERATIONS_PER_JOB, 1)

            video_config = types.GenerateVideosConfig(
                person_generation="allow_adult",
                aspect_ratio="16:9",
                duration_seconds=duration_to_request,
                number_of_videos=num_videos_to_request,
            )

            self.logger.info(
                "Sending live prompt to Veo model: '{}' with config: {}",
                prompt, video_config
            )

            operation = client.models.generate_videos(
                model=self.config.model,
                prompt=prompt,
                config=video_config,
                **kwargs,
            )

            self.logger.info(
                "Veo Integration: Polling for live video generation completion for job {} (Operation Name: {})...",
                job_id, operation.name
            )
            polling_interval = 10
            start_time = time.time()
            polling_timeout = 600

            while not operation.done:
                if time.time() - start_time > polling_timeout:
                    self.logger.error(
                        "Veo video generation polling timed out after {} seconds for job {}. This is a critical timeout.",
                        polling_timeout, job_id
                    )
                    raise VideoGenerationError(f"Veo video generation polling timed out after {polling_timeout} seconds for job {job_id}. This is a critical timeout.")

                time.sleep(polling_interval)

                try:
                    operation = client.operations.get(operation)

                    progress_percent = getattr(getattr(operation, 'metadata', None), 'progress_percentage', 'N/A')
                    self.logger.debug("Polling update for job {}: {}% done.", job_id, progress_percent)
                except ClientError as ce:
                    self.logger.warning("Veo API error during polling for job {}: {} (Code: {}). Retrying...", job_id, ce.message, ce.code)
                except Exception as pe:
                    self.logger.error(
                        "CRITICAL: Unexpected error during polling for job {}: {}. Failing job as this might indicate a corrupted operation state.",
                        job_id, pe, exc_info=True
                    )
                    raise VideoGenerationError(f"CRITICAL: Unexpected error during polling for job {job_id}: {pe}. Failing job as this might indicate a corrupted operation state.")

            if operation.error:
                error_msg = operation.error.get("message") if isinstance(operation.error, dict) else getattr(operation.error, "message", str(operation.error))
                error_code = operation.error.get("code") if isinstance(operation.error, dict) else getattr(operation.error, "code", "Unknown")
                self.logger.error(
                    "Veo video generation failed with final error: {} (Code: {}). Job: {}",
                    error_msg, error_code, job_id
                )
                raise VideoGenerationError(f"Veo video generation failed with final error: {error_msg} (Code: {error_code}). Job: {job_id}")

            if not operation.response or not operation.response.generated_videos:
                self.logger.error("Veo video generation completed but no video was returned in the response for job {}. Full response: {}", job_id, getattr(operation, 'response', None))
                raise VideoGenerationError(
                    "Veo video generation completed, but no video was returned. "
                    "This usually occurs if the prompt was filtered or blocked by Google's strict safety, copyright, or person-generation policy filters "
                    "(e.g. requesting real people, copyrighted characters like Spiderman, or other policy-restricted content)."
                )

            generated_video_details = operation.response.generated_videos[0]

            local_path = self._download_and_save_video(job_id, generated_video_details.video)

            return local_path

        except ClientError as e:
            self.logger.error("Google Veo API ClientError for job {}: {} (Code: {})", job_id, e.message, e.code, exc_info=True)
            raise VideoGenerationError(
                f"Google Veo API error during generation or polling: {e.message} (Code: {e.code})"
            )
        except Exception as e:
            self.logger.error(
                "An unexpected error occurred during Veo video generation for job {}: {}",
                job_id, e, exc_info=True,
            )
            raise VideoGenerationError(f"Unexpected general error in Veo generation: {e}")


    def _download_and_save_video(self, job_id: str, video_source: Any) -> str:
        """
        Downloads the video bytes from the Veo API and saves them locally.
        Returns the local file path.
        """
        self.logger.info("Veo Integration: Downloading video from API for job {}", job_id)

        try:
            client_for_download = self._client if self._client else self._initialize_gemini_client()

            downloaded_obj = client_for_download.files.download(file=video_source)

            video_bytes = None
            if hasattr(downloaded_obj, 'content') and isinstance(downloaded_obj.content, bytes):
                video_bytes = downloaded_obj.content
                self.logger.debug("Downloaded video as bytes directly from .content for job {}.", job_id)
            elif hasattr(downloaded_obj, 'read') and callable(downloaded_obj.read):
                video_bytes = downloaded_obj.read()
                self.logger.debug("Downloaded video as bytes using .read() for job {}.", job_id)
            elif isinstance(downloaded_obj, bytes):
                video_bytes = downloaded_obj
                self.logger.debug("Downloaded video is already bytes for job {}.", job_id)
            else:
                raise ValueError(f"Downloaded object type {type(downloaded_obj)} does not contain video bytes for job {job_id}.")

            if video_bytes is None:
                raise ValueError(f"Failed to extract video bytes from downloaded object for job {job_id}.")

            os.makedirs("outputs", exist_ok=True)
            local_path = f"outputs/{job_id}.mp4"
            with open(local_path, "wb") as f:
                f.write(video_bytes)

            self.logger.info("Veo Integration: Video successfully saved locally to {}", local_path)
            return local_path

        except Exception as e:
            self.logger.error("Failed to download and save video locally for job {}: {}", job_id, e, exc_info=True)
            raise VideoGenerationError(f"Failed to download and save video locally: {e}")
