import os
from loguru import logger
from dotenv import load_dotenv
from typing import Any, Optional, Literal

from src.cloud.google_storage import GCSFileStorageManager

load_dotenv()

STORAGE_MANAGER = os.getenv("DEFAULT_STORAGE_MANAGER", "GOOGLE")


class FileStorageService:
    def __init__(self, file_storage_manager: str = STORAGE_MANAGER):
        self._storage_manager = file_storage_manager
        self._manager = None

    @property
    def manager(self):
        if self._manager is None:
            if self._storage_manager.upper() == "GOOGLE":
                self._manager = GCSFileStorageManager()
            else:
                raise ValueError(
                    f"Unsupported storage manager: {self._storage_manager}"
                )
        return self._manager

    def upload_file_to_agent_folder(
        self,
        file_bytes: bytes,
        destination_path: str,
        content_type: str,
        bucket_name: Optional[str] = None,
        file_prefix: Literal["workflow", "agents", "upgrade", "users"] = "agents",
    ):
        """
        Upload binary data to Agents Directory in Google Cloud Storage
        """
        return self.upload_file(
            file_bytes=file_bytes,
            destination_path=destination_path,
            content_type=content_type,
            file_prefix=file_prefix,
            bucket_name=bucket_name,
        )

    def generate_signed_url(self, blob_name: str, expiration_in_hours: int = 24) -> Optional[str]:
        """
        Generates a v4 signed URL for a GCS blob. This method proxies the call to the storage manager.
        """
        logger.info(f"Generating signed URL for blob: {blob_name}")
        return self.manager.generate_signed_url(
            blob_name=blob_name,
            expiration_in_hours=expiration_in_hours,
        )

    def upload_file_to_workflow_folder(
        self,
        file_bytes: bytes,
        destination_path: str,
        content_type: str,
        file_prefix: Literal["workflow", "agents", "upgrade"] = "workflow",
        bucket_name: Optional[str] = None,
    ):
        """
        Upload binary data to Agents Directory in Google Cloud Storage
        """
        return self.upload_file(
            file_bytes=file_bytes,
            destination_path=destination_path,
            content_type=content_type,
            file_prefix=file_prefix,
            bucket_name=bucket_name,
        )

    def upload_file_to_upgrade_folder(
        self,
        file_bytes: bytes,
        destination_path: str,
        content_type: str,
        file_prefix: Literal["workflow", "agents", "upgrade"] = "upgrade",
        bucket_name: Optional[str] = None,
    ):
        """
        Upload binary data to Agents Directory in Google Cloud Storage
        """
        return self.upload_file(
            file_bytes=file_bytes,
            destination_path=destination_path,
            content_type=content_type,
            file_prefix=file_prefix,
            bucket_name=bucket_name,
        )

    def upload_file(
        self,
        file_bytes: bytes,
        destination_path: str,
        content_type: str,
        file_prefix: Literal['workflow', 'agents', "upgrade"],
        bucket_name: Optional[str] = None,
    ) -> str:
        """
        Uploads binary data to Google Cloud Storage.

        Args:
            file_bytes (bytes): The file content in bytes.
            destination_path (str): The path in the bucket to store the file.
            content_type (str): MIME type of the file.
            bucket_name (Optional[str]): Name of the GCS bucket (optional).

        Returns:
            str: Path of the uploaded file in GCS.
        """
        return self.manager.upload_binary_file(
            file_bytes=file_bytes,
            destination_path=destination_path,
            file_prefix=file_prefix,
            content_type=content_type,
            bucket_name=bucket_name,
        )

    def read_file(self, file_path: str, bucket_name: Optional[str] = None) -> bytes:
        """
        Reads a binary file from the specified path, optionally from a cloud storage bucket.

        Args:
            file_path (str): Path to the file to be read.
            bucket_name (Optional[str], optional): The cloud storage bucket name.

        Returns:
            bytes: The content of the file as binary data.
        """
        return self.manager.read_binary_file(
            file_path=file_path, bucket_name=bucket_name
        )

    def write_json_file(
        self,
        data: Any,
        file_path: str,
        file_prefix: Literal["workflow", "agent", "upgrade"],
    ):
        return self.manager.upload_json_data(
            data=data, destination_path=file_path, file_prefix=file_prefix
        )