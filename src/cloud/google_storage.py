from dotenv import load_dotenv
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
import json
from loguru import logger
from datetime import datetime, timedelta, timezone

from typing import Optional, List, Literal
import os

load_dotenv()


class GCSFileStorageManager:
    def __init__(self):
        """
        Initialize the Google Cloud Storage client.

        :param bucket_name: Name of the GCS bucket (optional, defaults to .env value).
        :param credentials_path: Optional path to the service account JSON key.
        """
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )

        self.client = storage.Client()
        self.bucket_name = os.getenv("GCS_BUCKET_NAME")

        if not self.bucket_name:
            raise ValueError(
                "Bucket name must be provided or set in the .env file as GCS_BUCKET_NAME"
            )
        self.bucket = self.client.bucket(self.bucket_name)

    def list_buckets(self) -> List[str]:
        """
        Lists all available buckets in the Google Cloud Storage account.

        :return: List of bucket names.
        """
        return [bucket.name for bucket in self.client.list_buckets()]

    def create_bucket(self, bucket_name: str, location: str = None) -> str:
        """
        Checks if the bucket exists; if not, creates a new bucket in Google Cloud Storage.

        :param bucket_name: Name of the new bucket.
        :param location: Location where the bucket will be created (default: US).
        :return: The created bucket name or a message if it already exists.
        """
        if not location:
            location = "ASIA"

        bucket = self.client.bucket(bucket_name)
        if self.client.lookup_bucket(bucket_name):
            return f"Bucket {bucket_name} already exists."

        new_bucket = self.client.create_bucket(bucket, location=location)
        return f"Bucket {new_bucket.name} created successfully in {new_bucket.location}"

    def upload_binary_file(
        self,
        file_bytes: bytes,
        destination_path: str,
        file_prefix: Literal["workflow", "agents", "upgrade"],
        content_type: str = "application/octet-stream",
        bucket_name: Optional[str] = None,
    ) -> str:
        """
        Upload binary data to Google Cloud Storage.
        """
        # Ensure the path has the 'workflow/' prefix
        prefixed_path = f"{file_prefix}/{destination_path.lstrip('/')}"

        target_bucket = self.client.bucket(bucket_name) if bucket_name else self.bucket
        blob = target_bucket.blob(prefixed_path)
        blob.upload_from_string(file_bytes, content_type=content_type)

        logger.info(f"File uploaded to {prefixed_path} in bucket {target_bucket.name}")
        return prefixed_path

    def read_binary_file(
        self, file_path: str, bucket_name: Optional[str] = None
    ) -> bytes:
        """
        Read a file's content from Google Cloud Storage.
        """

        # Get the bucket and blob reference using the provided file_path
        target_bucket = self.client.bucket(bucket_name) if bucket_name else self.bucket
        blob = target_bucket.blob(file_path)

        # Download the file content as bytes
        bytes_content = blob.download_as_bytes()
        logger.info(f"File {file_path} read from GCS bucket: {target_bucket}")
        return bytes_content


    def video_upload_from_bytes(
            self,
            destination_blob_name: str,
            file_bytes: bytes,
            job_id: str,
            content_type: str = "video/mp4",
            bucket_name: Optional[str] = None,
    ) -> str:
        """
        Uploads video binary data directly to Google Cloud Storage,
        using a structured path for videos (e.g., workflow/<user_id>/<job_id>/<unique_id>.mp4).
        Returns the gcs:// URI of the uploaded object.
        """
        target_bucket = self.client.bucket(bucket_name) if bucket_name else self.bucket
        blob = target_bucket.blob(destination_blob_name)

        try:
            blob.upload_from_string(file_bytes, content_type=content_type)
            logger.info(f"Video uploaded to gs://{target_bucket.name}/{destination_blob_name}")

            # Always return the full GCS URI
            return f"gs://{target_bucket.name}/{destination_blob_name}"
            # If you specifically wanted the public URL, you'd do:
            # return blob.public_url
            # If you want to handle cases where bucket is not public, you might fallback:
            # return blob.public_url if blob.public_url else f"gs://{target_bucket.name}/{destination_blob_name}"

        except GoogleCloudError as e:
            logger.error(f"Error uploading video {destination_blob_name} to GCS: {e}", exc_info=True)
            raise

    def upload_json_data(
        self,
        data,
        destination_path: str,
        file_prefix: Literal["workflow", "agents", "upgrade"],
        bucket_name: Optional[str] = None,
    ) -> str:
        """
        Upload JSON-serializable data to Google Cloud Storage as a JSON file.
        """
        if not destination_path.endswith(".json"):
            destination_path += ".json"
        prefixed_path = f"{file_prefix}/{destination_path.lstrip('/')}"

        # Serialize data to JSON string
        json_str = json.dumps(data)

        target_bucket = self.client.bucket(bucket_name) if bucket_name else self.bucket
        blob = target_bucket.blob(prefixed_path)
        blob.upload_from_string(json_str, content_type="application/json")

        logger.info(
            f"JSON file uploaded to {prefixed_path} in bucket {target_bucket.name}"
        )
        return prefixed_path

    def generate_signed_url(
            self, blob_name: str, expiration_in_hours: int = 24
    ) -> Optional[str]:
        """
        Generates a v4 signed URL for a GCS blob.
        This URL provides temporary read access to a private object.
        """
        try:
            blob = self.bucket.blob(blob_name)
            expiration_time = timedelta(hours=expiration_in_hours)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=expiration_time,
                method="GET",
            )
            logger.success(f"Successfully generated signed URL for blob: {blob_name}")
            return signed_url

        except GoogleCloudError as e:
            logger.error(f"Failed to generate signed URL for {blob_name}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during signed URL generation: {e}", exc_info=True)
            return None
