import asyncio
import json
import hashlib
import mimetypes
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, BinaryIO, Union
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from src.core.config import settings


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class StorageConfig:
    """Configuration for storage service."""
    max_file_size_mb: int = 100
    default_expiration_minutes: int = 60
    max_expiration_minutes: int = 1440  # 24 hours
    max_retries: int = 3
    retry_delay: float = 1.0
    chunk_size: int = 8 * 1024 * 1024  # 8MB chunks
    local_storage_path: str = "/tmp/workflow_artifacts"


# ============================================================
# STORAGE BACKENDS
# ============================================================

class StorageBackend:
    """Base class for storage backends."""

    async def upload(
            self,
            path: str,
            content: Union[str, bytes],
            content_type: str = "text/plain"
    ) -> Optional[str]:
        raise NotImplementedError

    async def download(self, path: str) -> Optional[str]:
        raise NotImplementedError

    async def delete(self, path: str) -> bool:
        raise NotImplementedError

    async def exists(self, path: str) -> bool:
        raise NotImplementedError

    def generate_signed_url(
            self,
            path: str,
            expiration_minutes: int = 60
    ) -> Optional[str]:
        raise NotImplementedError


class GCSBackend(StorageBackend):
    """Google Cloud Storage backend."""

    def __init__(self, bucket_name: str, config: StorageConfig):
        self.bucket_name = bucket_name
        self.config = config
        self.client = None
        self.bucket = None
        self._initialized = False

    def _initialize(self) -> bool:
        """Lazy initialization of GCS client."""
        if self._initialized:
            return self.bucket is not None

        self._initialized = True

        try:
            from google.cloud import storage
            self.client = storage.Client()
            self.bucket = self.client.bucket(self.bucket_name)
            logger.info(f"GCS initialized: {self.bucket_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize GCS: {e}")
            return False

    async def upload(
            self,
            path: str,
            content: Union[str, bytes],
            content_type: str = "text/plain"
    ) -> Optional[str]:
        """Uploads content to GCS with retry."""
        if not self._initialize():
            return None

        # Convert string to bytes
        if isinstance(content, str):
            content = content.encode('utf-8')

        # Check size
        size_mb = len(content) / (1024 * 1024)
        if size_mb > self.config.max_file_size_mb:
            logger.error(f"File too large: {size_mb:.2f}MB")
            return None

        blob = self.bucket.blob(path)

        for attempt in range(1, self.config.max_retries + 1):
            try:
                await asyncio.to_thread(
                    blob.upload_from_string,
                    content,
                    content_type=content_type
                )

                uri = f"gs://{self.bucket_name}/{path}"
                logger.debug(f"Uploaded: {uri}")
                return uri

            except Exception as e:
                logger.warning(f"Upload attempt {attempt} failed: {e}")
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay * attempt)

        return None

    async def download(self, path: str) -> Optional[str]:
        """Downloads content from GCS."""
        if not self._initialize():
            return None

        blob = self.bucket.blob(path)

        for attempt in range(1, self.config.max_retries + 1):
            try:
                content = await asyncio.to_thread(blob.download_as_text)
                return content
            except Exception as e:
                logger.warning(f"Download attempt {attempt} failed: {e}")
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay * attempt)

        return None

    async def delete(self, path: str) -> bool:
        """Deletes a blob from GCS."""
        if not self._initialize():
            return False

        try:
            blob = self.bucket.blob(path)
            await asyncio.to_thread(blob.delete)
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False

    async def exists(self, path: str) -> bool:
        """Checks if blob exists."""
        if not self._initialize():
            return False

        try:
            blob = self.bucket.blob(path)
            return await asyncio.to_thread(blob.exists)
        except Exception:
            return False

    def generate_signed_url(
            self,
            path: str,
            expiration_minutes: int = 60
    ) -> Optional[str]:
        """Generates a signed URL for temporary access."""
        if not self._initialize():
            return None

        expiration_minutes = min(
            expiration_minutes,
            self.config.max_expiration_minutes
        )

        try:
            blob = self.bucket.blob(path)
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="GET"
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate signed URL: {e}")
            return None


