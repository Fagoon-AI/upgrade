import os
import time
import uuid
from loguru import logger
from typing import Any, List, Optional
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from src.cloud.google_storage import GCSFileStorageManager
from src.core.settings import system_setting
from src.video_generation.base import BaseVideoGenerator, BaseVideoGeneratorConfig


class VideoGenerationError(Exception):
    pass


class VeoVideoGeneratorConfig(BaseVideoGeneratorConfig):
    pass


class VeoVideoGenerator(BaseVideoGenerator):
    def __init__(self, config: VeoVideoGeneratorConfig):
        super().__init__(config)
        self._client = None
        self._gcs_manager = GCSFileStorageManager()


    def _initialize_gemini_client(self):
        if self._client is None:
            if not system_setting.GEMINI_API_KEY or system_setting.GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
                self.logger.error("GEMINI_API_KEY is not configured or is placeholder. Cannot initialize Veo client for live generation.")
                raise VideoGenerationError("Gemini API key is not configured for Veo generation.")
            try:
                self._client = genai.Client(api_key=system_setting.GEMINI_API_KEY)
                self.logger.info("Successfully initialized Gemini client for Veo model.")
            except Exception as e:
                self.logger.error(f"Failed to initialize Gemini client for live Veo generation: {e}")
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
        Generates a video using the Veo API and uploads it to GCS at the specified video_path.
        Returns the video_path (GCS URL) upon successful upload.
        """
        self.logger.info(
            f"Veo Integration: Starting live video generation for job {job_id} with prompt: '{prompt}'. Target GCS path: {video_path}"
        )

        if not system_setting.ENABLE_VEO_GENERATION:
            if system_setting.MOCK_VEO_API_IF_DISABLED:
                self.logger.warning(
                    f"Veo generation is disabled (ENABLE_VEO_GENERATION=False). "
                    f"Generating mock video for job {job_id} instead of live API call."
                )
                # In a mock scenario, you'd still want to "upload" a mock video to GCS
                # and return the designated video_path.
                # For demonstration, let's create dummy bytes and upload them.
                mock_video_bytes = b"This is a mock video content for " + prompt.encode('utf-8')
                self._gcs_manager.video_upload_from_bytes(
                    destination_blob_name=video_path,
                    file_bytes=mock_video_bytes,
                    job_id=job_id,
                    content_type="video/mp4"
                )
                self.logger.info(f"Mock video uploaded to GCS at: {video_path}")
                return video_path
            else:
                self.logger.error(
                    f"Veo generation is disabled and not mocked. "
                    f"Failing job {job_id} as per configuration."
                )
                raise VideoGenerationError("Live Veo generation is disabled by configuration.")


        try:
            client = self._initialize_gemini_client()
            duration_to_request = min(system_setting.MAX_VEO_VIDEO_DURATION_SECONDS, 5)
            num_videos_to_request = min(system_setting.MAX_VEO_GENERATIONS_PER_JOB, 1)

            video_config = types.GenerateVideosConfig(
                person_generation="dont_allow",
                aspect_ratio="16:9",
                duration_seconds=duration_to_request,
                number_of_videos=num_videos_to_request,
            )

            self.logger.info(
                f"Sending live prompt to Veo model: '{prompt}' with config: {video_config}"
            )

            operation = client.models.generate_videos(
                model=self.config.model,
                prompt=prompt,
                config=video_config,
                **kwargs,
            )

            self.logger.info(
                f"Veo Integration: Polling for live video generation completion for job {job_id} (Operation Name: {operation.name})..."
            )
            polling_interval = 10
            start_time = time.time()
            polling_timeout = 600

            while not operation.done:
                if time.time() - start_time > polling_timeout:
                    error_message = f"Veo video generation polling timed out after {polling_timeout} seconds for job {job_id}. This is a critical timeout."
                    self.logger.error(error_message)
                    raise VideoGenerationError(error_message)

                time.sleep(polling_interval)

                try:
                    operation = client.operations.get(operation)

                    progress_percent = getattr(getattr(operation, 'metadata', None), 'progress_percentage', 'N/A')
                    self.logger.debug(f"Polling update for job {job_id}: {progress_percent}% done.")
                except ClientError as ce:
                    self.logger.warning(f"Veo API error during polling for job {job_id}: {ce.message} (Code: {ce.code}). Retrying...")
                except Exception as pe:
                    error_message = (
                        f"CRITICAL: Unexpected error during polling for job {job_id}: {pe}. "
                        "Failing job as this might indicate a corrupted operation state."
                    )
                    self.logger.error(error_message, exc_info=True)
                    raise VideoGenerationError(error_message)

            if operation.error:
                error_message = (
                    f"Veo video generation failed with final error: {operation.error.message} "
                    f"(Code: {operation.error.code}). Job: {job_id}"
                )
                self.logger.error(error_message)
                raise VideoGenerationError(error_message)

            if not operation.response or not operation.response.generated_videos:
                error_message = f"Veo video generation completed but no video was returned in the response for job {job_id}."
                self.logger.error(error_message)
                raise VideoGenerationError(error_message)

            generated_video_details = operation.response.generated_videos[0]

            self._download_and_save_video(video_path, job_id, generated_video_details.video)

            return video_path

        except ClientError as e:
            self.logger.error(f"Google Veo API ClientError for job {job_id}: {e.message} (Code: {e.code})", exc_info=True)
            raise VideoGenerationError(
                f"Google Veo API error during generation or polling: {e.message} (Code: {e.code})"
            )
        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred during Veo video generation for job {job_id}: {e}",
                exc_info=True,
            )
            raise VideoGenerationError(f"Unexpected general error in Veo generation: {e}")


    def _download_and_save_video(self, destination_gcs_path: str, job_id: str, video_source: Any) -> None:
        """
        Downloads the video bytes from the Veo API and uploads them directly to GCS.
        This function does NOT return the path, as it's provided as an argument.
        """
        self.logger.info(f"Veo Integration: Downloading video from API for job {job_id}")

        try:
            client_for_download = self._client if self._client else self._initialize_gemini_client()

            downloaded_obj = client_for_download.files.download(file=video_source)

            video_bytes = None
            if hasattr(downloaded_obj, 'content') and isinstance(downloaded_obj.content, bytes):
                video_bytes = downloaded_obj.content
                self.logger.debug(f"Downloaded video as bytes directly from .content for job {job_id}.")
            elif hasattr(downloaded_obj, 'read') and callable(downloaded_obj.read):
                video_bytes = downloaded_obj.read()
                self.logger.debug(f"Downloaded video as bytes using .read() for job {job_id}.")
            elif isinstance(downloaded_obj, bytes):
                video_bytes = downloaded_obj
                self.logger.debug(f"Downloaded video is already bytes for job {job_id}.")
            else:
                raise ValueError(f"Downloaded object type {type(downloaded_obj)} does not contain video bytes for job {job_id}.")

            if video_bytes is None:
                raise ValueError(f"Failed to extract video bytes from downloaded object for job {job_id}.")

            self.logger.info(f"Veo Integration: Uploading video from memory to GCS for job {job_id} to path: {destination_gcs_path}")

            gcs_url = self._gcs_manager.video_upload_from_bytes(
                destination_blob_name=destination_gcs_path,
                file_bytes=video_bytes,
                job_id=job_id,
                content_type="video/mp4"
            )

            if gcs_url != destination_gcs_path:
                self.logger.warning(
                    f"GCSManager returned a different URL ({gcs_url}) than expected "
                    f"({destination_gcs_path}) for job {job_id}. This might indicate a configuration issue."
                )
            self.logger.info(f"Veo Integration: Video successfully uploaded to GCS: {gcs_url}")
            return

        except Exception as upload_e:
            self.logger.error(f"Failed to download/upload video from memory for job {job_id}: {upload_e}", exc_info=True)
            raise VideoGenerationError(f"Failed to stream video from Veo API to GCS: {upload_e}")