class LocalBackend(StorageBackend):
    """Local filesystem backend for development."""

    def __init__(self, base_path: str, config: StorageConfig):
        self.base_path = Path(base_path)
        self.config = config
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        """Gets full filesystem path."""
        return self.base_path / path

    async def upload(
            self,
            path: str,
            content: Union[str, bytes],
            content_type: str = "text/plain"
    ) -> Optional[str]:
        """Uploads content to local filesystem."""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            mode = 'wb' if isinstance(content, bytes) else 'w'
            with open(full_path, mode) as f:
                f.write(content)

            return f"file://{full_path}"
        except Exception as e:
            logger.error(f"Local upload failed: {e}")
            return None

    async def download(self, path: str) -> Optional[str]:
        """Downloads content from local filesystem."""
        full_path = self._get_full_path(path)

        try:
            with open(full_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Local download failed: {e}")
            return None

    async def delete(self, path: str) -> bool:
        """Deletes file from local filesystem."""
        full_path = self._get_full_path(path)

        try:
            if full_path.exists():
                full_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Local delete failed: {e}")
            return False

    async def exists(self, path: str) -> bool:
        """Checks if file exists."""
        return self._get_full_path(path).exists()

    def generate_signed_url(
            self,
            path: str,
            expiration_minutes: int = 60
    ) -> Optional[str]:
        """Returns file URL for local backend."""
        full_path = self._get_full_path(path)
        if full_path.exists():
            return f"file://{full_path}"
        return None


# ============================================================
# STORAGE SERVICE
# ============================================================

class StorageService:
    """
    World-Class Storage Service.

    Features:
    - Multi-backend support (GCS, Local)
    - Automatic retry with backoff
    - Content type detection
    - Size validation
    - Signed URL generation
    - Path sanitization
    - Metadata storage

    Usage:
        service = StorageService()
        uri = await service.upload_artifact(execution_id, node_id, content)
        content = await service.get_artifact_content(uri)
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self.backend = self._create_backend()

    def _create_backend(self) -> StorageBackend:
        """Creates appropriate storage backend."""
        bucket_name = getattr(settings, 'GCS_BUCKET_NAME', None)

        if bucket_name and bucket_name.strip():
            return GCSBackend(bucket_name, self.config)
        else:
            logger.warning("GCS not configured, using local storage")
            return LocalBackend(self.config.local_storage_path, self.config)

    @property
    def is_cloud_storage(self) -> bool:
        """Checks if using cloud storage."""
        return isinstance(self.backend, GCSBackend)

    # ============================================================
    # PUBLIC METHODS
    # ============================================================

    async def upload_artifact(
            self,
            execution_id: str,
            node_id: str,
            content: Union[str, bytes],
            filename: str = "result.txt",
            metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Uploads a workflow artifact.

        Args:
            execution_id: Execution ID
            node_id: Node ID
            content: Content to upload
            filename: Filename for the artifact
            metadata: Optional metadata

        Returns:
            Storage URI or None on failure
        """
        # Sanitize inputs
        execution_id = self._sanitize_path(execution_id)
        node_id = self._sanitize_path(node_id)
        filename = self._sanitize_filename(filename)

        # Build path
        path = f"executions/{execution_id}/{node_id}/{filename}"

        # Detect content type
        content_type = self._detect_content_type(filename, content)

        # Upload content
        uri = await self.backend.upload(path, content, content_type)

        if uri:
            logger.info(
                f"Artifact uploaded: {path}",
                extra={
                    "execution_id": execution_id,
                    "node_id": node_id,
                    "size_bytes": len(content) if isinstance(content, (str, bytes)) else 0
                }
            )

        return uri

    async def get_artifact_content(
            self,
            storage_uri: str
    ) -> Optional[str]:
        """
        Retrieves artifact content from storage.

        Args:
            storage_uri: Storage URI (gs:// or file://)

        Returns:
            Content string or None on failure
        """
        if not storage_uri:
            return None

        # Handle GCS URI
        if storage_uri.startswith("gs://"):
            bucket_name = getattr(settings, 'GCS_BUCKET_NAME', '')
            path = storage_uri.replace(f"gs://{bucket_name}/", "")
            return await self.backend.download(path)

        # Handle file URI
        if storage_uri.startswith("file://"):
            path = storage_uri.replace("file://", "")
            path = path.replace(str(self.config.local_storage_path) + "/", "")
            return await self.backend.download(path)

        # Return as-is if not a storage URI
        return storage_uri

    async def delete_artifact(self, storage_uri: str) -> bool:
        """Deletes an artifact from storage."""
        if not storage_uri:
            return False

        path = self._uri_to_path(storage_uri)
        if path:
            return await self.backend.delete(path)
        return False

    async def artifact_exists(self, storage_uri: str) -> bool:
        """Checks if artifact exists."""
        if not storage_uri:
            return False

        path = self._uri_to_path(storage_uri)
        if path:
            return await self.backend.exists(path)
        return False

    def generate_signed_url(
            self,
            storage_uri: str,
            expiration_minutes: int = 60
    ) -> Optional[str]:
        """
        Generates a temporary signed URL.

        Args:
            storage_uri: Storage URI
            expiration_minutes: URL expiration time

        Returns:
            Signed URL or None
        """
        if not storage_uri:
            return None

        path = self._uri_to_path(storage_uri)
        if path:
            return self.backend.generate_signed_url(path, expiration_minutes)
        return None

    # ============================================================
    # BULK OPERATIONS
    # ============================================================

    async def delete_execution_artifacts(
            self,
            execution_id: str
    ) -> int:
        """
        Deletes all artifacts for an execution.

        Args:
            execution_id: Execution ID

        Returns:
            Number of deleted artifacts
        """
        # This would need a list operation which varies by backend
        # For now, we'll return 0 as this would need backend-specific implementation
        logger.warning("Bulk delete not fully implemented")
        return 0

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _sanitize_path(self, path: str) -> str:
        """Sanitizes a path component."""
        if not path:
            return "unknown"

        # Remove potentially dangerous characters
        path = path.replace("..", "").replace("/", "_").replace("\\", "_")
        return path[:100]  # Limit length

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitizes a filename."""
        if not filename:
            return "file.txt"

        # Keep only safe characters
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        filename = "".join(c if c in safe_chars else "_" for c in filename)

        # Ensure extension
        if "." not in filename:
            filename += ".txt"

        return filename[:255]  # Limit length

    def _detect_content_type(
            self,
            filename: str,
            content: Union[str, bytes]
    ) -> str:
        """Detects content type from filename or content."""
        # Try to detect from filename
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type:
            return mime_type

        # Try to detect from content
        if isinstance(content, str):
            if content.strip().startswith("{") or content.strip().startswith("["):
                return "application/json"
            if content.strip().startswith("<?xml") or content.strip().startswith("<"):
                return "application/xml"

        return "text/plain"

    def _uri_to_path(self, uri: str) -> Optional[str]:
        """Converts storage URI to path."""
        if uri.startswith("gs://"):
            bucket_name = getattr(settings, 'GCS_BUCKET_NAME', '')
            return uri.replace(f"gs://{bucket_name}/", "")

        if uri.startswith("file://"):
            return uri.replace("file://", "").replace(
                str(self.config.local_storage_path) + "/", ""
            )

        return None